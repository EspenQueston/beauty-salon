"use client";

/**
 * Ce qui, dans les effets de l'accueil, dépend du navigateur : l'interrupteur
 * de pause du fond et la préférence de mouvement réduit.
 */

import { useSyncExternalStore } from "react";

/* --------------------------------------------------------------------------
 * Mettre le fond en pause
 * ----------------------------------------------------------------------- */

/*
 * Un interrupteur pour tout ce qui bouge en fond de l'accueil : le ciel et
 * le défilé de photos du haut de page. Retenu sur l'appareil, pour tous les
 * salons : quelqu'un que le mouvement gêne ne veut pas le redire à chaque
 * mini-site.
 */
const CLE_PAUSE = "beauty-salon.fond-en-pause";
const abonnes = new Set<() => void>();
// Stockage bloqué (navigation privée) : le choix tient jusqu'au rechargement.
let enMemoire: boolean | null = null;

function lirePause(): boolean {
  if (enMemoire !== null) return enMemoire;
  try {
    return localStorage.getItem(CLE_PAUSE) === "1";
  } catch {
    return false;
  }
}

function suivrePause(rappel: () => void) {
  abonnes.add(rappel);
  const surStockage = (event: StorageEvent) => {
    if (event.key === CLE_PAUSE) rappel();
  };
  window.addEventListener("storage", surStockage);
  return () => {
    abonnes.delete(rappel);
    window.removeEventListener("storage", surStockage);
  };
}

export function basculerPauseFond() {
  enMemoire = !lirePause();
  try {
    localStorage.setItem(CLE_PAUSE, enMemoire ? "1" : "0");
  } catch {
    // Le choix reste en mémoire pour cette page.
  }
  abonnes.forEach((rappel) => rappel());
}

/** Le fond est-il en pause ? Faux côté serveur : rien n'est encore choisi. */
export function usePauseFond(): boolean {
  return useSyncExternalStore(suivrePause, lirePause, () => false);
}

/* --------------------------------------------------------------------------
 * Mouvement réduit
 * ----------------------------------------------------------------------- */

const REQUETE_CALME = "(prefers-reduced-motion: reduce)";

function suivreCalme(rappel: () => void) {
  const requete = window.matchMedia(REQUETE_CALME);
  requete.addEventListener("change", rappel);
  return () => requete.removeEventListener("change", rappel);
}

/** La visiteuse a-t-elle demandé moins d'animations à son système ? */
export function useMouvementReduit(): boolean {
  return useSyncExternalStore(
    suivreCalme,
    () => window.matchMedia(REQUETE_CALME).matches,
    () => false,
  );
}
