"use client";

/**
 * Le temps qu'il reste pour régler, en clair.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi un compte à rebours et non une heure limite
 * ---------------------------------------------------------------------------
 *
 * « Avant 14:37 » oblige à regarder l'heure et à soustraire. « Il reste
 * 23 minutes » se comprend sans rien calculer — et c'est la seule chose
 * qu'on a besoin de savoir devant une application de paiement qui demande un
 * mot de passe oublié.
 *
 * ---------------------------------------------------------------------------
 * Ce qu'il ne décide pas
 * ---------------------------------------------------------------------------
 *
 * Rien. Il compte, il prévient le parent quand il atteint zéro, et c'est le
 * serveur qui dit ce qui se passe alors. Une horloge de navigateur se règle
 * à la main, se décale, se fige quand l'onglet passe en arrière-plan : lui
 * faire décider si un créneau est perdu ou non, c'est accepter qu'un
 * téléphone mal réglé prenne la décision.
 *
 * D'où `onElapsed` : à zéro, on redemande au serveur. Lui seul tranche.
 */

import { useEffect, useRef, useState } from "react";

import { SalonIcon } from "@/features/salon/icons";

/** Secondes restantes, jamais négatives. */
function secondsLeft(deadline: string): number {
  return Math.max(0, Math.round((new Date(deadline).getTime() - Date.now()) / 1000));
}

/** « 23 min », « 4 min 05 s », « 45 s » — la précision suit l'urgence. */
function human(seconds: number): string {
  if (seconds >= 600) return `${Math.ceil(seconds / 60)} min`;
  if (seconds >= 60) {
    const minutes = Math.floor(seconds / 60);
    return `${minutes} min ${String(seconds % 60).padStart(2, "0")} s`;
  }
  return `${seconds} s`;
}

export function Countdown({
  deadline,
  onElapsed,
  className = "",
}: {
  deadline: string;
  onElapsed?: () => void;
  className?: string;
}) {
  // L'état initial se calcule dans l'initialiseur, pas dans un effet : le
  // poser depuis un effet provoquerait un second rendu immédiat, et le
  // compteur s'afficherait une fraction de seconde à sa valeur de départ.
  const [left, setLeft] = useState(() => secondsLeft(deadline));

  // Un seul avertissement au parent, même si l'intervalle continue de battre.
  const warned = useRef(false);

  /*
   * Recalage quand l'échéance change, pendant le rendu et non dans un effet.
   *
   * C'est le motif recommandé par React pour ajuster un état d'après une
   * propriété : le rendu en cours est abandonné et relancé avec la bonne
   * valeur, sans jamais peindre le chiffre périmé. Le faire dans un effet
   * afficherait l'ancien compteur une image durant, puis le corrigerait.
   */
  const [seen, setSeen] = useState(deadline);
  if (seen !== deadline) {
    setSeen(deadline);
    setLeft(secondsLeft(deadline));
  }

  useEffect(() => {
    // Le drapeau se remet ici et non pendant le rendu : une référence n'est
    // pas un état, et l'écrire pendant le rendu rendrait le composant
    // sensible à un rendu abandonné.
    warned.current = false;

    const timer = setInterval(() => {
      const value = secondsLeft(deadline);
      setLeft(value);
      if (value === 0 && !warned.current) {
        warned.current = true;
        onElapsed?.();
      }
    }, 1000);

    return () => clearInterval(timer);
  }, [deadline, onElapsed]);

  if (left === 0) return null;

  // Sous deux minutes, le ton change : c'est le moment où l'on referme son
  // application de paiement pour revenir envoyer la capture.
  const urgent = left <= 120;

  return (
    <p
      className={`flex items-center gap-2 text-sm ${
        urgent ? "text-amber-700" : "text-[var(--site-muted)]"
      } ${className}`}
      // Le temps qui passe n'a pas à être annoncé à chaque seconde par un
      // lecteur d'écran : ce serait ininterrompu et illisible.
      aria-live="off"
    >
      <SalonIcon name="clock" className="size-4 shrink-0" />
      <span>
        Créneau gardé encore <strong className="tabular">{human(left)}</strong>
      </span>
    </p>
  );
}
