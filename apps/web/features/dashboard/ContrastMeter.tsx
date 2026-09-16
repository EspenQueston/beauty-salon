"use client";

/**
 * Note de lisibilité d'une palette, en pourcentage.
 *
 * Le salon choisit ses couleurs à l'œil, sur un écran d'ordinateur bien
 * réglé, dans une pièce éclairée. Ses clientes lisent la même page sur un
 * téléphone d'entrée de gamme, en plein soleil. Un chiffre reproductible
 * tranche là où deux avis s'opposeraient.
 *
 * Trois paires sont mesurées, parce que ce sont les trois qui décident
 * réellement d'une réservation :
 *
 *   - le prix, écrit en couleur principale sur une carte blanche ;
 *   - le texte des boutons, blanc sur la couleur principale ;
 *   - le texte courant, sur le fond de page.
 *
 * Quand une paire échoue, on ne se contente pas de le dire : on propose la
 * même teinte corrigée, et un bouton pour l'appliquer. Un diagnostic sans
 * remède se contourne en l'ignorant.
 */

import { adjustForContrast, scoreContrast, type ContrastScore } from "@/lib/contrast";
import { Icon } from "./icons";

interface Pair {
  key: string;
  label: string;
  hint: string;
  foreground: string;
  background: string;
  /** Quelle couleur corriger si la paire échoue, et comment. */
  fix?: { field: "primary" | "surface"; against: string };
}

export function ContrastMeter({
  primary,
  accent,
  surface,
  onFix,
}: {
  primary: string;
  accent: string;
  surface: string;
  onFix: (field: "primary" | "surface", value: string) => void;
}) {
  const pairs: Pair[] = [
    {
      key: "price",
      label: "Prix et titres",
      hint: "couleur principale sur une carte blanche",
      foreground: primary,
      background: "#FFFFFF",
      fix: { field: "primary", against: "#FFFFFF" },
    },
    {
      key: "button",
      label: "Texte des boutons",
      hint: "blanc sur la couleur principale",
      foreground: "#FFFFFF",
      background: primary,
      fix: { field: "primary", against: "#FFFFFF" },
    },
    {
      key: "body",
      label: "Texte courant",
      hint: "sur le fond de page",
      foreground: "#17171C",
      background: surface,
    },
    {
      key: "pill",
      label: "Pastilles",
      hint: "couleur principale sur la secondaire",
      foreground: primary,
      background: accent,
    },
  ];

  const scores = pairs
    .map((pair) => ({ pair, score: scoreContrast(pair.foreground, pair.background) }))
    .filter((row): row is { pair: Pair; score: ContrastScore } => row.score !== null);

  if (scores.length === 0) return null;

  // La note d'ensemble est celle du **maillon le plus faible**, pas une
  // moyenne : une moyenne masquerait un bouton illisible derrière trois
  // paires correctes.
  const weakest = scores.reduce((worst, row) =>
    row.score.percent < worst.score.percent ? row : worst,
  );

  return (
    <div className="rounded-xl border border-line bg-surface-muted p-4">
      <div className="flex flex-wrap items-center gap-4">
        <Gauge score={weakest.score} />

        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-center gap-2 font-medium text-ink">
            Lisibilité : {weakest.score.label}
            <span className="text-sm font-normal text-subtle">
              contraste {weakest.score.ratio.toFixed(1)}:1
            </span>
          </p>
          <p className="mt-1 text-sm leading-relaxed text-muted">
            {weakest.score.detail}
          </p>
        </div>
      </div>

      <ul className="mt-4 space-y-1.5">
        {scores.map(({ pair, score }) => {
          const suggestion =
            score.verdict === "insuffisant" || score.verdict === "limite"
              ? pair.fix
                ? adjustForContrast(primary, pair.fix.against)
                : null
              : null;

          return (
            <li
              key={pair.key}
              className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm"
            >
              <span
                aria-hidden
                className="inline-flex size-5 shrink-0 items-center justify-center rounded"
                style={{ background: pair.background, color: pair.foreground }}
              >
                <span className="text-[0.7rem] font-bold">A</span>
              </span>

              <span className="text-ink">{pair.label}</span>
              <span className="text-subtle">{pair.hint}</span>

              <span
                className={`tabular ml-auto font-semibold ${
                  score.verdict === "insuffisant"
                    ? "text-danger"
                    : score.verdict === "limite"
                      ? "text-warning"
                      : "text-success"
                }`}
              >
                {score.percent} %
              </span>

              {suggestion && (
                <button
                  type="button"
                  onClick={() => onFix(pair.fix!.field, suggestion)}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-surface px-2.5 py-1 text-xs font-medium text-ink transition hover:border-salon"
                >
                  <span
                    aria-hidden
                    className="size-3 rounded-full ring-1 ring-black/10"
                    style={{ background: suggestion }}
                  />
                  Corriger
                </button>
              )}
            </li>
          );
        })}
      </ul>

      <p className="mt-3 text-xs leading-relaxed text-subtle">
        Mesure du contraste WCAG 2.1. Au-dessus de 70 %, vos textes restent
        lisibles sur un petit écran en plein jour.
      </p>
    </div>
  );
}

/** Jauge circulaire : le chiffre se lit sans avoir à comparer deux barres. */
function Gauge({ score }: { score: ContrastScore }) {
  const radius = 26;
  const circumference = 2 * Math.PI * radius;
  const filled = (score.percent / 100) * circumference;

  const colour =
    score.verdict === "insuffisant"
      ? "var(--ui-danger)"
      : score.verdict === "limite"
        ? "var(--ui-warning)"
        : "var(--ui-success)";

  return (
    <div className="relative size-16 shrink-0">
      <svg viewBox="0 0 64 64" className="size-full -rotate-90" aria-hidden>
        <circle
          cx="32"
          cy="32"
          r={radius}
          fill="none"
          stroke="var(--ui-border)"
          strokeWidth="6"
        />
        <circle
          cx="32"
          cy="32"
          r={radius}
          fill="none"
          stroke={colour}
          strokeWidth="6"
          strokeLinecap="round"
          strokeDasharray={`${filled} ${circumference}`}
          className="transition-[stroke-dasharray] duration-500 ease-out"
        />
      </svg>

      <span className="absolute inset-0 flex items-center justify-center">
        {score.verdict === "excellent" ? (
          <span style={{ color: colour }}>
            <Icon name="check" className="size-6" />
          </span>
        ) : (
          <span className="tabular text-sm font-semibold" style={{ color: colour }}>
            {score.percent}
          </span>
        )}
      </span>

      <span className="sr-only">
        Note de lisibilité : {score.percent} sur 100. {score.label}.
      </span>
    </div>
  );
}
