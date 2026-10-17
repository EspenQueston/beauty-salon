"use client";

/**
 * Annuler son rendez-vous, depuis l'espace cliente.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi ce bouton existe maintenant
 * ---------------------------------------------------------------------------
 *
 * Le salon publie « annulation gratuite jusqu'à 24 h avant » sur son
 * mini-site, dans son e-mail de confirmation et sur sa page d'infos. C'était
 * une promesse que rien ne permettait d'exercer : il fallait téléphoner.
 *
 * Deux conséquences, et la seconde coûte cher. Le salon recevait des appels
 * pour un geste qu'une page peut faire. Et les clientes qui n'osent pas
 * appeler ne prévenaient pas du tout — un créneau de quatre heures perdu
 * sans qu'il puisse être reproposé.
 *
 * ---------------------------------------------------------------------------
 * Deux temps, jamais un seul
 * ---------------------------------------------------------------------------
 *
 * Annuler est irréversible : le créneau repart, et rien ne garantit qu'il
 * sera encore libre en cas de regret. Un bouton qui agit au premier appui
 * transforme un frôlement de pouce en rendez-vous perdu.
 *
 * Le premier appui ouvre donc une confirmation, qui dit ce qui va se passer
 * — y compris pour l'acompte déjà versé, qui est la vraie question et que
 * seul le salon peut trancher. Le motif reste facultatif : l'exiger ferait
 * renoncer, et une annulation sans motif vaut mieux qu'une absence.
 */

import { useTranslations } from "next-intl";
import { useState } from "react";

import { api } from "./api";
import { SalonIcon } from "@/features/salon/icons";
import type { ClientBooking } from "./types";

export function Annuler({
  booking,
  host,
  salonUrl,
  onDone,
}: {
  booking: ClientBooking;
  host: string;
  /** Racine du mini-site : c'est là qu'on renvoie hors délai. */
  salonUrl: string;
  onDone: () => void;
}) {
  const t = useTranslations("espace");
  const [ouvert, setOuvert] = useState(false);
  const [motif, setMotif] = useState("");
  const [pending, setPending] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);

  /*
    Hors délai : on ne cache pas le sujet, on donne la sortie.

    Un bouton qui disparaît sans un mot laisse croire à une panne. La phrase
    dit la règle du salon et mène à ses coordonnées — c'est la seule réponse
    honnête quand la politique demande de parler à quelqu'un.
  */
  if (!booking.can_cancel) {
    if (!booking.cancel_until) return null;
    return (
      <p className="mt-2 text-xs leading-relaxed text-[var(--site-subtle)]">
        Passé {booking.cancel_deadline_hours} h avant le rendez-vous,
        l&apos;annulation se fait avec le salon.{" "}
        <a
          href={`${salonUrl}/infos`}
          className="font-medium text-[var(--salon-ink)] underline-offset-2 hover:underline"
        >
          {t("annuler.leContacter")}
        </a>
      </p>
    );
  }

  async function annuler() {
    setPending(true);
    setErreur(null);
    try {
      await api("/api/v1/public/booking/cancel", host, {
        method: "POST",
        body: JSON.stringify({
          token: booking.cancel_token,
          reason: motif.trim(),
        }),
      });
      onDone();
    } catch (caught) {
      setErreur(caught instanceof Error ? caught.message : t("annuler.echec"));
      setPending(false);
    }
  }

  if (!ouvert) {
    return (
      <button
        type="button"
        onClick={() => setOuvert(true)}
        className="mt-2 inline-flex items-center gap-1.5 text-sm font-medium text-[var(--site-muted)] underline-offset-2 transition hover:text-red-600 hover:underline"
      >
        <SalonIcon name="close" className="size-3.5 shrink-0" />
        {t("annuler.annuler")}
      </button>
    );
  }

  return (
    <div className="mt-3 rounded-xl border border-red-200 bg-red-50/60 p-3">
      <p className="text-sm font-medium text-[var(--site-ink)]">
        {t("annuler.confirmer")}
      </p>
      <p className="mt-1 text-xs leading-relaxed text-[var(--site-muted)]">
        Le créneau repartira aussitôt et pourra être pris par quelqu&apos;un
        d&apos;autre.
        {Number(booking.deposit_amount) > 0 && (
          <>
            {" "}
            Pour l&apos;acompte déjà versé, le salon vous recontactera :
            c&apos;est lui qui décide, pas cette page.
          </>
        )}
      </p>

      <label className="mt-2.5 block">
        <span className="mb-1 block text-xs text-[var(--site-muted)]">
          {t("annuler.mot")}
        </span>
        <input
          value={motif}
          onChange={(event) => setMotif(event.target.value)}
          maxLength={280}
          placeholder={t("annuler.exemple")}
          className="w-full rounded-lg border border-[var(--site-line)] bg-[var(--site-surface)] px-3 py-2 text-sm text-[var(--site-ink)] transition focus:border-[var(--salon-primary)] focus:outline-none"
        />
      </label>

      {erreur && (
        <p role="alert" className="mt-2 text-xs font-medium text-red-600">
          {erreur}
        </p>
      )}

      {/*
        Deux colonnes : « Confirmer » et « Garder », côte à côte et de même
        largeur. Empilés, le second se retrouve sous le pouce à l'endroit
        exact où l'on vient d'appuyer.
      */}
      <div className="mt-3 grid grid-cols-2 gap-2">
        <button
          type="button"
          onClick={() => void annuler()}
          disabled={pending}
          className="rounded-lg bg-red-600 px-3 py-2.5 text-sm font-semibold text-white transition hover:bg-red-700 disabled:opacity-60"
        >
          {pending ? t("annuler.unInstant") : "Confirmer"}
        </button>
        <button
          type="button"
          onClick={() => {
            setOuvert(false);
            setErreur(null);
          }}
          className="rounded-lg border border-[var(--site-line)] bg-[var(--site-surface)] px-3 py-2.5 text-sm font-medium text-[var(--site-ink)] transition hover:border-[var(--site-line-strong)]"
        >
          Garder
        </button>
      </div>
    </div>
  );
}
