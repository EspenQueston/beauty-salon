"use client";

/**
 * Recherche et filtres du catalogue.
 *
 * À trois prestations, une liste suffit. À trente réparties en six
 * catégories — le cas d'un salon installé — retrouver « Défrisage » demande
 * de parcourir la page entière. Deux gestes couvrent l'essentiel : taper
 * trois lettres, ou cliquer une catégorie.
 *
 * Le filtre par catégorie est **distinct de sa suppression**. Dans la version
 * précédente, la seule action offerte sur une catégorie était la croix qui
 * l'efface : un clic un peu rapide et le catalogue perdait une section.
 * Cliquer filtre ; supprimer demande d'ouvrir la gestion des catégories.
 */

import { Icon } from "./icons";

export interface FilterState {
  query: string;
  categoryId: string | null;
  /** Masque les prestations désactivées, invisibles sur le mini-site. */
  activeOnly: boolean;
}

export const EMPTY_FILTER: FilterState = {
  query: "",
  categoryId: null,
  activeOnly: false,
};

export function CatalogFilter({
  categories,
  counts,
  value,
  onChange,
  total,
  shown,
}: {
  categories: { id: string; name: string }[];
  /** Nombre de prestations par catégorie : un filtre vide se voit avant le clic. */
  counts: Record<string, number>;
  value: FilterState;
  onChange: (next: FilterState) => void;
  total: number;
  shown: number;
}) {
  const filtering =
    value.query.trim() !== "" || value.categoryId !== null || value.activeOnly;

  return (
    <div className="mb-6">
      <div className="flex flex-wrap items-center gap-2">
        <label className="relative min-w-[14rem] flex-1">
          <span className="sr-only">Rechercher une prestation</span>
          <Icon
            name="sparkles"
            className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-subtle"
          />
          <input
            type="search"
            value={value.query}
            onChange={(event) =>
              onChange({ ...value, query: event.target.value })
            }
            placeholder="Rechercher une prestation…"
            className="w-full rounded-xl border border-line bg-surface py-2.5 pl-9 pr-3 text-sm text-ink transition focus:border-salon"
          />
        </label>

        <button
          type="button"
          onClick={() => onChange({ ...value, activeOnly: !value.activeOnly })}
          aria-pressed={value.activeOnly}
          className={`inline-flex items-center gap-1.5 rounded-xl border px-3 py-2.5 text-sm font-medium transition ${
            value.activeOnly
              ? "border-salon bg-salon-soft text-salon"
              : "border-line bg-surface text-muted hover:text-ink"
          }`}
        >
          <Icon name="check" className="size-4" />
          En ligne seulement
        </button>
      </div>

      {categories.length > 1 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          <Chip
            active={value.categoryId === null}
            onClick={() => onChange({ ...value, categoryId: null })}
            count={total}
          >
            Toutes
          </Chip>

          {categories.map((category) => (
            <Chip
              key={category.id}
              active={value.categoryId === category.id}
              onClick={() =>
                onChange({
                  ...value,
                  // Recliquer la catégorie courante la désélectionne : c'est
                  // le geste attendu, et il évite de chercher « Toutes ».
                  categoryId:
                    value.categoryId === category.id ? null : category.id,
                })
              }
              count={counts[category.id] ?? 0}
            >
              {category.name}
            </Chip>
          ))}
        </div>
      )}

      {filtering && (
        <p className="mt-3 flex flex-wrap items-center gap-2 text-sm text-muted">
          <span>
            <span className="tabular font-medium text-ink">{shown}</span>{" "}
            prestation{shown > 1 ? "s" : ""} sur {total}
          </span>
          <button
            type="button"
            onClick={() => onChange(EMPTY_FILTER)}
            className="rounded-lg px-2 py-1 text-sm font-medium text-salon transition hover:bg-salon-soft"
          >
            Tout afficher
          </button>
        </p>
      )}
    </div>
  );
}

function Chip({
  active,
  onClick,
  count,
  children,
}: {
  active: boolean;
  onClick: () => void;
  count: number;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm transition ${
        active
          ? "border-salon bg-salon text-white"
          : "border-line bg-surface text-muted hover:bg-surface-hover hover:text-ink"
      }`}
    >
      {children}
      <span
        className={`tabular text-xs ${active ? "text-white/70" : "text-subtle"}`}
      >
        {count}
      </span>
    </button>
  );
}
