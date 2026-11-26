"use client";

/**
 * « Se déconnecter », avec une confirmation.
 *
 * Le bouton déconnectait au premier toucher. Sur téléphone, il est à côté
 * du nom, là où le pouce passe en faisant défiler : une cliente se
 * retrouvait dehors sans l'avoir voulu, et devait retrouver son mot de
 * passe pour revoir l'heure de son rendez-vous.
 *
 * La fenêtre est rendue sur place, en position fixe — pas dans
 * `document.body` : les couleurs du mini-site sont des variables posées sur
 * son conteneur, et un portail les perdait (fond transparent). Sur un
 * voile ; le focus va à
 * « Annuler » — Entrée ne déconnecte jamais par accident —, Échap et un clic
 * sur le voile ferment, et le focus revient au bouton d'origine.
 */

import { useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";

import { SalonIcon } from "@/features/salon/icons";

export function BoutonDeconnexion({
  onConfirmer,
}: {
  onConfirmer: () => Promise<void>;
}) {
  const t = useTranslations("espace.compte");
  const [ouvert, setOuvert] = useState(false);
  const [occupe, setOccupe] = useState(false);
  const declencheur = useRef<HTMLButtonElement>(null);
  const annuler = useRef<HTMLButtonElement>(null);
  // Lu par Échap sans relancer l'effet : le focus ne doit pas sauter
  // pendant l'envoi.
  const enCours = useRef(false);

  useEffect(() => {
    if (!ouvert) return;
    annuler.current?.focus({ preventScroll: true });
    const bouton = declencheur.current;
    const auClavier = (evenement: KeyboardEvent) => {
      if (evenement.key === "Escape" && !enCours.current) setOuvert(false);
    };
    // La page ne défile pas derrière le voile.
    const avant = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    document.addEventListener("keydown", auClavier);
    return () => {
      document.body.style.overflow = avant;
      document.removeEventListener("keydown", auClavier);
      bouton?.focus({ preventScroll: true });
    };
  }, [ouvert]);

  async function confirmer() {
    setOccupe(true);
    enCours.current = true;
    try {
      await onConfirmer();
    } finally {
      enCours.current = false;
      setOccupe(false);
      setOuvert(false);
    }
  }

  return (
    <>
      <button
        ref={declencheur}
        type="button"
        onClick={() => setOuvert(true)}
        aria-haspopup="dialog"
        className="inline-flex shrink-0 items-center gap-1.5 rounded-xl border border-[var(--site-line)] px-3 py-2 text-sm text-[var(--site-muted)] transition hover:text-[var(--site-ink)]"
      >
        <SalonIcon name="logout" className="size-4" />
        {t("seDeconnecter")}
      </button>

      {ouvert && (
        <div className="fixed inset-0 z-[60] flex items-end justify-center sm:items-center sm:p-6">
          <div
            aria-hidden
            onClick={() => !occupe && setOuvert(false)}
            className="absolute inset-0 bg-black/45 backdrop-blur-[2px]"
          />
          <div
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="deconnexion-titre"
            aria-describedby="deconnexion-corps"
            className="animate-toast-in relative w-full rounded-t-3xl border border-[var(--site-line)] bg-[var(--site-surface)] p-5 pb-[max(1.25rem,env(safe-area-inset-bottom))] shadow-2xl sm:max-w-sm sm:rounded-2xl sm:p-6"
          >
            <span
              aria-hidden
              className="mx-auto -mt-1 mb-4 block h-1 w-10 rounded-full bg-[var(--site-line)] sm:hidden"
            />
            <span
              className="mb-3 flex size-11 items-center justify-center rounded-2xl"
              style={{
                background: "var(--salon-accent)",
                color: "var(--salon-ink-accent)",
              }}
            >
              <SalonIcon name="logout" className="size-5" />
            </span>
            <h2
              id="deconnexion-titre"
              className="text-base font-semibold text-[var(--site-ink)] sm:text-lg"
            >
              {t("deconnexionTitre")}
            </h2>
            <p
              id="deconnexion-corps"
              className="mt-1 text-sm leading-relaxed text-[var(--site-muted)]"
            >
              {t("deconnexionCorps")}
            </p>
            <div className="mt-5 grid grid-cols-2 gap-2">
              <button
                ref={annuler}
                type="button"
                onClick={() => setOuvert(false)}
                disabled={occupe}
                className="rounded-xl border border-[var(--site-line)] px-4 py-2.5 text-sm font-semibold text-[var(--site-ink)] transition hover:bg-[var(--site-line)]/30 disabled:opacity-60"
              >
                {t("annuler")}
              </button>
              <button
                type="button"
                onClick={() => void confirmer()}
                disabled={occupe}
                className="salon-gradient rounded-xl px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:brightness-110 disabled:opacity-60"
              >
                {occupe ? t("unInstant") : t("confirmerDeconnexion")}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
