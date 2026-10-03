"use client";

/**
 * Le catalogue complet : une recherche, une rangée de catégories, les cartes.
 *
 * ---------------------------------------------------------------------------
 * Ce qu'on cherche en arrivant ici
 * ---------------------------------------------------------------------------
 *
 * Une prestation précise — « box braids », « pose gel » — ou une famille.
 * Les deux gestes sont au même endroit, en haut, et restent à portée pendant
 * qu'on descend : la barre se colle sous le menu. Sur un catalogue de trente
 * prestations, remonter tout en haut pour changer de catégorie était le
 * geste le plus fréquent de la page.
 *
 * ---------------------------------------------------------------------------
 * La recherche
 * ---------------------------------------------------------------------------
 *
 * Sans casse ni accents, sur le nom, la description et la catégorie. Chaque
 * mot tapé doit se retrouver quelque part — « tresses longues » ne montre pas
 * toutes les tresses ni tout ce qui est long. Elle se combine avec la
 * catégorie choisie : chercher « gel » dans « Ongles ».
 *
 * L'état tient dans l'adresse (`?categorie=ongles&q=gel`), remplacée et non
 * empilée : un lien partagé ouvre la même vue, et le bouton Retour ne
 * rejoue pas chaque lettre tapée.
 */

import { useTranslations } from "next-intl";
import { useDeferredValue, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { Reveal } from "@/features/ui/Reveal";

import { CategorieRail } from "./CategorieRail";
import { normaliser, type CategorieFiltre } from "./catalogue";
import { SalonIcon } from "./icons";
import { Pill } from "./ui";

export type PrestationCatalogue = {
  id: string;
  /** Nom, description et catégorie, déjà normalisés par le serveur. */
  texte: string;
  carte: ReactNode;
};

export type SectionCatalogue = {
  categorie: CategorieFiltre;
  prestations: PrestationCatalogue[];
};

/** Hauteur du menu du mini-site, qui reste collé en haut (SalonNav). */
const SOUS_LE_MENU = 61;

export function CatalogueExplorer({
  sections,
  initiale,
}: {
  sections: SectionCatalogue[];
  initiale: { categorie: string | null; q: string };
}) {
  const t = useTranslations("salon.filtre");
  const tp = useTranslations("salon.pages");
  const haut = useRef<HTMLDivElement>(null);

  const categories = sections.map((section) => section.categorie);
  const total = categories.reduce((somme, c) => somme + c.compte, 0);

  // Une catégorie inconnue dans l'adresse — renommée depuis le partage du
  // lien — retombe sur « Toutes » plutôt que sur une page vide.
  const [categorie, setCategorie] = useState<string | null>(
    categories.some((c) => c.slug === initiale.categorie) ? initiale.categorie : null,
  );
  const [recherche, setRecherche] = useState(initiale.q);
  // La liste suit la frappe sans la ralentir : sur un téléphone d'entrée de
  // gamme, refiltrer trente cartes à chaque lettre se sent.
  const differee = useDeferredValue(recherche);

  const visibles = useMemo(() => {
    const mots = normaliser(differee).split(/\s+/).filter(Boolean);
    return sections
      .filter((section) => !categorie || section.categorie.slug === categorie)
      .map((section) => ({
        ...section,
        prestations: section.prestations.filter((p) =>
          mots.every((mot) => p.texte.includes(mot)),
        ),
      }))
      .filter((section) => section.prestations.length > 0);
  }, [sections, categorie, differee]);

  const trouvees = visibles.reduce((somme, s) => somme + s.prestations.length, 0);
  const filtre = Boolean(categorie) || recherche.trim() !== "";

  /*
    L'adresse suit l'état, sans navigation.

    `replaceState` et non `pushState` : chaque lettre tapée ferait sinon une
    entrée d'historique, et le bouton Retour deviendrait inutilisable.
  */
  useEffect(() => {
    const url = new URL(window.location.href);
    if (categorie) url.searchParams.set("categorie", categorie);
    else url.searchParams.delete("categorie");
    const q = differee.trim();
    if (q) url.searchParams.set("q", q);
    else url.searchParams.delete("q");
    if (url.href !== window.location.href) {
      window.history.replaceState(window.history.state, "", url);
    }
  }, [categorie, differee]);

  /*
    Choisir une catégorie ramène au début des résultats, si l'on était
    descendu : sinon on changeait de famille en restant au milieu de la
    précédente, devant un écran qui semblait n'avoir pas réagi.
  */
  function choisir(slug: string | null) {
    setCategorie(slug);
    const bloc = haut.current;
    if (bloc && bloc.getBoundingClientRect().top < SOUS_LE_MENU) {
      bloc.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  function toutAfficher() {
    setRecherche("");
    choisir(null);
  }

  return (
    <div ref={haut} style={{ scrollMarginTop: SOUS_LE_MENU }}>
      {/*
        La barre collée sous le menu. Fond translucide et flou : on devine
        les cartes qui passent dessous, et l'on comprend qu'elle flotte.
      */}
      <div
        className="sticky z-30 -mx-4 border-b border-[var(--site-line)] bg-[var(--site-ground)]/85 px-4 pb-3 pt-3 backdrop-blur-md"
        style={{ top: SOUS_LE_MENU }}
      >
        <label className="relative block">
          <span className="sr-only">{t("rechercher")}</span>
          <SalonIcon
            name="search"
            className="pointer-events-none absolute left-4 top-1/2 size-5 -translate-y-1/2 text-[var(--site-subtle)]"
          />
          {/*
            16 px de texte, pas moins : en dessous, Safari sur iPhone agrandit
            toute la page au moment où l'on touche le champ.
          */}
          <input
            type="search"
            value={recherche}
            onChange={(evenement) => setRecherche(evenement.target.value)}
            onKeyDown={(evenement) => {
              if (evenement.key === "Escape") setRecherche("");
            }}
            placeholder={t("exemple")}
            enterKeyHint="search"
            autoComplete="off"
            spellCheck={false}
            className="h-12 w-full rounded-2xl border border-[var(--site-line)] bg-[var(--site-surface)] pl-12 pr-12 text-base text-[var(--site-ink)] shadow-sm outline-none transition placeholder:text-[var(--site-subtle)] focus:border-[var(--salon-primary)] focus:ring-4 focus:ring-[var(--salon-primary)]/15 [&::-webkit-search-cancel-button]:hidden"
          />
          {recherche && (
            <button
              type="button"
              onClick={() => setRecherche("")}
              aria-label={t("effacer")}
              className="absolute right-2 top-1/2 flex size-9 -translate-y-1/2 items-center justify-center rounded-full text-[var(--site-muted)] transition hover:bg-black/[0.05] hover:text-[var(--site-ink)]"
            >
              <SalonIcon name="close" className="size-4" />
            </button>
          )}
        </label>

        {categories.length > 1 && (
          <div className="mt-3">
            <CategorieRail
              categories={categories}
              total={total}
              active={categorie}
              onChange={choisir}
            />
          </div>
        )}
      </div>

      {/* Annoncé aux lecteurs d'écran à chaque changement de filtre. */}
      <p
        aria-live="polite"
        className={`mt-4 text-sm text-[var(--site-muted)] ${filtre ? "" : "sr-only"}`}
      >
        {t("resultats", { n: trouvees })}
      </p>

      {visibles.length === 0 ? (
        <div className="mx-auto mt-10 max-w-sm text-center">
          <span className="mx-auto flex size-14 items-center justify-center rounded-2xl bg-[var(--salon-primary-soft)] text-[var(--salon-ink)]">
            <SalonIcon name="search" className="size-6" />
          </span>
          <h2 className="mt-4 text-lg font-semibold text-[var(--site-ink)]">
            {t("aucunTitre")}
          </h2>
          <p className="mt-1.5 text-sm text-[var(--site-muted)]">
            {recherche.trim()
              ? t("aucunCorpsRecherche", { q: recherche.trim() })
              : t("aucunCorps")}
          </p>
          <button
            type="button"
            onClick={toutAfficher}
            className="salon-gradient mt-5 inline-flex h-11 items-center justify-center rounded-full px-6 text-sm font-semibold text-white shadow-sm transition hover:brightness-110"
          >
            {t("toutAfficher")}
          </button>
        </div>
      ) : (
        <div className="mt-6 space-y-12">
          {visibles.map(({ categorie: c, prestations }) => (
            <Reveal
              key={c.id}
              as="section"
              // Les ancres d'avant (`/prestations#ongles`) mènent toujours
              // à leur section, sous le menu et la barre de filtre.
              id={c.slug}
              className="scroll-mt-48"
            >
              <div className="mb-4 flex flex-wrap items-center gap-3">
                <span
                  className="flex size-11 items-center justify-center rounded-2xl"
                  style={{
                    background: "var(--salon-accent)",
                    color: "var(--salon-ink-accent)",
                  }}
                >
                  <SalonIcon name={c.icone} className="size-5" />
                </span>
                <h2 className="text-xl font-semibold tracking-tight text-[var(--site-ink)]">
                  {c.nom}
                </h2>
                <Pill>{tp("prestationsCompte", { n: prestations.length })}</Pill>
              </div>

              <div className="grid grid-cols-2 gap-3 sm:gap-4 md:grid-cols-3 lg:grid-cols-4">
                {prestations.map(({ id, carte }) => (
                  <div key={id}>{carte}</div>
                ))}
              </div>
            </Reveal>
          ))}
        </div>
      )}
    </div>
  );
}
