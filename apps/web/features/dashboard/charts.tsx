"use client";

/**
 * Les graphiques des comptes, en SVG écrit à la main.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi pas une bibliothèque
 * ---------------------------------------------------------------------------
 *
 * Une bibliothèque de graphiques pèse 80 à 200 Ko avant la première pixel
 * affiché. Sur les réseaux visés — mobile, facturé à la donnée — c'est plus
 * lourd que tout le reste du tableau de bord réuni, pour quatre figures dont
 * on maîtrise entièrement la forme.
 *
 * Écrits à la main, ils héritent aussi des variables de thème : ils passent
 * en mode sombre sans une ligne de JavaScript.
 *
 * ---------------------------------------------------------------------------
 * Ce que ces figures respectent
 * ---------------------------------------------------------------------------
 *
 *   - **Un seul axe.** Recettes et dépenses sont dans la même unité, donc
 *     sur la même échelle. Deux échelles superposées laissent croire à des
 *     croisements qui n'existent pas.
 *   - **La couleur suit l'entité, jamais son rang.** « Recettes » est bleu
 *     partout, même quand elles passent deuxièmes.
 *   - **Jamais plus de trois teintes distinctes** dans une figure où toutes
 *     les parts se touchent : au-delà, deux d'entre elles deviennent
 *     indistinguables — y compris en vision normale. Le reste est regroupé
 *     sous « Autres », et le total reste exact.
 *   - **La couleur n'est jamais le seul canal.** Chaque part est étiquetée,
 *     chaque série légendée, et un tableau des valeurs reste accessible.
 */

import { useId, useState } from "react";

/* --------------------------------------------------------------------------
 * Outils communs
 * ---------------------------------------------------------------------- */

/** Échelle « jolie » : des graduations sur lesquelles l'œil se pose. */
function niceMax(value: number): number {
  if (value <= 0) return 1;
  const magnitude = 10 ** Math.floor(Math.log10(value));
  const scaled = value / magnitude;
  const step = scaled <= 1 ? 1 : scaled <= 2 ? 2 : scaled <= 5 ? 5 : 10;
  return step * magnitude;
}

function shortMoney(value: number): string {
  const absolute = Math.abs(value);
  if (absolute >= 1_000_000) return `${(value / 1_000_000).toFixed(1)} M`;
  if (absolute >= 1_000) return `${Math.round(value / 1_000)} k`;
  return String(Math.round(value));
}

function monthLabel(iso: string): string {
  const date = new Date(`${iso}T00:00:00`);
  return new Intl.DateTimeFormat("fr-FR", { month: "short" }).format(date);
}

/* --------------------------------------------------------------------------
 * Recettes et dépenses, mois par mois
 * ---------------------------------------------------------------------- */

export interface MonthPoint {
  month: string;
  income: string;
  expense: string;
  net: string;
  cumulative: string;
}

/**
 * Colonnes groupées : deux séries, une échelle, douze mois.
 *
 * Groupées et non empilées : empiler recettes et dépenses additionnerait deux
 * grandeurs qui ne s'additionnent pas — leur somme ne veut rien dire, c'est
 * leur écart qui compte.
 */
