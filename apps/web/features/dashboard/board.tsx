"use client";

/**
 * Les blocs du tableau des comptes.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi un fichier à part
 * ---------------------------------------------------------------------------
 *
 * Cette mise en page — pastille d'icône qui déborde de la carte, panneau de
 * couleur en tête de graphique, tableau à barres de progression, fil vertical
 * des derniers mouvements — ne vaut que pour l'écran des comptes. C'est le
 * seul de l'espace où l'on vient lire des chiffres et rien d'autre : ailleurs
 * on vient agir, et une carte qui commence par un aplat de couleur repousse
 * le bouton d'un demi-écran vers le bas.
 *
 * Les garder ici plutôt que dans `features/ui` est donc délibéré : rien de ce
 * fichier ne doit fuir vers l'agenda ou la fiche d'une cliente.
 *
 * ---------------------------------------------------------------------------
 * La couleur ne dit jamais seule
 * ---------------------------------------------------------------------------
 *
 * Les dégradés portent la hiérarchie — ce qui saute aux yeux en premier —
 * jamais l'information elle-même. Un montant garde son signe écrit, une
 * évolution garde sa flèche, une part garde son pourcentage. Une gérante qui
 * distingue mal le rouge du vert lit exactement la même page.
 */

import { useId, type ReactNode } from "react";

import { Icon, type IconName } from "./icons";

/* --------------------------------------------------------------------------
 * Palette
 * ---------------------------------------------------------------------- */

export type Tone = "dark" | "info" | "success" | "danger" | "warning" | "salon";

/**
 * Dégradés à 195° : la lumière tombe d'en haut à gauche, comme sur le reste
 * des surfaces du produit. Un angle par carte donnerait six sources de
 * lumière différentes sur le même écran.
 */
const GRADIENTS: Record<Tone, string> = {
  dark: "linear-gradient(195deg, #42424a 0%, #191919 100%)",
  info: "linear-gradient(195deg, #49a3f1 0%, #1a73e8 100%)",
  success: "linear-gradient(195deg, #66bb6a 0%, #43a047 100%)",
  danger: "linear-gradient(195deg, #ec407a 0%, #d81b60 100%)",
  warning: "linear-gradient(195deg, #ffa726 0%, #fb8c00 100%)",
  salon:
    "linear-gradient(195deg, color-mix(in srgb, var(--salon-primary) 68%, white) 0%, var(--salon-primary) 100%)",
};

/** L'ombre reprend la teinte de la pastille : une ombre grise la décolle du
 *  fond, une ombre colorée la fait appartenir à la carte. */
const HALOS: Record<Tone, string> = {
  dark: "rgb(25 25 25 / 0.42)",
  info: "rgb(26 115 232 / 0.42)",
  success: "rgb(67 160 71 / 0.42)",
  danger: "rgb(216 27 96 / 0.42)",
  warning: "rgb(251 140 0 / 0.42)",
  salon: "color-mix(in srgb, var(--salon-primary) 42%, transparent)",
};

export function toneStyle(tone: Tone, spread = 18) {
  return {
    backgroundImage: GRADIENTS[tone],
    boxShadow: `0 ${Math.round(spread / 2)}px ${spread}px -${Math.round(
      spread / 3,
    )}px ${HALOS[tone]}`,
  };
}

/* --------------------------------------------------------------------------
 * Le chiffre, en tête de page
 * ---------------------------------------------------------------------- */

export interface Evolution {
  /** Variation en pourcentage, ou `null` quand la période de référence est
   *  vide — diviser par zéro ne donne pas « 0 % », il ne donne pas de
   *  réponse. */
  percent: number | null;
  /** Ce à quoi on compare, écrit en toutes lettres. */
  against: string;
  /** Sens qui constitue une bonne nouvelle. Une dépense qui monte n'en est
   *  pas une, et la teinte doit le dire. */
  good: "up" | "down";
  /** Unité de la variation : « % » par défaut, « pts » pour une marge — une
   *  marge qui passe de 10 à 13 gagne 3 points, pas 30 %. */
  unit?: string;
}

