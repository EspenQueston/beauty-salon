"use client";

/**
 * Dates et montants de l'espace professionnel, dans la langue de l'espace.
 *
 * Les écrans formataient avec `"fr-FR"` écrit en dur : en anglais, on lisait
 * « 9 octobre 2026 » au milieu d'une phrase anglaise. Ces formats suivent la
 * langue de l'adresse (`/en/…`).
 *
 * `en-GB` et non `en-US` : jour avant mois (« 9 October 2026 », « 09/10 »),
 * comme en français — un salon qui passe d'une langue à l'autre ne doit pas
 * se demander si le 03/04 est un 3 avril ou un 4 mars.
 */

import { useLocale } from "next-intl";
import { useMemo } from "react";

export function regionDe(langue: string): string {
  return langue === "en" ? "en-GB" : "fr-FR";
}

export function formatsPour(langue: string) {
  const region = regionDe(langue);
  return {
    region,
    /** « 9 octobre 2026 » / « 9 October 2026 ». */
    dateLongue: new Intl.DateTimeFormat(region, { day: "numeric", month: "long", year: "numeric" }),
    /** « 9 oct. » / « 9 Oct ». */
    dateCourte: new Intl.DateTimeFormat(region, { day: "numeric", month: "short" }),
    /** « 14:30 », dans les deux langues. */
    heure: new Intl.DateTimeFormat(region, { hour: "2-digit", minute: "2-digit" }),
    /**
     * Un pourcentage : « 30 % » (espace insécable) en français, « 30% » en
     * anglais. `signe` le précède : « −16 % ».
     */
    pourcent(valeur: number | string, signe = ""): string {
      return region.startsWith("fr") ? `${signe}${valeur}\u00a0%` : `${signe}${valeur}%`;
    },
    /** Un montant, sans décimales inutiles : « 99 CNY », pas « 99,00 CNY ». */
    montant(valeur: string | number, devise: string): string {
      const nombre = Number(valeur);
      return new Intl.NumberFormat(region, {
        style: "currency",
        currency: devise,
        minimumFractionDigits: Number.isInteger(nombre) ? 0 : 2,
        maximumFractionDigits: 2,
      }).format(nombre);
    },
  };
}

export function useFormats() {
  const langue = useLocale();
  return useMemo(() => formatsPour(langue), [langue]);
}