export function MonthlyBars({
  points,
  currency,
}: {
  points: MonthPoint[];
  currency: string;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const labelId = useId();

  const max = niceMax(
    Math.max(
      ...points.flatMap((point) => [Number(point.income), Number(point.expense)]),
      0,
    ),
  );

  // Repère en coordonnées SVG : le graphique s'étire, les proportions non.
  const W = 720;
  const H = 240;
  const PAD = { top: 16, right: 8, bottom: 28, left: 44 };
  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;

  const slot = plotW / Math.max(points.length, 1);
  // 2 px de fond entre deux barres voisines : sans cet écart, deux colonnes
  // adjacentes se lisent comme un seul bloc.
  const barW = Math.max(3, slot / 2 - 3);

  const y = (value: number) => PAD.top + plotH - (value / max) * plotH;

  return (
    <figure className="m-0">
      <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1.5">
        <Legend color="var(--viz-income)" label="Recettes" />
        <Legend color="var(--viz-expense)" label="Dépenses" />
      </div>

      <div className="overflow-x-auto">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="h-56 w-full min-w-[34rem] sm:h-64"
          role="img"
          aria-labelledby={labelId}
        >
          <title id={labelId}>
            Recettes et dépenses des {points.length} derniers mois
          </title>

          {/* Grille discrète : elle aide à situer, elle ne concurrence pas
              les barres. */}
          {[0, 0.25, 0.5, 0.75, 1].map((ratio) => (
            <g key={ratio}>
              <line
                x1={PAD.left}
                x2={W - PAD.right}
                y1={y(max * ratio)}
                y2={y(max * ratio)}
                stroke="var(--viz-grid)"
                strokeWidth={1}
              />
              <text
                x={PAD.left - 8}
                y={y(max * ratio) + 4}
                textAnchor="end"
                className="fill-[var(--color-subtle)] text-[11px] tabular-nums"
              >
                {shortMoney(max * ratio)}
              </text>
            </g>
          ))}

          {points.map((point, index) => {
            const income = Number(point.income);
            const expense = Number(point.expense);
            const x = PAD.left + index * slot;
            const active = hover === index;

            return (
              <g key={point.month}>
                {/* Cible de survol pleine hauteur : viser une barre de 8 px
                    au doigt est impossible. */}
                <rect
                  x={x}
                  y={PAD.top}
                  width={slot}
                  height={plotH}
                  fill={active ? "var(--viz-grid)" : "transparent"}
                  onPointerEnter={() => setHover(index)}
                  onPointerLeave={() => setHover(null)}
                />

                <rect
                  x={x + slot / 2 - barW - 1}
                  y={y(income)}
                  width={barW}
                  height={Math.max(0, PAD.top + plotH - y(income))}
                  rx={3}
                  fill="var(--viz-income)"
                  pointerEvents="none"
                />
                <rect
                  x={x + slot / 2 + 1}
                  y={y(expense)}
                  width={barW}
                  height={Math.max(0, PAD.top + plotH - y(expense))}
                  rx={3}
                  fill="var(--viz-expense)"
                  pointerEvents="none"
                />

                <text
                  x={x + slot / 2}
                  y={H - 8}
                  textAnchor="middle"
                  className={`text-[11px] ${
                    active ? "fill-[var(--color-ink)]" : "fill-[var(--color-subtle)]"
                  }`}
                >
                  {monthLabel(point.month)}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      {/* La valeur exacte au survol, sous la figure plutôt qu'en bulle
          flottante : une bulle suit mal le doigt sur un écran tactile. */}
      <figcaption
        aria-live="polite"
        className="mt-2 min-h-5 text-xs text-muted"
      >
        {hover !== null ? (
          <>
            <span className="font-medium text-ink">
              {new Intl.DateTimeFormat("fr-FR", {
                month: "long",
                year: "numeric",
              }).format(new Date(`${points[hover].month}T00:00:00`))}
            </span>{" "}
            · recettes{" "}
            <span className="tabular text-ink">
              {Number(points[hover].income).toLocaleString("fr-FR")} {currency}
            </span>{" "}
            · dépenses{" "}
            <span className="tabular text-ink">
              {Number(points[hover].expense).toLocaleString("fr-FR")} {currency}
            </span>
          </>
        ) : (
          "Survolez un mois pour le détail."
        )}
      </figcaption>
    </figure>
  );
}

/* --------------------------------------------------------------------------
 * Résultat cumulé
 * ---------------------------------------------------------------------- */

/**
 * La courbe qui répond à « est-ce que je remonte la pente ».
 *
 * Une seule série, donc pas de légende : le titre la nomme. La zone sous la
 * courbe change de couleur selon le signe — c'est la seule information que la
 * ligne seule ne donne pas au premier coup d'œil.
 */
export function CumulativeCurve({
  points,
  currency,
}: {
  points: MonthPoint[];
  currency: string;
}) {
  const labelId = useId();
  const values = points.map((point) => Number(point.cumulative));

  const max = Math.max(...values, 0);
  const min = Math.min(...values, 0);
  const span = max - min || 1;

  const W = 720;
  const H = 180;
  const PAD = { top: 14, right: 8, bottom: 24, left: 44 };
  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;

  const x = (index: number) =>
    PAD.left + (index / Math.max(points.length - 1, 1)) * plotW;
  const y = (value: number) => PAD.top + plotH - ((value - min) / span) * plotH;

  const line = values.map((value, index) => `${x(index)},${y(value)}`).join(" ");
  const area = `${PAD.left},${y(0)} ${line} ${x(values.length - 1)},${y(0)}`;
  const last = values[values.length - 1] ?? 0;
  const positive = last >= 0;

  return (
    <figure className="m-0">
      <div className="overflow-x-auto">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="h-40 w-full min-w-[34rem] sm:h-44"
          role="img"
          aria-labelledby={labelId}
        >
          <title id={labelId}>Résultat cumulé sur la période</title>

          {/* La ligne du zéro est la seule graduation qui compte ici :
              au-dessus on gagne, en dessous on perd. */}
          <line
            x1={PAD.left}
            x2={W - PAD.right}
            y1={y(0)}
            y2={y(0)}
            stroke="var(--color-line-strong)"
            strokeWidth={1}
            strokeDasharray="4 4"
          />
          <text
            x={PAD.left - 8}
            y={y(0) + 4}
            textAnchor="end"
            className="fill-[var(--color-subtle)] text-[11px]"
          >
            0
          </text>

          <polygon
            points={area}
            fill={positive ? "var(--viz-income)" : "var(--viz-expense)"}
            opacity={0.14}
          />
          <polyline
            points={line}
            fill="none"
            stroke={positive ? "var(--viz-income)" : "var(--viz-expense)"}
            strokeWidth={2}
            strokeLinejoin="round"
            strokeLinecap="round"
          />

          {/* Un seul point marqué : le dernier. Marquer les douze
              transformerait la courbe en collier de perles. */}
          <circle
            cx={x(values.length - 1)}
            cy={y(last)}
            r={4}
            fill={positive ? "var(--viz-income)" : "var(--viz-expense)"}
            stroke="var(--color-surface)"
            strokeWidth={2}
          />

          {points.map((point, index) =>
            index % 2 === 0 ? (
              <text
                key={point.month}
                x={x(index)}
                y={H - 6}
                textAnchor="middle"
                className="fill-[var(--color-subtle)] text-[11px]"
              >
                {monthLabel(point.month)}
              </text>
            ) : null,
          )}
        </svg>
      </div>

      <figcaption className="mt-1 text-xs text-muted">
        Cumul à ce jour :{" "}
        <span
          className={`tabular font-medium ${
            positive ? "text-emerald-600" : "text-danger"
          }`}
        >
          {last.toLocaleString("fr-FR")} {currency}
        </span>
      </figcaption>
    </figure>
  );
}

/* --------------------------------------------------------------------------
 * Anneau : d'où vient l'argent
 * ---------------------------------------------------------------------- */

export interface Slice {
  category: string;
  label: string;
  total: string;
}

const DONUT_COLORS = [
  "var(--viz-income)",
  "var(--viz-expense)",
  "var(--viz-third)",
  "var(--viz-other)",
];

/**
 * Anneau, trois parts au maximum plus « Autres ».
 *
 * Cette limite n'est pas esthétique. Dans une figure où toutes les parts se
 * touchent, quatre teintes catégorielles ou plus produisent au moins une
 * paire que les lecteurs daltoniens — et parfois les autres — ne distinguent
 * pas. Le serveur regroupe donc la queue sous « Autres », en gris, qui n'est
 * pas une catégorie mais l'absence de catégorie.
 *
 * Chaque part est étiquetée avec son pourcentage : la couleur ne porte jamais
 * l'information seule.
 */
export function DonutChart({
  slices,
  currency,
}: {
  slices: Slice[];
  currency: string;
}) {
  const labelId = useId();
  const total = slices.reduce((sum, slice) => sum + Number(slice.total), 0);

  if (total <= 0) {
    return (
      <p className="py-8 text-center text-sm text-muted">
        Aucune recette sur la période.
      </p>
    );
  }

  const R = 54;
  const STROKE = 22;
  const circumference = 2 * Math.PI * R;

  // Les décalages sont calculés d'avance plutôt qu'accumulés dans le rendu :
  // muter une variable pendant le rendu rend le résultat dépendant du nombre
  // de passes de React, donc instable.
  const arcs = slices.reduce<{ slice: Slice; length: number; offset: number }[]>(
    (acc, slice) => {
      const length = (Number(slice.total) / total) * circumference;
      const previous = acc[acc.length - 1];
      const offset = previous ? previous.offset + previous.length : 0;
      return [...acc, { slice, length, offset }];
    },
    [],
  );

  return (
    <figure className="m-0 flex flex-wrap items-center gap-5">
      <svg
        viewBox="0 0 140 140"
        className="size-32 shrink-0 sm:size-36"
        role="img"
        aria-labelledby={labelId}
      >
        <title id={labelId}>Répartition des recettes par origine</title>
        <g transform="rotate(-90 70 70)">
          {arcs.map(({ slice, length, offset }, index) => {
            // 2 px de fond entre deux parts : sans cet écart, deux teintes
            // voisines se lisent comme une seule.
            const drawn = Math.max(0, length - 2);
            return (
              <circle
                key={slice.category}
                cx={70}
                cy={70}
                r={R}
                fill="none"
                stroke={DONUT_COLORS[index] ?? "var(--viz-other)"}
                strokeWidth={STROKE}
                strokeDasharray={`${drawn} ${circumference - drawn}`}
                strokeDashoffset={-offset}
              />
            );
          })}
        </g>
      </svg>

      <ul className="min-w-0 flex-1 space-y-1.5">
        {slices.map((slice, index) => {
          const share = Number(slice.total) / total;
          return (
            <li
              key={slice.category}
              className="flex flex-wrap items-baseline gap-x-2 text-sm"
            >
              <span
                aria-hidden
                className="size-2.5 shrink-0 rounded-sm"
                style={{ background: DONUT_COLORS[index] ?? "var(--viz-other)" }}
              />
              <span className="min-w-0 flex-1 truncate text-ink">{slice.label}</span>
              <span className="tabular font-medium text-ink">
                {Math.round(share * 100)} %
              </span>
              <span className="tabular w-full text-xs text-subtle sm:w-auto">
                {Number(slice.total).toLocaleString("fr-FR")} {currency}
              </span>
            </li>
          );
        })}
      </ul>
    </figure>
  );
}

/* --------------------------------------------------------------------------
 * Barres classées : où part l'argent
 * ---------------------------------------------------------------------- */

/**
 * Postes de dépense, du plus lourd au plus léger.
 *
 * Horizontales parce que les noms de postes sont longs — « Eau, électricité,
 * internet » ne tient pas sous une colonne verticale sans être pivoté, et un
 * texte pivoté ne se lit pas.
 *
 * Une seule teinte, en dégradé du plus foncé au plus clair : ici c'est la
 * **magnitude** qui porte l'information, pas l'identité. Huit teintes
 * catégorielles diraient « ces postes sont différents », ce qu'on sait déjà,
 * et deviendraient indistinguables.
 */
export function RankedBars({
  rows,
  currency,
  emptyLabel,
}: {
  rows: Slice[];
  currency: string;
  emptyLabel: string;
}) {
  const total = rows.reduce((sum, row) => sum + Number(row.total), 0);
  const max = Math.max(...rows.map((row) => Number(row.total)), 0);

  if (rows.length === 0 || total <= 0) {
    return <p className="py-8 text-center text-sm text-muted">{emptyLabel}</p>;
  }

  return (
    <ul className="space-y-2.5">
      {rows.map((row, index) => {
        const value = Number(row.total);
        const width = max > 0 ? (value / max) * 100 : 0;
        // La rampe va du plus foncé (le plus gros poste) au plus clair.
        const step = Math.max(1, 8 - Math.min(index, 7));

        return (
          <li key={row.category}>
            <div className="mb-1 flex flex-wrap items-baseline justify-between gap-x-2">
              <span className="min-w-0 truncate text-sm text-ink">{row.label}</span>
              <span className="tabular text-sm font-medium text-ink">
                {value.toLocaleString("fr-FR")} {currency}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="h-2.5 min-w-0 flex-1 overflow-hidden rounded-full bg-surface-muted">
                <span
                  className="block h-full rounded-full transition-[width] duration-500"
                  style={{
                    width: `${width}%`,
                    background: `var(--viz-ramp-${step})`,
                  }}
                />
              </span>
              <span className="tabular w-10 shrink-0 text-right text-xs text-subtle">
                {Math.round((value / total) * 100)} %
              </span>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5 text-xs text-muted">
      <span
        aria-hidden
        className="size-2.5 rounded-sm"
        style={{ background: color }}
      />
      {label}
    </span>
  );
}
