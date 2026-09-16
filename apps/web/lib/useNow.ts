"use client";

/**
 * Horloge partagée, pour les affichages qui doivent vieillir tout seuls.
 *
 * Un « en retard de 3 min » figé à l'heure du chargement est pire qu'absent :
 * il donne un chiffre faux avec l'aplomb d'un chiffre juste. Cette horloge
 * fait donc avancer le rendu sans que personne ne recharge la page.
 *
 * Un seul `setInterval` pour toute l'application, quel que soit le nombre de
 * cartes affichées, et il s'arrête dès que plus rien ne l'écoute — un agenda
 * de trente rendez-vous ne doit pas réveiller le processeur trente fois par
 * minute sur un téléphone d'entrée de gamme.
 *
 * Le pas est volontairement grossier : à la minute près, une seconde
 * d'imprécision ne change rien à ce qui est affiché.
 */

import { useSyncExternalStore } from "react";

const TICK = 30_000;

const listeners = new Set<() => void>();
let timer: ReturnType<typeof setInterval> | null = null;

/*
 * 0 signifie « heure inconnue », et c'est aussi ce que voit le serveur.
 * Les fonctions de calcul traitent ce cas comme « rien à signaler », donc le
 * rendu serveur et la première passe client sont identiques : pas d'écart
 * d'hydratation, la valeur réelle arrive juste après le montage.
 */
let snapshot = 0;

function subscribe(listener: () => void): () => void {
  listeners.add(listener);

  // Poser l'heure ici plutôt qu'au premier battement : sans cela, un agenda
  // resterait trente secondes sans savoir quelle heure il est.
  snapshot = Date.now();

  if (timer === null) {
    timer = setInterval(() => {
      snapshot = Date.now();
      for (const notify of listeners) notify();
    }, TICK);
  }

  return () => {
    listeners.delete(listener);
    if (listeners.size === 0 && timer !== null) {
      clearInterval(timer);
      timer = null;
    }
  };
}

const getSnapshot = () => snapshot;
const getServerSnapshot = () => 0;

/** Millisecondes epoch, rafraîchies toutes les 30 s. 0 avant le montage. */
export function useNow(): number {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
