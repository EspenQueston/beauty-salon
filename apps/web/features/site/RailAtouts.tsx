"use client";

/**
 * Les trois atouts, en rail à défilement par crans. Version téléphone.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi les pastilles se déduisent du défilement
 * ---------------------------------------------------------------------------
 *
 * Elles pourraient être des boutons qui pilotent le rail. Elles font
 * l'inverse : c'est le rail qui les met à jour, et elles servent aussi de
 * commande. La nuance compte — sur un écran tactile on fait glisser bien plus
 * souvent qu'on ne vise une pastille de six pixels, et un indicateur qui ne
 * suivrait pas le doigt mentirait neuf fois sur dix.
 *
 * La position vient d'`IntersectionObserver` et non d'un calcul sur
 * `scrollLeft` : un écouteur de défilement se déclenche à chaque image et
 * oblige à mesurer la géométrie à chaque fois, ce qui coûte cher sur les
 * appareils visés. L'observateur, lui, ne parle que quand la carte visible
 * change.
 */

import { useEffect, useRef, useState } from "react";

import { useTranslations } from "next-intl";

import type { Atout } from "@/features/site/contenu";

export function RailAtouts({ atouts }: { atouts: Atout[] }) {
  const t = useTranslations("accueil.atouts");
  const rail = useRef<HTMLUListElement>(null);
  const interaction = useRef(false);
  const actifRef = useRef(0);
  const [actif, setActif] = useState(0);

  useEffect(() => {
    const noeud = rail.current;
    if (!noeud || typeof IntersectionObserver === "undefined") return;

    const cartes = Array.from(noeud.children).filter(
      (n): n is HTMLElement => n instanceof HTMLElement,
    );

    const observateur = new IntersectionObserver(
      (entrees) => {
        // La carte la plus visible gagne : pendant un glissement, deux cartes
        // sont à l'écran et il faut choisir celle qui l'est le plus.
        let meilleure = -1;
        let part = 0;
        for (const entree of entrees) {
          if (entree.intersectionRatio <= part) continue;
          part = entree.intersectionRatio;
          meilleure = cartes.indexOf(entree.target as HTMLElement);
        }
        if (meilleure >= 0 && part > 0.55) {
          actifRef.current = meilleure;
          setActif(meilleure);
        }
      },
      { root: noeud, threshold: [0.25, 0.55, 0.8, 1] },
    );

    for (const carte of cartes) observateur.observe(carte);
    return () => observateur.disconnect();
  }, []);

  useEffect(() => {
    if (atouts.length < 2 || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const timer = window.setInterval(() => {
      const noeud = rail.current;
      if (!noeud || interaction.current || document.visibilityState !== "visible") return;
      const cadre = noeud.getBoundingClientRect();
      if (cadre.top > window.innerHeight * 0.85 || cadre.bottom < 0) return;
      const prochain = (actifRef.current + 1) % atouts.length;
      const carte = noeud.children[prochain];
      if (carte instanceof HTMLElement) {
        noeud.scrollTo({ left: carte.offsetLeft - noeud.offsetLeft, behavior: "smooth" });
      }
    }, 6000);
    return () => window.clearInterval(timer);
  }, [atouts.length]);

  function allerA(index: number) {
    interaction.current = true;
    const noeud = rail.current;
    const carte = noeud?.children[index];
    if (!(carte instanceof HTMLElement)) return;
    noeud?.scrollTo({
      left: carte.offsetLeft - noeud.offsetLeft,
      behavior: "smooth",
    });
  }

  return (
    <div className="sm:hidden">
      <ul ref={rail} className="rail" onPointerDown={() => { interaction.current = true; }} onFocusCapture={() => { interaction.current = true; }}>
        {atouts.map((atout, index) => (
          <li key={atout.cle}>
            <article data-actif={index === actif} className="rail-carte verre lisere relative flex h-full flex-col overflow-hidden rounded-3xl p-5 shadow-card">
              <span
                aria-hidden
                className="chiffre-fantome tabular pointer-events-none absolute -right-1 -top-1 z-0 text-6xl font-bold"
              >
                {String(index + 1).padStart(2, "0")}
              </span>

              <span className="relative z-10 inline-flex size-11 items-center justify-center rounded-2xl bg-salon-soft text-salon-ink">
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.7"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden
                  className="size-5"
                >
                  {atout.icone}
                </svg>
              </span>

              <h3 className="relative z-10 mt-4 text-lg font-semibold tracking-tight text-ink">
                {t(`${atout.cle}.titre`)}
              </h3>
              <p className="relative z-10 mt-2 flex-1 text-[0.85rem] leading-relaxed text-muted">
                {t(`${atout.cle}.corpsCourt`)}
              </p>

              <span className="relative z-10 mt-4 inline-flex w-fit rounded-full bg-salon-soft px-2.5 py-1 text-[0.66rem] font-semibold uppercase tracking-wide text-salon-ink">
                {t(`${atout.cle}.etiquette`)}
              </span>
            </article>
          </li>
        ))}
      </ul>

      {/*
        Les pastilles sont des boutons, pas des points décoratifs : quelqu'un
        qui navigue au clavier ou au lecteur d'écran doit pouvoir atteindre la
        troisième carte sans faire glisser un rail qu'il ne voit pas.
      */}
      <div className="rail-points mt-1">
        {atouts.map((atout, index) => (
          <button
            key={atout.cle}
            type="button"
            aria-current={index === actif}
            aria-label={t("allerA", { titre: t(`${atout.cle}.titre`) })}
            onClick={() => allerA(index)}
            className="grid h-6 w-6 place-items-center"
          >
            <span className="rail-point" data-actif={index === actif} />
          </button>
        ))}
      </div>
    </div>
  );
}
