"use client";

/**
 * Barre de sections horizontale, collante.
 *
 * L'écran Profil porte six blocs — vitrine, réseaux, couleurs, à propos,
 * règles, annulation. Corriger un numéro de téléphone puis vérifier une
 * couleur demandait deux allers-retours à l'aveugle dans une page de trois
 * écrans.
 *
 * La barre suit le défilement et **surligne la section en cours** : elle sert
 * autant à se déplacer qu'à savoir où l'on est. Elle défile
 * horizontalement sur téléphone plutôt que de passer à la ligne, pour ne pas
 * manger la moitié de l'écran.
 *
 * Le repérage passe par un `IntersectionObserver` unique plutôt que par un
 * calcul de position à chaque frappe de défilement : le navigateur fait le
 * travail hors du fil principal.
 */

import { useEffect, useRef, useState } from "react";

export interface NavSection {
  id: string;
  label: string;
}

export function SectionNav({ sections }: { sections: NavSection[] }) {
  const [active, setActive] = useState(sections[0]?.id ?? "");
  const barRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (typeof IntersectionObserver === "undefined") return;

    const observer = new IntersectionObserver(
      (entries) => {
        // Plusieurs sections peuvent être visibles ensemble ; on retient la
        // plus haute à l'écran, celle qu'on est effectivement en train de lire.
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible[0]) setActive(visible[0].target.id);
      },
      // La zone d'observation exclut la barre elle-même en haut, et les deux
      // tiers bas de l'écran : sans cela, la dernière section ne serait
      // jamais « courante » puisqu'elle n'atteint jamais le sommet.
      { rootMargin: "-96px 0px -60% 0px", threshold: 0 },
    );

    for (const section of sections) {
      const node = document.getElementById(section.id);
      if (node) observer.observe(node);
    }
    return () => observer.disconnect();
  }, [sections]);

  // Garde l'onglet courant visible quand la barre défile horizontalement.
  useEffect(() => {
    const bar = barRef.current;
    if (!bar) return;
    const current = bar.querySelector<HTMLElement>(`[data-for="${active}"]`);
    current?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [active]);

  return (
    <div
      ref={barRef}
      className="sticky top-0 z-20 -mx-4 mb-6 overflow-x-auto border-b border-line bg-bg/90 px-4 backdrop-blur sm:-mx-6 sm:px-6 lg:-mx-8 lg:px-8"
    >
      <nav aria-label="Sections du profil">
        <ul className="flex min-w-max gap-1 py-2">
          {sections.map((section) => {
            const current = section.id === active;
            return (
              <li key={section.id}>
                <a
                  href={`#${section.id}`}
                  data-for={section.id}
                  aria-current={current ? "true" : undefined}
                  className={`relative block whitespace-nowrap rounded-lg px-3 py-2 text-sm font-medium transition ${
                    current
                      ? "text-salon"
                      : "text-muted hover:bg-surface-hover hover:text-ink"
                  }`}
                >
                  {section.label}
                  {current && (
                    <span className="absolute inset-x-3 -bottom-0.5 h-0.5 rounded-full bg-salon" />
                  )}
                </a>
              </li>
            );
          })}
        </ul>
      </nav>
    </div>
  );
}