export function StatCard({
  icon,
  tone,
  label,
  value,
  unit,
  evolution,
  note,
}: {
  icon: IconName;
  tone: Tone;
  label: string;
  value: string;
  unit?: string;
  evolution?: Evolution | null;
  /** Remplace l'évolution quand il n'y en a pas à montrer. */
  note?: string;
}) {
  return (
    <div className="relative flex flex-col rounded-2xl border border-line bg-surface px-3.5 pb-3 pt-4 shadow-card sm:px-5 sm:pb-4">
      {/*
        Deux dispositions, et la bascule n'est pas cosmétique.

        À partir de `sm`, celle de la référence : pastille à gauche, chiffres
        alignés à droite. Elle suppose une carte large.

        En dessous, la pastille passe au-dessus et les chiffres prennent
        toute la largeur — parce qu'en deux colonnes sur un téléphone de 320
        points, la disposition en rangée ne laisse que 54 points au nombre,
        et « −1 000 k » en demande 74. Mesuré, pas supposé : le nombre se
        faisait couper en « 1 8… », et un montant tronqué ne vaut rien.
      */}
      <div className="flex flex-col items-start gap-2 sm:flex-row sm:justify-between sm:gap-3">
        {/*
          La pastille déborde vers le haut de sa carte. Ce n'est pas un
          ornement : elle sort de la grille, donc l'œil la trouve avant de
          lire, et le repérage d'une carte parmi quatre se fait à la couleur
          plutôt qu'au libellé.
        */}
        <span
          aria-hidden
          style={toneStyle(tone)}
          className="-mt-7 flex size-11 shrink-0 items-center justify-center rounded-2xl text-white sm:-mt-8 sm:size-14"
        >
          <Icon name={icon} className="size-5 sm:size-6" />
        </span>

        <span className="min-w-0 max-w-full text-left sm:text-right">
          <span className="block truncate text-[0.68rem] leading-tight text-subtle sm:text-xs">
            {label}
          </span>
          <span className="tabular mt-0.5 block truncate text-xl font-semibold leading-tight text-ink sm:text-[1.65rem]">
            {value}
          </span>
          {/* L'unité s'enroule plutôt que de se couper : « de ce qui r… » ne
              dit plus de quoi la marge est la part. */}
          {unit && (
            <span className="block text-[0.62rem] leading-tight text-subtle sm:text-[0.7rem]">
              {unit}
            </span>
          )}
        </span>
      </div>

      <div className="mt-2.5 border-t border-line pt-2 sm:mt-3 sm:pt-2.5">
        {evolution ? (
          <EvolutionLine {...evolution} />
        ) : (
          <p className="truncate text-[0.68rem] text-subtle sm:text-xs">
            {note ?? "—"}
          </p>
        )}
      </div>
    </div>
  );
}

/**
 * « +12 % vs les 30 jours précédents ».
 *
 * La flèche double la couleur : elle porte le sens à elle seule, et elle
 * survit au thème sombre comme à l'impression en noir et blanc.
 */
function EvolutionLine({ percent, against, good, unit = "%" }: Evolution) {
  if (percent === null) {
    return (
      <p className="truncate text-[0.68rem] text-subtle sm:text-xs">
        Rien à comparer sur {against}
      </p>
    );
  }

  const rising = percent > 0;
  const flat = Math.abs(percent) < 0.05;
  const welcome = flat ? null : rising === (good === "up");

  return (
    // Le repli plutôt que la coupure : « vs les 12 mois d'a… » ne dit plus à
    // quoi on compare, et une évolution sans période de référence n'est pas
    // un chiffre. Sur une carte large la ligne tient d'un seul tenant ; sur
    // un téléphone elle passe à la ligne et la carte grandit d'une ligne.
    <p className="flex flex-wrap items-baseline gap-x-1 text-[0.68rem] leading-tight text-subtle sm:text-xs">
      <span
        className={`shrink-0 font-semibold ${
          welcome === null
            ? "text-muted"
            : welcome
              ? "text-emerald-600 dark:text-emerald-400"
              : "text-danger"
        }`}
      >
        <span aria-hidden>{flat ? "=" : rising ? "↑" : "↓"}</span>{" "}
        {flat
          ? "stable"
          : `${rising ? "+" : "−"}${Math.abs(percent).toLocaleString("fr-FR", {
              maximumFractionDigits: 1,
            })} ${unit}`}
      </span>
      <span>vs {against}</span>
    </p>
  );
}

