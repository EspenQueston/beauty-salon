"use client";

/**
 * Relief : inclinaison 3D au survol.
 *
 * La carte suit le curseur de quelques degrés, avec une lumière qui glisse
 * dessus. L'effet est volontairement discret : à huit degrés on donne du
 * relief, à vingt on donne le mal de mer et on rend le texte illisible.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi ce composant ne s'appelle plus `Tilt`
 * ---------------------------------------------------------------------------
 *
 * Il posait la classe `tilt`, exactement le nom que `Reveal` emploie pour sa
 * variante d'apparition en biais. Deux effets différents sous un seul nom :
 * leurs règles se recouvraient dès qu'on les employait sur la même page, et
 * la seule façon de savoir laquelle gagnait était de les lire toutes les deux.
 *
 * ---------------------------------------------------------------------------
 * Les garde-fous
 * ---------------------------------------------------------------------------
 *
 *   - `(hover: hover) and (pointer: fine)` — sur un écran tactile l'effet
 *     n'a pas de sens, et le calcul coûterait de la batterie pour rien ;
 *   - `prefers-reduced-motion` — le mouvement est désactivé sans rien
 *     casser de la mise en page ;
 *   - tout passe par `transform`, jamais par la géométrie : le navigateur
 *     compose sans recalculer la page, ce qui compte sur un mobile lent.
 *
 * Les coordonnées du curseur sont écrites en variables CSS même quand
 * l'inclinaison est coupée : `.halo` s'en sert pour éclairer la surface, et
 * une lueur qui suit le pointeur ne demande aucun mouvement de la carte.
 */

import { useCallback, useRef, type ReactNode } from "react";

const DEGRES_MAX = 7;

export function Relief({
  children,
  className = "",
  reflet = true,
  /** Amplitude relative : 0,5 pour les grandes surfaces, qui tournent moins. */
  force = 1,
}: {
  children: ReactNode;
  className?: string;
  /** Reflet qui suit le curseur. À couper sur les surfaces déjà chargées. */
  reflet?: boolean;
  force?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const actif = useRef(false);

  const permis = useCallback(() => {
    if (typeof window === "undefined") return false;
    return (
      window.matchMedia("(hover: hover) and (pointer: fine)").matches &&
      !window.matchMedia("(prefers-reduced-motion: reduce)").matches
    );
  }, []);

  const surMouvement = useCallback(
    (evenement: React.PointerEvent<HTMLDivElement>) => {
      const noeud = ref.current;
      if (!noeud) return;

      const cadre = noeud.getBoundingClientRect();
      // Position du curseur ramenée à [-0.5, 0.5] sur chaque axe.
      const x = (evenement.clientX - cadre.left) / cadre.width - 0.5;
      const y = (evenement.clientY - cadre.top) / cadre.height - 0.5;

      // Le halo suit le curseur dans tous les cas : il n'anime rien.
      noeud.style.setProperty("--reflet-x", `${((x + 0.5) * 100).toFixed(1)}%`);
      noeud.style.setProperty("--reflet-y", `${((y + 0.5) * 100).toFixed(1)}%`);

      if (!permis()) return;

      const amplitude = DEGRES_MAX * force;
      noeud.style.setProperty(
        "--relief-x",
        `${(-y * amplitude).toFixed(2)}deg`,
      );
      noeud.style.setProperty("--relief-y", `${(x * amplitude).toFixed(2)}deg`);

      if (!actif.current) {
        actif.current = true;
        noeud.dataset.incline = "true";
      }
    },
    [permis, force],
  );

  const surSortie = useCallback(() => {
    const noeud = ref.current;
    if (!noeud) return;
    actif.current = false;
    delete noeud.dataset.incline;
    noeud.style.setProperty("--relief-x", "0deg");
    noeud.style.setProperty("--relief-y", "0deg");
  }, []);

  return (
    <div
      ref={ref}
      onPointerMove={surMouvement}
      onPointerLeave={surSortie}
      className={`relief ${reflet ? "relief--reflet" : ""} ${className}`}
    >
      {children}
    </div>
  );
}
