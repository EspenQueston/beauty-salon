"use client";

/**
 * Le menu de l'espace cliente : une entrée par section, qui suit la lecture.
 *
 * ---------------------------------------------------------------------------
 * Ce qu'il fait
 * ---------------------------------------------------------------------------
 *
 *   - un clic fait défiler en douceur jusqu'à la section (et met l'ancre
 *     dans l'adresse, pour qu'un lien partagé ou un « retour » y ramène) ;
 *   - sans clic, l'entrée active **suit le défilement** : on lit le
 *     parrainage, « Parrainage » s'allume tout seul ;
 *   - sur ordinateur, c'est une colonne collée à gauche ; sur téléphone, une
 *     barre de pastilles collée sous l'en-tête, dont la pastille active vient
 *     se placer d'elle-même dans le champ.
 *
 * Une section absente (rien à faire, parrainage fermé) n'a pas d'entrée : le
 * menu se recalcule à partir de ce qui est réellement dans la page.
 *
 * ---------------------------------------------------------------------------
 * Comment l'entrée active est choisie
 * ---------------------------------------------------------------------------
 *
 * Une ligne de lecture est tracée à 35 % de la hauteur de l'écran : la
 * section active est la dernière dont le haut l'a franchie. Plus robuste que
 * « la plus visible », qui hésite entre deux sections courtes. Arrivé tout en
 * bas de la page, la dernière section s'allume même si elle est trop courte
 * pour atteindre la ligne.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { SalonIcon, type SalonIconName } from "@/features/salon/icons";

export interface EntreeMenu {
  id: string;
  libelle: string;
  icone: SalonIconName;
  /** Un nombre qui appelle un geste (avis à donner, acompte à régler). */
  badge?: number;
}

const LIGNE_DE_LECTURE = 0.35;

/**
 * `cle` : les identifiants joints par « | ». Une chaîne plutôt qu'un
 * tableau : un tableau neuf à chaque rendu relançait le suivi à chaque
 * rendu, et le calcul en attente était annulé avant d'avoir lieu.
 */
function useSectionActive(cle: string) {
  const ids = useMemo(() => (cle ? cle.split("|") : []), [cle]);
  const [active, setActive] = useState<string>(ids[0] ?? "");
  // Pendant un défilement déclenché par un clic, l'entrée cliquée reste
  // allumée : sinon elle clignoterait sur chaque section traversée.
  const verrou = useRef<number | null>(null);

  const calculer = useCallback(() => {
    if (verrou.current !== null) return;
    // Jamais sous l'en-tête fixe et la barre du menu (≈ 140 px) : sur un
    // écran bas (téléphone à l'horizontale), 35 % tomberait derrière eux.
    const ligne = Math.max(window.innerHeight * LIGNE_DE_LECTURE, 140);
    let courante = ids[0] ?? "";
    for (const id of ids) {
      const element = document.getElementById(id);
      if (element && element.getBoundingClientRect().top <= ligne)
        courante = id;
    }
    const enBas =
      window.innerHeight + window.scrollY >=
      document.documentElement.scrollHeight - 4;
    if (enBas && ids.length) courante = ids[ids.length - 1];
    setActive(courante);
  }, [ids]);

  useEffect(() => {
    // Un calcul toutes les 60 ms au plus pendant le défilement : assez vif
    // pour suivre la lecture, sans recalculer à chaque pixel. Un minuteur
    // plutôt que requestAnimationFrame, que le navigateur suspend dans un
    // onglet en arrière-plan.
    let attente = 0;
    const planifier = () => {
      if (attente) return;
      attente = window.setTimeout(() => {
        attente = 0;
        calculer();
      }, 60);
    };
    planifier();
    window.addEventListener("scroll", planifier, { passive: true });
    window.addEventListener("resize", planifier);
    return () => {
      window.clearTimeout(attente);
      window.removeEventListener("scroll", planifier);
      window.removeEventListener("resize", planifier);
    };
  }, [calculer]);

  const choisir = useCallback(
    (id: string) => {
      setActive(id);
      if (verrou.current !== null) window.clearTimeout(verrou.current);
      // Le temps d'un défilement doux ; ensuite le suivi reprend la main.
      verrou.current = window.setTimeout(() => {
        verrou.current = null;
        calculer();
      }, 900);
    },
    [calculer],
  );

  return { active, choisir };
}