/* --------------------------------------------------------------------------
 * Carte à panneau de couleur
 * ---------------------------------------------------------------------- */

export function ChartCard({
  tone,
  title,
  subtitle,
  foot,
  children,
}: {
  tone: Tone;
  title: string;
  subtitle: ReactNode;
  foot: string;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col rounded-2xl border border-line bg-surface p-3 shadow-card sm:p-4">
      {/*
        Le panneau remonte hors de la carte, comme la pastille des chiffres :
        les deux rangées se répondent, et le graphique se lit comme une
        vignette posée plutôt qu'un encadré de plus.
      */}
      <div
        style={toneStyle(tone, 22)}
        className="-mt-7 rounded-2xl px-2 pb-1.5 pt-3 sm:-mt-8 sm:px-3 sm:pb-2 sm:pt-4"
      >
        {children}
      </div>

      <h3 className="mt-3.5 text-[0.95rem] font-semibold text-ink sm:mt-4">
        {title}
      </h3>
      <p className="mt-1 text-xs leading-relaxed text-muted">{subtitle}</p>

      <div className="mt-auto flex items-center gap-1.5 border-t border-line pt-2.5 text-[0.7rem] text-subtle">
        <Icon name="clock" className="size-3.5 shrink-0" />
        <span className="truncate">{foot}</span>
      </div>
    </div>
  );
}

/* --------------------------------------------------------------------------
 * Les deux figures qui vivent dans un panneau de couleur
 * ---------------------------------------------------------------------- */

export interface Point {
  label: string;
  value: number;
  /** Texte lu par le lecteur d'écran et montré au survol. */
  title: string;
}

const W = 340;
const H = 148;
const PAD = { top: 12, right: 8, bottom: 22, left: 8 };
const PLOT_W = W - PAD.left - PAD.right;
const PLOT_H = H - PAD.top - PAD.bottom;

/** Trois filets horizontaux, pas plus : sur un panneau coloré, une grille
 *  complète se bat avec la courbe qu'elle sert à lire. */
function Grid() {
  return (
    <>
      {[0, 0.5, 1].map((ratio) => (
        <line
          key={ratio}
          x1={PAD.left}
          x2={W - PAD.right}
          y1={PAD.top + PLOT_H * ratio}
          y2={PAD.top + PLOT_H * ratio}
          stroke="rgb(255 255 255 / 0.22)"
          strokeWidth={1}
        />
      ))}
    </>
  );
}

function Labels({ points }: { points: Point[] }) {
  // Un mois sur deux dès qu'il y en a plus de sept : douze abréviations sur
  // 340 unités se chevauchent, et deux étiquettes qui se touchent ne se
  // lisent ni l'une ni l'autre.
  const step = points.length > 7 ? 2 : 1;
  const slot = PLOT_W / Math.max(points.length, 1);

  return (
    <>
      {points.map((point, index) =>
        index % step === 0 ? (
          <text
            key={point.label + index}
            x={PAD.left + slot * index + slot / 2}
            y={H - 6}
            textAnchor="middle"
            fontSize={9}
            fill="rgb(255 255 255 / 0.7)"
          >
            {point.label}
          </text>
        ) : null,
      )}
    </>
  );
}

export function GradientBars({
  points,
  caption,
}: {
  points: Point[];
  caption: string;
}) {
  const titleId = useId();
  const max = Math.max(...points.map((point) => point.value), 1);
  const slot = PLOT_W / Math.max(points.length, 1);
  const barW = Math.max(3, Math.min(14, slot * 0.42));

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      // Hauteur laissée au `viewBox` : en la forçant, `meet` centrerait le
      // dessin dans une boîte plus large, et `none` étirerait les étiquettes
      // de mois à l'horizontale. Le rapport 340×148 tombe déjà juste à la
      // largeur d'une carte, sur téléphone comme sur trois colonnes.
      className="block h-auto w-full"
      role="img"
      aria-labelledby={titleId}
    >
      <title id={titleId}>{caption}</title>
      <Grid />

      {points.map((point, index) => {
        const height = (point.value / max) * PLOT_H;
        return (
          <rect
            key={point.label + index}
            x={PAD.left + slot * index + slot / 2 - barW / 2}
            y={PAD.top + PLOT_H - height}
            width={barW}
            // Une hauteur nulle ne dessine rien du tout : 2 unités de socle
            // disent « ce mois existe et vaut zéro », le vide dit « ce mois
            // manque ».
            height={Math.max(height, 2)}
            rx={2}
            fill="rgb(255 255 255 / 0.92)"
          >
            <title>{point.title}</title>
          </rect>
        );
      })}

      <Labels points={points} />
    </svg>
  );
}

