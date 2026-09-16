"use client";

/**
 * Un nombre qui monte jusqu'à sa valeur, une fois visible.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi ça mérite d'exister
 * ---------------------------------------------------------------------------
 *
 * « 16 prestations » posé là est une donnée ; le même nombre qui grimpe de 0
 * à 16 est une affirmation. La différence n'est pas décorative : le mouvement
 * attire l'œil sur la seule ligne du haut de page qui donne une mesure du
 * salon, et une visiteuse qui ne l'aurait pas lue la lit.
 *
 * ---------------------------------------------------------------------------
 * Trois précautions
 * ---------------------------------------------------------------------------
 *
 *   - **Il ne démarre qu'une fois visible**, et ne se rejoue pas. Un compteur
 *     qui repart à zéro chaque fois qu'on remonte est agaçant à la deuxième
 *     occurrence.
 *   - **Il s'arrête toujours sur la bonne valeur.** L'animation se cale sur
 *     l'horloge d'affichage et non sur un pas fixe : une image sautée ne
 *     laisse pas le compteur à 15 au lieu de 16.
 *   - **Sans mouvement, le nombre est là d'emblée.** C'est une donnée avant
 *     d'être un effet.
 */

import { useEffect, useRef, useState } from "react";

/** Assez court pour ne pas faire attendre, assez long pour se remarquer. */
const DUREE = 900;

export function CountUp({ value }: { value: number }) {
  const ref = useRef<HTMLSpanElement>(null);

  // L'état de départ est la valeur finale, pas zéro.
  //
  // C'est ce qui rend le composant honnête quand rien ne peut l'animer —
  // script bloqué, robot d'indexation, mouvement réduit : le nombre est là,
  // juste, dès le rendu serveur. La remise à zéro n'a lieu qu'au moment
  // précis où l'animation démarre, donc jamais dans ces cas-là.
  const [affiche, setAffiche] = useState(value);

  useEffect(() => {
    const element = ref.current;
    if (!element) return;

    const calme = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (calme || typeof IntersectionObserver === "undefined") return;

    let frame = 0;
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          observer.unobserve(entry.target);

          const depart = performance.now();
          const monter = (maintenant: number) => {
            const part = Math.min(1, (maintenant - depart) / DUREE);
            // Décélération : le nombre ralentit en approchant, comme un
            // compteur mécanique. Linéaire, il s'arrête net et paraît cassé.
            const adouci = 1 - (1 - part) ** 3;
            setAffiche(Math.round(value * adouci));
            if (part < 1) frame = requestAnimationFrame(monter);
          };
          setAffiche(0);
          frame = requestAnimationFrame(monter);
        }
      },
      { threshold: 0.4 },
    );

    observer.observe(element);
    return () => {
      observer.disconnect();
      cancelAnimationFrame(frame);
    };
  }, [value]);

  return (
    <span ref={ref} className="tabular">
      {affiche}
    </span>
  );
}