/** Les sections réellement présentes dans la page, dans l'ordre du menu. */
function usePresentes(entrees: EntreeMenu[]) {
  const [presentes, setPresentes] = useState<string[]>([]);
  const cle = entrees.map((entree) => entree.id).join("|");

  useEffect(() => {
    const mesurer = () => {
      const ids = cle
        .split("|")
        .filter((id) => id && document.getElementById(id));
      setPresentes((avant) =>
        avant.join("|") === ids.join("|") ? avant : ids,
      );
    };
    mesurer();
    // Le parrainage, les rendez-vous… arrivent après le premier rendu.
    const observateur = new MutationObserver(mesurer);
    observateur.observe(document.body, { childList: true, subtree: true });
    return () => observateur.disconnect();
  }, [cle]);

  return entrees.filter((entree) => presentes.includes(entree.id));
}

export function MenuEspace({
  entrees,
  titre,
}: {
  entrees: EntreeMenu[];
  titre: string;
}) {
  const visibles = usePresentes(entrees);
  const { active, choisir } = useSectionActive(
    visibles.map((entree) => entree.id).join("|"),
  );
  const barre = useRef<HTMLUListElement>(null);

  // Téléphone : la pastille active vient dans le champ de la barre, sans
  // faire défiler la page elle-même.
  useEffect(() => {
    const liste = barre.current;
    const pastille = liste?.querySelector<HTMLElement>(
      `[data-section="${active}"]`,
    );
    if (!liste || !pastille || liste.scrollWidth <= liste.clientWidth) return;
    const cible =
      pastille.offsetLeft - (liste.clientWidth - pastille.offsetWidth) / 2;
    liste.scrollTo({ left: Math.max(0, cible), behavior: "smooth" });
  }, [active]);

  if (visibles.length < 2) return null;

  function aller(event: React.MouseEvent<HTMLAnchorElement>, id: string) {
    const section = document.getElementById(id);
    if (!section) return;
    event.preventDefault();
    choisir(id);
    const reduit = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;
    section.scrollIntoView({
      behavior: reduit ? "auto" : "smooth",
      block: "start",
    });
    window.history.replaceState(null, "", `#${id}`);
  }

  return (
    <nav
      aria-label={titre}
      className="sticky top-[4.5rem] z-30 -mx-4 mb-5 border-y border-[var(--site-line)] bg-[color-mix(in_srgb,var(--site-ground)_88%,transparent)] px-4 py-2 backdrop-blur-md sm:-mx-6 sm:px-6 lg:top-24 lg:mx-0 lg:mb-0 lg:self-start lg:border-0 lg:bg-transparent lg:p-0 lg:backdrop-blur-none"
    >
      <p className="mb-2 hidden px-3 text-[0.7rem] font-semibold uppercase tracking-[0.14em] text-[var(--site-subtle)] lg:block">
        {titre}
      </p>
      <ul
        ref={barre}
        className="flex gap-1.5 overflow-x-auto [scrollbar-width:none] lg:flex-col lg:gap-1 lg:overflow-visible [&::-webkit-scrollbar]:hidden"
      >
        {visibles.map((entree) => {
          const actif = entree.id === active;
          return (
            <li key={entree.id} className="shrink-0">
              <a
                href={`#${entree.id}`}
                data-section={entree.id}
                aria-current={actif ? "location" : undefined}
                onClick={(event) => aller(event, entree.id)}
                className={`group relative flex items-center gap-2 whitespace-nowrap rounded-full px-3 py-1.5 text-[13px] font-medium transition lg:rounded-xl lg:px-3 lg:py-2.5 lg:text-sm ${
                  actif
                    ? "salon-gradient text-white shadow-sm"
                    : "text-[var(--site-muted)] hover:bg-[var(--salon-primary)]/[0.08] hover:text-[var(--site-ink)]"
                }`}
              >
                <SalonIcon name={entree.icone} className="size-4 shrink-0" />
                <span className="lg:flex-1">{entree.libelle}</span>
                {entree.badge ? (
                  <span
                    className={`tabular min-w-5 rounded-full px-1.5 text-center text-[11px] font-semibold leading-5 ${
                      actif
                        ? "bg-white/25 text-white"
                        : "bg-[var(--salon-primary)] text-white"
                    }`}
                  >
                    {entree.badge}
                  </span>
                ) : null}
              </a>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