export function GradientLine({
  points,
  caption,
}: {
  points: Point[];
  caption: string;
}) {
  const titleId = useId();
  const values = points.map((point) => point.value);
  const max = Math.max(...values, 0);
  const min = Math.min(...values, 0);
  const span = max - min || 1;

  const slot = PLOT_W / Math.max(points.length, 1);
  const x = (index: number) => PAD.left + slot * index + slot / 2;
  const y = (value: number) =>
    PAD.top + PLOT_H - ((value - min) / span) * PLOT_H;

  const line = values.map((value, index) => `${x(index)},${y(value)}`).join(" ");

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="block h-auto w-full"
      role="img"
      aria-labelledby={titleId}
    >
      <title id={titleId}>{caption}</title>
      <Grid />

      {/* La ligne du zéro n'est tracée que si elle traverse le graphique :
          en la forçant, une série entièrement positive gagnerait un trait
          collé à son bord bas, qu'on prendrait pour un axe. */}
      {min < 0 && max > 0 && (
        <line
          x1={PAD.left}
          x2={W - PAD.right}
          y1={y(0)}
          y2={y(0)}
          stroke="rgb(255 255 255 / 0.55)"
          strokeWidth={1}
          strokeDasharray="3 3"
        />
      )}

      <polyline
        points={line}
        fill="none"
        stroke="rgb(255 255 255 / 0.95)"
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />

      {points.map((point, index) => (
        <circle
          key={point.label + index}
          cx={x(index)}
          cy={y(point.value)}
          r={2.8}
          fill="#fff"
        >
          <title>{point.title}</title>
        </circle>
      ))}

      <Labels points={points} />
    </svg>
  );
}

/* --------------------------------------------------------------------------
 * Le tableau à barres
 * ---------------------------------------------------------------------- */

export interface ShareRow {
  key: string;
  icon: IconName;
  tone: Tone;
  label: string;
  amount: string;
  /** Part du total, de 0 à 100. */
  share: number;
}

