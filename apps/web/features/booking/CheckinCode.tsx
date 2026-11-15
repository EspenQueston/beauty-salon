"use client";

/**
 * Le QR d'arrivée, replié par défaut.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi replié
 * ---------------------------------------------------------------------------
 *
 * Il ne sert qu'une minute, à la porte du salon. Déplié en permanence, il
 * pousserait sous la ligne de flottaison tout ce qu'on vient réellement
 * vérifier — l'heure, le prix, chez qui. Un bouton suffit, et il porte son
 * usage dans son libellé.
 *
 * ---------------------------------------------------------------------------
 * Ce qu'il contient, et ce qu'il ne donne pas
 * ---------------------------------------------------------------------------
 *
 * Un jeton signé qui désigne ce rendez-vous, rien d'autre — ni nom, ni
 * téléphone, ni montant. Et il ne donne aucun droit à lui seul : c'est la
 * session du salon qui autorise l'écriture. Quelqu'un qui photographierait
 * cet écran n'en ferait rien.
 *
 * Le code reste sur fond blanc quel que soit le thème : un lecteur a besoin
 * du contraste maximal, et l'inverser en mode sombre le rend illisible pour
 * la moitié des téléphones.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi il vit ici plutôt que dans l'espace cliente
 * ---------------------------------------------------------------------------
 *
 * Deux pages le montrent désormais : l'espace cliente et la page de suivi
 * d'un rendez-vous. Deux copies d'un QR code, c'est deux occasions d'en
 * corriger une seule — et un code d'arrivée qui diverge d'un écran à
 * l'autre est précisément ce qu'on ne peut pas se permettre à la porte du
 * salon.
 */

import { useTranslations } from "next-intl";
import { useState } from "react";
import { QRCodeSVG } from "qrcode.react";

import { SalonIcon } from "@/features/salon/icons";

export function CheckinCode({
  token,
  code = "",
  defaultOpen = false,
}: {
  token: string;
  /**
   * Le même droit d'arrivée, en six caractères.
   *
   * Il n'est pas là pour faire joli : l'appareil photo du salon manque
   * précisément les jours où il faudrait qu'il marche — permission refusée,
   * objectif rayé, poste fixe à l'accueil sans caméra. La cliente lit alors
   * son code à voix haute, et elle est enregistrée quand même.
   *
   * L'alphabet écarte les caractères qui se confondent à l'oral comme à la
   * lecture : ni O ni 0, ni I ni 1, ni S ni 5.
   */
  code?: string;
  /**
   * Déplié d'emblée.
   *
   * Vrai sur la page de suivi d'un rendez-vous, où le code est l'objet même
   * de la visite : replié, il se lit comme absent — c'est précisément ce
   * qu'on nous a signalé. Faux dans l'espace cliente, où la page répond
   * d'abord à « c'est quand, et chez qui ».
   */
  defaultOpen?: boolean;
}) {
  const t = useTranslations("reservation");
  const [open, setOpen] = useState(defaultOpen);

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="mt-4 flex w-full items-center gap-3 rounded-xl border border-dashed border-[var(--site-line)] p-3 text-left transition hover:border-[var(--salon-primary)]"
      >
        <span
          aria-hidden
          className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-[var(--salon-primary)]/12"
        >
          <SalonIcon
            name="sparkle"
            className="size-5 text-[var(--salon-ink)]"
          />
        </span>
        <span className="min-w-0">
          <span className="block text-sm font-medium text-[var(--site-ink)]">
            {t("code.titre")}
          </span>
          <span className="block text-xs text-[var(--site-subtle)]">
            {t("code.sousTitre")}
          </span>
        </span>
      </button>
    );
  }

  return (
    <div className="mt-4 rounded-xl border border-[var(--site-line)] p-4 text-center">
      <span className="mx-auto block w-fit rounded-2xl bg-white p-3 ring-1 ring-black/10">
        <QRCodeSVG value={token} size={176} level="M" marginSize={0} />
      </span>

      {code && (
        // Le code est écrit en toutes lettres sous le QR, pas caché derrière
        // un « afficher » : au comptoir, la caméra a déjà échoué quand on en
        // a besoin, et il ne reste ni le temps ni le réseau pour dérouler un
        // second écran.
        <p className="mt-3 flex flex-wrap items-baseline justify-center gap-x-2 gap-y-0.5">
          <span className="text-xs text-[var(--site-subtle)]">
            ou dictez ce code
          </span>
          <span className="tabular text-lg font-semibold tracking-[0.22em] text-[var(--site-ink)]">
            {code.slice(0, 3)} {code.slice(3)}
          </span>
        </p>
      )}

      <p className="mt-2 text-sm text-[var(--site-muted)]">
        {t("code.explication")}
      </p>
      <button
        type="button"
        onClick={() => setOpen(false)}
        className="mt-2 text-xs text-[var(--site-subtle)] underline-offset-2 hover:text-[var(--site-ink)] hover:underline"
      >
        Masquer
      </button>
    </div>
  );
}
