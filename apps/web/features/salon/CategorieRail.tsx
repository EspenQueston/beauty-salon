"use client";

/**
 * Le choix d'une catégorie de prestations : une rangée de puces.
 *
 * ---------------------------------------------------------------------------
 * Ce qu'elle remplace
 * ---------------------------------------------------------------------------
 *
 * Des puces qui passaient à la ligne. Sur téléphone, quatre catégories en
 * occupaient déjà trois lignes — un bloc de boutons à traverser avant la
 * première prestation — et chacune menait ailleurs : en haut de la page du
 * catalogue depuis l'accueil, plus bas dans la page sur le catalogue. Rien
 * ne disait laquelle était choisie, puisqu'aucune ne l'était.
 *
 * ---------------------------------------------------------------------------
 * Ce qu'elle fait
 * ---------------------------------------------------------------------------
 *
 * Une seule ligne, qui défile sous le pouce, avec « Toutes » en tête. La
 * puce choisie est pleine, aux couleurs du salon : on voit où l'on est. Un
 * appui filtre sur place, sans quitter la page. Chaque puce porte le compte
 * de ses prestations — on sait avant de toucher s'il y a un choix derrière.
 *
 * Des boutons à bascule (`aria-pressed`) et non des onglets : rien n'est
 * masqué qui ne se retrouve en choisissant « Toutes », et un lecteur d'écran
 * annonce « activé » sur la catégorie en cours.
 */

import { useTranslations } from "next-intl";
import { useEffect, useRef } from "react";

import type { CategorieFiltre } from "./catalogue";
import { SalonIcon, type SalonIconName } from "./icons";

type Puce = { slug: string | null; nom: string; icone: SalonIconName; compte: number };

export function CategorieRail({
  categories,
  total,
  active,
  onChange,
}: {
  categories: CategorieFiltre[];
  total: number;
  /** Le slug de la catégorie choisie, ou null pour toutes. */
  active: string | null;
  onChange: (slug: string | null) => void;
}) {
  const t = useTranslations("salon.filtre");
  const rail = useRef<HTMLDivElement>(null);
  const premier = useRef(true);

  /*
    La puce choisie vient au centre de la rangée.

    Sans cela, choisir la dernière catégorie la laissait à moitié hors de
    l'écran. Défilement horizontal du rail seulement : `scrollIntoView`
    ferait aussi défiler la page jusqu'à lui, ce qui, au chargement de
    l'accueil, sauterait d'un coup au milieu de la page.

    Pas au premier rendu : la page s'ouvre, rien ne doit bouger tout seul.
  */
  useEffect(() => {
    if (premier.current) {
      premier.current = false;
      return;
    }
    const conteneur = rail.current;
    const puce = conteneur?.querySelector<HTMLElement>('[aria-pressed="true"]');
    if (!conteneur || !puce) return;
    conteneur.scrollTo({
      left: puce.offsetLeft - (conteneur.clientWidth - puce.clientWidth) / 2,
      behavior: "smooth",
    });
  }, [active]);

  const puces: Puce[] = [
    { slug: null, nom: t("toutes"), icone: "grid", compte: total },
    ...categories.map(({ slug, nom, icone, compte }) => ({ slug, nom, icone, compte })),
  ];

  return (
    <div
      ref={rail}
      role="group"
      aria-label={t("parCategorie")}
      /*
        D'un bord à l'autre de l'écran, les puces alignées sur la marge du
        texte. Le fondu des bords dit qu'il y en a d'autres à côté, sans
        barre de défilement.
      */
      className="-mx-4 flex snap-x gap-2 overflow-x-auto scroll-px-4 px-4 py-0.5 [mask-image:linear-gradient(to_right,transparent,black_1rem,black_calc(100%-1.5rem),transparent)] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
    >
      {puces.map((puce) => {
        const choisie = puce.slug === active;
        return (
          <button
            key={puce.slug ?? "toutes"}
            type="button"
            aria-pressed={choisie}
            onClick={() => onChange(puce.slug)}
            className={`inline-flex h-10 shrink-0 snap-start items-center gap-2 rounded-full border pl-3.5 pr-2 text-sm font-medium whitespace-nowrap transition active:scale-[0.97] ${
              choisie
                ? "salon-gradient border-transparent text-white shadow-sm"
                : "border-[var(--site-line)] bg-[var(--site-surface)] text-[var(--site-ink)] hover:border-[var(--salon-primary)]"
            }`}
          >
            <SalonIcon
              name={puce.icone}
              className={`size-4 ${choisie ? "text-white" : "text-[var(--salon-ink)]"}`}
            />
            {puce.nom}
            <span
              className={`tabular min-w-[1.5rem] rounded-full px-1.5 py-0.5 text-center text-[0.7rem] font-semibold ${
                choisie
                  ? "bg-white/20 text-white"
                  : "bg-black/[0.05] text-[var(--site-muted)]"
              }`}
            >
              {puce.compte}
            </span>
          </button>
        );
      })}
    </div>
  );
}