export function ShareTable({
  rows,
  empty,
}: {
  rows: ShareRow[];
  empty: string;
}) {
  if (rows.length === 0) {
    return <p className="px-1 py-6 text-sm text-muted">{empty}</p>;
  }

  return (
    // Un vrai tableau : ce sont des données tabulaires, et un lecteur
    // d'écran doit pouvoir annoncer « Loyer, 120 000, 34 % ».
    <table className="w-full border-collapse">
      <thead>
        <tr className="border-b border-line text-left">
          <th className="pb-2 pr-2 text-[0.62rem] font-semibold uppercase tracking-[0.1em] text-subtle">
            Poste
          </th>
          <th className="pb-2 pl-2 text-right text-[0.62rem] font-semibold uppercase tracking-[0.1em] text-subtle">
            Montant
          </th>
          <th className="hidden w-[38%] pb-2 pl-4 text-[0.62rem] font-semibold uppercase tracking-[0.1em] text-subtle sm:table-cell">
            Part
          </th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.key} className="border-b border-line last:border-0">
            <td className="py-2.5 pr-2 align-middle">
              <span className="flex items-center gap-2.5">
                <span
                  aria-hidden
                  style={{ backgroundImage: GRADIENTS[row.tone] }}
                  className="flex size-7 shrink-0 items-center justify-center rounded-lg text-white"
                >
                  <Icon name={row.icon} className="size-3.5" />
                </span>
                <span className="min-w-0">
                  <span className="block truncate text-sm font-medium text-ink">
                    {row.label}
                  </span>
                  {/* Sous le téléphone la colonne « Part » disparaît : la
                      barre passe alors sous le libellé plutôt que de
                      comprimer trois colonnes sur 320 pixels. */}
                  <span className="mt-1 block sm:hidden">
                    <Bar share={row.share} />
                  </span>
                </span>
              </span>
            </td>

            <td className="tabular py-2.5 pl-2 text-right align-middle text-sm font-semibold text-ink">
              {row.amount}
            </td>

            <td className="hidden py-2.5 pl-4 align-middle sm:table-cell">
              <Bar share={row.share} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Bar({ share }: { share: number }) {
  const width = Math.max(Math.min(share, 100), 1.5);
  return (
    <span className="flex items-center gap-2">
      <span
        aria-hidden
        className="h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-surface-muted"
      >
        <span
          className="salon-gradient block h-full rounded-full transition-[width] duration-700"
          style={{ width: `${width}%` }}
        />
      </span>
      <span className="tabular w-9 shrink-0 text-right text-[0.7rem] text-subtle">
        {share.toLocaleString("fr-FR", { maximumFractionDigits: 0 })} %
      </span>
    </span>
  );
}

/* --------------------------------------------------------------------------
 * Le fil des derniers mouvements
 * ---------------------------------------------------------------------- */

export interface FeedItem {
  id: string;
  icon: IconName;
  tone: Tone;
  title: string;
  meta: string;
  amount: string;
  /** Recette : le montant se met en vert, et il porte déjà son signe. */
  income: boolean;
  badge?: string;
}

export function Feed({ items, empty }: { items: FeedItem[]; empty: string }) {
  if (items.length === 0) {
    return <p className="px-1 py-6 text-sm text-muted">{empty}</p>;
  }

  return (
    <ol className="relative space-y-4">
      {items.map((item, index) => (
        <li key={item.id} className="relative flex gap-3">
          {/* Le fil ne descend pas sous le dernier point : un trait qui
              continue dans le vide laisse croire qu'il manque une ligne. */}
          {index < items.length - 1 && (
            <span
              aria-hidden
              className="absolute bottom-[-1rem] left-[0.84rem] top-8 w-px bg-line-strong"
            />
          )}

          <span
            aria-hidden
            style={{ backgroundImage: GRADIENTS[item.tone] }}
            className="relative z-10 flex size-7 shrink-0 items-center justify-center rounded-lg text-white"
          >
            <Icon name={item.icon} className="size-3.5" />
          </span>

          <span className="min-w-0 flex-1">
            <span className="flex items-baseline justify-between gap-2">
              <span className="min-w-0 truncate text-sm font-medium text-ink">
                {item.title}
              </span>
              <span
                className={`tabular shrink-0 text-sm font-semibold ${
                  item.income
                    ? "text-emerald-600 dark:text-emerald-400"
                    : "text-ink"
                }`}
              >
                {item.amount}
              </span>
            </span>
            <span className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1">
              <span className="text-xs text-subtle">{item.meta}</span>
              {item.badge && (
                <span className="rounded-full bg-surface-muted px-1.5 py-px text-[0.62rem] text-muted">
                  {item.badge}
                </span>
              )}
            </span>
          </span>
        </li>
      ))}
    </ol>
  );
}

/* --------------------------------------------------------------------------
 * Enveloppe commune
 * ---------------------------------------------------------------------- */

/**
 * Carte de section : titre, sous-titre, contenu.
 *
 * Distincte de `Card` du kit produit parce que son en-tête porte ici deux
 * lignes — un titre et le compte de ce qu'il résume — et que cet en-tête
 * revient à l'identique sur le tableau, le fil et l'anneau.
 */
export function BoardCard({
  title,
  lead,
  action,
  children,
  className = "",
}: {
  title: string;
  lead?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`flex flex-col rounded-2xl border border-line bg-surface p-4 shadow-card sm:p-5 ${className}`}
    >
      <header className="mb-3 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-[1.05rem] font-semibold tracking-tight text-ink">
            {title}
          </h2>
          {lead && (
            <p className="mt-0.5 flex items-center gap-1.5 text-xs text-muted">
              {lead}
            </p>
          )}
        </div>
        {action}
      </header>
      {children}
    </section>
  );
}
