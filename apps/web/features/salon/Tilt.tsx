"use client";

/**
 * Inclinaison 3D au survol.
 *
 * La carte suit le curseur de quelques degrés, avec une lumière qui glisse
 * dessus. L'effet est volontairement discret : à huit degrés on donne du
 * relief, à vingt on donne le mal de mer et on rend le texte illisible.
 *
 * Trois garde-fous, tous nécessaires ici :
 *
 *   - `(hover: hover) and (pointer: fine)` — sur un écran tactile l'effet
 *     n'a pas de sens, et le calcul coûterait de la batterie pour rien ;
 *   - `prefers-reduced-motion` — le mouvement est désactivé sans rien
 *     casser de la mise en page ;
 *   - tout passe par `transform`, jamais par la géométrie : le navigateur
 *     compose sans recalculer la page, ce qui compte sur un mobile lent.
 */

import { useCallback, useRef, type ReactNode } from "react";

const MAX_DEGREES = 7;

export function Tilt({
  children,
  className = "",
  glare = true,
}: {
  children: ReactNode;
  className?: string;
  /** Reflet qui suit le curseur. À couper sur les surfaces déjà chargées. */
  glare?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const active = useRef(false);

  const enabled = useCallback(() => {
    if (typeof window === "undefined") return false;
    return (
      window.matchMedia("(hover: hover) and (pointer: fine)").matches &&
      !window.matchMedia("(prefers-reduced-motion: reduce)").matches
    );
  }, []);

  const onMove = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      const node = ref.current;
      if (!node || !enabled()) return;

      const box = node.getBoundingClientRect();
      // Position du curseur ramenée à [-0.5, 0.5] sur chaque axe.
      const x = (event.clientX - box.left) / box.width - 0.5;
      const y = (event.clientY - box.top) / box.height - 0.5;

      node.style.setProperty("--tilt-x", `${(-y * MAX_DEGREES).toFixed(2)}deg`);
      node.style.setProperty("--tilt-y", `${(x * MAX_DEGREES).toFixed(2)}deg`);
      node.style.setProperty("--glare-x", `${((x + 0.5) * 100).toFixed(1)}%`);
      node.style.setProperty("--glare-y", `${((y + 0.5) * 100).toFixed(1)}%`);

      if (!active.current) {
        active.current = true;
        node.dataset.tilting = "true";
      }
    },
    [enabled],
  );

  const onLeave = useCallback(() => {
    const node = ref.current;
    if (!node) return;
    active.current = false;
    delete node.dataset.tilting;
    node.style.setProperty("--tilt-x", "0deg");
    node.style.setProperty("--tilt-y", "0deg");
  }, []);

  return (
    <div
      ref={ref}
      onPointerMove={onMove}
      onPointerLeave={onLeave}
      className={`tilt ${glare ? "tilt--glare" : ""} ${className}`}
    >
      {children}
    </div>
  );
}
