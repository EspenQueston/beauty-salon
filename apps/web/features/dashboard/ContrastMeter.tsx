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

import { useTranslations } from "next-intl";

import {
  adjustForContrast,
  scoreContrast,
  type ContrastScore,
} from "@/lib/contrast";
import { useFormats } from "./formats";
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
  const t = useTranslations("pro.contraste");
  const { pourcent } = useFormats();
  const pairs: Pair[] = [
    {
      key: "price",
      label: t("paires.price.libelle"),
      hint: t("paires.price.aide"),
      foreground: primary,
      background: "#FFFFFF",
      fix: { field: "primary", against: "#FFFFFF" },
    },
    {
      key: "button",
      label: t("paires.button.libelle"),
      hint: t("paires.button.aide"),
      foreground: "#FFFFFF",
      background: primary,
      fix: { field: "primary", against: "#FFFFFF" },
    },
    {
      key: "body",
      label: t("paires.body.libelle"),
      hint: t("paires.body.aide"),
      foreground: "#17171C",
      background: surface,
    },
    {
      key: "pill",
      label: t("paires.pill.libelle"),
      hint: t("paires.pill.aide"),
      foreground: primary,
      background: accent,
    },
  ];

  const scores = pairs
    .map((pair) => ({
      pair,
      score: scoreContrast(pair.foreground, pair.background),
    }))
    .filter(
      (row): row is { pair: Pair; score: ContrastScore } => row.score !== null,
    );

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
            {t("lisibilite", { verdict: t(`verdicts.${weakest.score.verdict}.libelle`) })}
            <span className="text-sm font-normal text-subtle">
              {t("ratio", { ratio: weakest.score.ratio.toFixed(1) })}
            </span>
          </p>
          <p className="mt-1 text-sm leading-relaxed text-muted">
            {t(`verdicts.${weakest.score.verdict}.detail`)}
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
                {pourcent(score.percent)}
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
                  {t("corriger")}
                </button>
              )}
            </li>
          );
        })}
      </ul>

      <p className="mt-3 text-xs leading-relaxed text-subtle">
        {t("mesure")}
      </p>
    </div>
  );
}

/** Jauge circulaire : le chiffre se lit sans avoir à comparer deux barres. */
function Gauge({ score }: { score: ContrastScore }) {
  const t = useTranslations("pro.contraste");
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
          <span
            className="tabular text-sm font-semibold"
            style={{ color: colour }}
          >
            {score.percent}
          </span>
        )}
      </span>

      <span className="sr-only">
        {t("note", {
          n: score.percent,
          verdict: t(`verdicts.${score.verdict}.libelle`),
        })}
      </span>
    </div>
  );
}
