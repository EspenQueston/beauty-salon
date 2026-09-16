"use client";

/**
 * L'état d'ouverture, et il bouge tout seul.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi ce n'est pas un simple calcul côté serveur
 * ---------------------------------------------------------------------------
 *
 * Le serveur sait très bien dire « ouvert » au moment où il rend la page.
 * Mais une page de salon reste ouverte : on la partage sur WhatsApp, on la
 * rouvre le soir, on la laisse dans un onglet. Une heure plus tard, la
 * pastille annonce encore « Ferme à 22:00 » alors qu'il est 22 h 30.
 *
 * Elle se recalcule donc toutes les trente secondes dans le navigateur. Ce
 * n'est pas un gadget : c'est la seule chose de la page qui prouve qu'elle
 * est branchée sur un commerce réel et non imprimée une fois pour toutes.
 *
 * ---------------------------------------------------------------------------
 * `useSyncExternalStore` plutôt qu'un effet
 * ---------------------------------------------------------------------------
 *
 * Un `useState` posé depuis un effet ferait clignoter la pastille après
 * l'hydratation et tomberait sous la règle `set-state-in-effect`. Ici,
 * `getServerSnapshot` renvoie l'instant que le serveur a utilisé : le premier
 * rendu du navigateur est identique au sien au caractère près, donc aucun
 * avertissement d'hydratation. Ce n'est qu'ensuite que l'horloge prend la
 * main.
 *
 * L'instantané est arrondi à la demi-minute : `getSnapshot` est appelé à
 * chaque rendu et doit renvoyer la même valeur tant que rien n'a bougé,
 * sinon React boucle.
 */

import { useSyncExternalStore } from "react";

import type { PublicSalon } from "@/lib/types";
import { etatOuverture } from "./ouverture";

const PAS = 30_000;

const abonnes = new Set<() => void>();
let horloge: ReturnType<typeof setInterval> | null = null;

function souscrire(rappel: () => void): () => void {
  abonnes.add(rappel);
  if (horloge === null) {
    horloge = setInterval(() => {
      for (const abonne of abonnes) abonne();
    }, PAS);
  }
  return () => {
    abonnes.delete(rappel);
    if (abonnes.size === 0 && horloge !== null) {
      clearInterval(horloge);
      horloge = null;
    }
  };
}

const instantaneNavigateur = () => Math.floor(Date.now() / PAS) * PAS;

export function StatutOuverture({
  salon,
  instantServeur,
  ton = "clair",
}: {
  salon: PublicSalon;
  /** L'instant retenu par le serveur, pour une hydratation identique. */
  instantServeur: number;
  /** « clair » : posé sur une photo. « encre » : posé sur la page. */
  ton?: "clair" | "encre";
}) {
  const instant = useSyncExternalStore(
    souscrire,
    instantaneNavigateur,
    () => instantServeur,
  );

  const etat = etatOuverture(salon, new Date(instant));
  if (!etat.detail) return null;

  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-medium ${
        ton === "clair"
          ? "bg-white/15 text-white backdrop-blur"
          : "border border-[var(--site-line)] bg-[var(--site-surface)] text-[var(--site-ink)]"
      }`}
    >
      {/*
        Le point pulse quand c'est ouvert, et seulement alors.

        Une pastille qui clignote en permanence devient un décor qu'on cesse
        de voir. Réservée à l'état ouvert, la pulsation *est* l'information :
        elle dit « en ce moment », ce qu'aucun mot ne dit aussi vite.
      */}
      <span className="relative flex size-2">
        {etat.ouvert && (
          <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-400 opacity-75" />
        )}
        <span
          className={`relative inline-flex size-2 rounded-full ${
            etat.ouvert ? "bg-emerald-400" : "bg-neutral-400"
          }`}
        />
      </span>
      <span>
        <span className="font-semibold">
          {etat.ouvert ? "Ouvert" : "Fermé"}
        </span>
        <span className={ton === "clair" ? "text-white/75" : "text-[var(--site-muted)]"}>
          {" · "}
          {etat.detail}
        </span>
      </span>
    </span>
  );
}
