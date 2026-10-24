"use client";

/**
 * Proposer les notifications au bon moment — et savoir se taire.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi une invitation, en plus du réglage de la cloche
 * ---------------------------------------------------------------------------
 *
 * Le réglage existait, rangé au pied du panneau des notifications : il
 * fallait ouvrir la cloche, descendre, comprendre. Sur téléphone, presque
 * personne ne le trouvait — et une gérante sans notification découvre la
 * réservation de 9 h à 11 h. L'invitation vient donc à elle, une fois le
 * tableau de bord chargé.
 *
 * ---------------------------------------------------------------------------
 * Ce qu'elle ne fait jamais
 * ---------------------------------------------------------------------------
 *
 *   - **demander la permission d'elle-même** : la fenêtre du navigateur ne
 *     s'ouvre qu'au clic sur « Activer ». Surgie sans geste, elle se fait
 *     refuser par réflexe, et un refus ne se rattrape plus depuis la page ;
 *   - **insister** : « Plus tard » la fait taire trois jours, puis quinze
 *     après trois reports. Elle ne se montre pas quand il n'y a rien à
 *     proposer (déjà activé, navigateur incapable).
 *
 * Un refus enregistré dans le navigateur ne se rattrape pas depuis la page —
 * mais c'est précisément l'appareil qui ne sonnera pas. L'invitation le dit
 * alors, avec le chemin des réglages, une fois par mois au plus.
 *
 * Le report est gardé dans le navigateur : il concerne cet appareil, comme
 * l'abonnement lui-même.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import type { EtatPush } from "@/features/dashboard/push";

const JOUR = 86_400_000; // en millisecondes

interface Report {
  jusqua: number;
  fois: number;
}

function lireReport(cle: string): Report | null {
  try {
    const brut = localStorage.getItem(cle);
    return brut ? (JSON.parse(brut) as Report) : null;
  } catch {
    return null;
  }
}

function ecrireReport(cle: string, report: Report): void {
  try {
    localStorage.setItem(cle, JSON.stringify(report));
  } catch {
    // Navigation privée : l'invitation reviendra au prochain chargement,
    // ce qui reste supportable.
  }
}

export type EtapeRappel = "invite" | "ios" | "occupe" | "active" | "refuse";

export function useRappelPush({
  cle,
  actif,
  lireEtat,
  activer,
  delai = 2500,
}: {
  /** Clé de stockage du report, propre à l'espace (salon, cliente). */
  cle: string;
  /** Faux tant que l'espace n'est pas prêt (session, salon choisi). */
  actif: boolean;
  lireEtat: () => Promise<EtatPush>;
  activer: () => Promise<EtatPush>;
  delai?: number;
}) {
  const [etape, setEtape] = useState<EtapeRappel | null>(null);
  // Les fonctions changent à chaque rendu du parent ; seules comptent les
  // dernières, au moment où l'on s'en sert.
  const lire = useRef(lireEtat);
  const brancher = useRef(activer);
  useEffect(() => {
    lire.current = lireEtat;
    brancher.current = activer;
  });

  useEffect(() => {
    if (!actif) return;
    let annule = false;
    const minuterie = window.setTimeout(() => {
      const report = lireReport(cle);
      if (report && report.jusqua > Date.now()) return;
      lire
        .current()
        .then((etat) => {
          if (annule) return;
          if (etat === "possible") setEtape("invite");
          else if (etat === "non-installe") setEtape("ios");
          else if (etat === "refuse") setEtape("refuse");
        })
        .catch(() => undefined);
    }, delai);
    return () => {
      annule = true;
      window.clearTimeout(minuterie);
    };
  }, [actif, cle, delai]);

  const plusTard = useCallback(() => {
    const fois = (lireReport(cle)?.fois ?? 0) + 1;
    ecrireReport(cle, {
      fois,
      jusqua: Date.now() + (fois >= 3 ? 15 : 3) * JOUR,
    });
    setEtape(null);
  }, [cle]);

  const accepter = useCallback(async () => {
    setEtape("occupe");
    let resultat: EtatPush;
    try {
      resultat = await brancher.current();
    } catch {
      resultat = "incompatible";
    }
    if (resultat === "pret") {
      setEtape("active");
      window.setTimeout(() => setEtape(null), 2600);
    } else if (resultat === "refuse") {
      // Plus rien à proposer depuis la page : on explique, puis on se tait
      // pour de bon (un mois), le réglage du navigateur est le seul chemin.
      ecrireReport(cle, { fois: 9, jusqua: Date.now() + 30 * JOUR });
      setEtape("refuse");
    } else if (resultat === "possible") {
      // La fenêtre du navigateur a été fermée sans choisir.
      setEtape("invite");
    } else {
      setEtape(null);
    }
  }, [cle]);

  /** « Compris » sur un refus : rien de plus à faire ici avant un mois. */
  const fermer = useCallback(() => {
    ecrireReport(cle, { fois: 9, jusqua: Date.now() + 30 * JOUR });
    setEtape(null);
  }, [cle]);

  return { etape, plusTard, accepter, fermer };
}
