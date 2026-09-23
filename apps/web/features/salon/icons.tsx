/**
 * Pictogrammes du mini-site.
 *
 * Dessinés à la main plutôt qu'importés : le mini-site s'ouvre depuis un
 * lien WhatsApp sur un téléphone d'entrée de gamme, souvent sur un forfait
 * facturé à la donnée. Une bibliothèque d'icônes coûterait plus cher que
 * tout le contenu de la page.
 *
 * Le vocabulaire est celui du métier — ciseaux, vernis, peigne, séchoir —
 * parce qu'une cliente reconnaît un service à sa silhouette avant d'en lire
 * le nom.
 */

import type { ReactNode } from "react";

export type SalonIconName =
  | "scissors"
  | "polish"
  | "dryer"
  | "comb"
  | "sparkle"
  | "lipstick"
  | "razor"
  | "clock"
  | "pin"
  | "home"
  | "phone"
  | "whatsapp"
  | "instagram"
  | "tiktok"
  | "facebook"
  | "wechat"
  | "calendar"
  | "arrow"
  | "play"
  | "close"
  | "menu"
  | "check"
  | "star"
  | "sun"
  | "moon"
  | "user"
  | "store"
  | "echange"
  | "globe";

const PATHS: Record<SalonIconName, ReactNode> = {
  user: (
    <>
      <circle cx="12" cy="8" r="3.6" />
      <path d="M4.8 20.2a7.6 7.6 0 0 1 14.4 0" />
    </>
  ),
  store: (
    <>
      <path d="M4 9.5V20h16V9.5" />
      <path d="M3 9.5 5 4h14l2 5.5a3 3 0 0 1-5.6 1.4 3 3 0 0 1-5.4 0A3 3 0 0 1 3 9.5z" />
    </>
  ),
  scissors: (
    <>
      <circle cx="6" cy="6.5" r="2.4" />
      <circle cx="6" cy="17.5" r="2.4" />
      <path d="M8.1 7.9 20 17.5M20 6.5 8.1 16.1" />
    </>
  ),
  polish: (
    <>
      <path d="M9.5 8h5v11a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2z" />
      <path d="M10.5 8V4.8a1 1 0 0 1 1-1h1a1 1 0 0 1 1 1V8" />
      <path d="M9.5 12.5h5" />
    </>
  ),
  dryer: (
    <>
      <path d="M4 9.5a4.5 4.5 0 0 1 4.5-4.5h5.8a3.2 3.2 0 0 1 0 9H8.5A4.5 4.5 0 0 1 4 9.5z" />
      <path d="M9 14v4.5a2 2 0 0 0 2 2h.6" />
      <path d="M17.5 9.5h3" />
    </>
  ),
  comb: (
    <>
      <path d="M4 6.5h16" />
      <path d="M6.5 6.5v6M10 6.5v9M13.5 6.5v6M17 6.5v9" />
    </>
  ),
  sparkle: (
    <>
      <path d="M12 3.5 13.7 8.3 18.5 10 13.7 11.7 12 16.5 10.3 11.7 5.5 10 10.3 8.3z" />
      <path d="M18 16.6l.65 1.75 1.75.65-1.75.65L18 21.4l-.65-1.75-1.75-.65 1.75-.65z" />
    </>
  ),
  lipstick: (
    <>
      <path d="M9 11h6v9.5a.5.5 0 0 1-.5.5h-5a.5.5 0 0 1-.5-.5z" />
      <path d="M10 11V6.2c0-1.2 1-2.2 2.2-2.2h.6c.7 0 1.2.6 1.2 1.3V11" />
    </>
  ),
  razor: (
    <>
      <rect x="5" y="3.5" width="14" height="4.5" rx="1.4" />
      <path d="M12 8v4" />
      <rect x="9.5" y="12" width="5" height="8.5" rx="1.4" />
    </>
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="8.6" />
      <path d="M12 7.2V12l3.2 1.9" />
    </>
  ),
  pin: (
    <>
      <path d="M12 21s6.5-5.6 6.5-10.2A6.5 6.5 0 0 0 5.5 10.8C5.5 15.4 12 21 12 21z" />
      <circle cx="12" cy="10.6" r="2.4" />
    </>
  ),
  home: (
    <>
      <path d="M3.6 10.4 12 3.6l8.4 6.8" />
      <path d="M5.6 9v10.2a1 1 0 0 0 1 1h10.8a1 1 0 0 0 1-1V9" />
      <path d="M9.9 20.2v-5.4h4.2v5.4" />
    </>
  ),
  phone: (
    <path d="M6.2 3.8h3l1.4 3.6-2 1.3a11.4 11.4 0 0 0 5.4 5.4l1.3-2 3.6 1.4v3a1.8 1.8 0 0 1-2 1.8A15.6 15.6 0 0 1 4.4 5.8a1.8 1.8 0 0 1 1.8-2z" />
  ),
  whatsapp: (
    <>
      <path
        fillRule="evenodd"
        clipRule="evenodd"
        d="M12.04 2.5a9.44 9.44 0 0 0-8.09 14.28L2.5 21.5l4.85-1.4A9.44 9.44 0 1 0 12.04 2.5m0 1.72a7.72 7.72 0 0 1 0 15.44 7.7 7.7 0 0 1-3.93-1.08l-.28-.17-2.88.83.85-2.8-.18-.29a7.72 7.72 0 0 1 6.42-11.93"
      />
      <path d="M9.4 7.6c-.2-.44-.4-.45-.58-.46h-.5c-.17 0-.45.06-.69.32s-.9.88-.9 2.15.93 2.5 1.06 2.67 1.79 2.87 4.42 3.9c2.19.87 2.63.7 3.11.65s1.54-.63 1.76-1.24.22-1.13.15-1.24-.24-.17-.5-.3-1.54-.76-1.78-.85-.41-.13-.59.13-.67.85-.82 1.02-.3.2-.56.07-1.1-.4-2.09-1.29c-.77-.69-1.3-1.54-1.45-1.8s-.02-.4.11-.53.26-.3.39-.46.17-.26.26-.43.04-.33-.02-.46-.58-1.4-.8-1.92" />
    </>
  ),
  instagram: (
    <>
      <rect x="3.5" y="3.5" width="17" height="17" rx="5" />
      <circle cx="12" cy="12" r="4" />
      <path d="M17 7h.01" />
    </>
  ),
  tiktok: (
    <path d="M16.5 2.5h-2.85v13.32a2.36 2.36 0 1 1-2.36-2.36c.22 0 .43.03.63.09v-2.93a5.4 5.4 0 0 0-.63-.04 5.29 5.29 0 1 0 5.29 5.29V9.35a6.5 6.5 0 0 0 3.82 1.23V7.65a3.72 3.72 0 0 1-3.9-3.62z" />
  ),
  facebook: (
    <path d="M14.6 21v-7.5h2.6l.4-3h-3V8.6c0-.9.3-1.5 1.5-1.5H17.7V4.4A19 19 0 0 0 15.4 4.3c-2.3 0-3.9 1.4-3.9 4v2.2H9v3h2.5V21z" />
  ),
  wechat: (
    <>
      <path d="M9 4.5c3.4 0 6.2 2.2 6.2 4.9S12.4 14.3 9 14.3a8 8 0 0 1-2-.25L4.2 15.2l.75-2.1A5.3 5.3 0 0 1 2.8 9.4C2.8 6.7 5.6 4.5 9 4.5z" />
      <path d="M15.6 9.7c3 0 5.6 2 5.6 4.4a4.7 4.7 0 0 1-1.9 3.5l.6 1.9-2.4-1a7.1 7.1 0 0 1-1.9.25c-3.1 0-5.6-2-5.6-4.4" />
    </>
  ),
  calendar: (
    <>
      <rect x="3.5" y="5" width="17" height="15.5" rx="3" />
      <path d="M3.5 10h17M8 3.2v3.6M16 3.2v3.6" />
    </>
  ),
  arrow: <path d="M5 12h13M13 6.5l5.5 5.5L13 17.5" />,
  play: <path d="M9 6.8v10.4l8.4-5.2z" />,
  close: <path d="m6.5 6.5 11 11M17.5 6.5l-11 11" />,
  menu: <path d="M4 7.5h16M4 12h16M4 16.5h16" />,
  check: <path d="m20 6.5-10.6 11L4 12" />,
  star: (
    <path d="m12 4 2.4 5.1 5.6.7-4.1 3.9 1.1 5.5L12 16.6 6.9 19.2 8 13.7 3.9 9.8l5.6-.7z" />
  ),
  sun: (
    <>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M18.4 5.6L17 7M7 17l-1.4 1.4" />
    </>
  ),
  moon: <path d="M20 14.5A8.2 8.2 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z" />,

  /*
    Deux flèches opposées : « convertis ceci en cela ».

    Le bouton de devise portait une étincelle, qui ne dit ni argent, ni
    change, ni menu — et qui sert partout ailleurs à marquer un soin. Une
    pièce aurait dit « de l'argent » : juste, et inerte. Ce bouton ne
    montre pas une monnaie, il en substitue une à une autre le temps
    d'une lecture ; c'est un geste, pas une matière.

    Deux traits seulement, et des pointes ouvertes : à 14 px une tête de
    flèche pleine se remplit et la flèche devient un pâté.
  */
  echange: (
    <>
      <path d="M4.5 9.2h13.2M14.4 5.9l3.3 3.3-3.3 3.3" />
      <path d="M19.5 14.8H6.3M9.6 11.5l-3.3 3.3 3.3 3.3" />
    </>
  ),

  /* Le méridien courbe, et non trois traits droits : à cette taille un
     globe quadrillé se lit comme un tableur. */
  globe: (
    <>
      <circle cx="12" cy="12" r="8.2" />
      <path d="M3.8 12h16.4M12 3.8c2.2 2.3 3.3 5.1 3.3 8.2S14.2 17.9 12 20.2c-2.2-2.3-3.3-5.1-3.3-8.2S9.8 6.1 12 3.8z" />
    </>
  ),
};

/**
 * Marques dessinees comme des aplats, jamais comme des contours.
 *
 * Les logos de reseaux sont concus pleins : le combine de WhatsApp trace au
 * trait donnait une tache illisible a 16 px, parce qu'on voyait le contour
 * d'une forme qui n'a de sens que remplie. Le reste du jeu d'icones reste au
 * trait, qui s'accorde a la typographie.
 */
const SOLID = new Set<SalonIconName>(["whatsapp", "tiktok", "facebook"]);

export function SalonIcon({
  name,
  className = "size-5",
  filled = false,
}: {
  name: SalonIconName;
  className?: string;
  filled?: boolean;
}) {
  const solid = filled || SOLID.has(name);

  return (
    <svg
      viewBox="0 0 24 24"
      fill={solid ? "currentColor" : "none"}
      stroke={solid ? "none" : "currentColor"}
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      className={className}
    >
      {PATHS[name]}
    </svg>
  );
}

/**
 * Icône déduite du nom de la catégorie.
 *
 * Un salon nomme ses catégories librement ; on reconnaît les familles les
 * plus courantes et on retombe sur l'étincelle sinon. Aucune icône n'est
 * jamais fausse au point de tromper — au pire elle est neutre.
 */
export function categoryIcon(name: string): SalonIconName {
  const key = name
    .toLowerCase()
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "");

  if (/ongle|nail|manucure|pedicure|vernis|gel/.test(key)) return "polish";
  if (/tresse|natte|braid|locks|twist|vanille/.test(key)) return "comb";
  if (/perruque|tissage|wig|extension|meche/.test(key)) return "dryer";
  if (/coupe|coiffure|barbe|barbier|rasage/.test(key)) return "scissors";
  if (/maquillage|makeup|levre|teint|sourcil|cil/.test(key)) return "lipstick";
  if (/soin|masque|traitement|hydrat|defris|lissage/.test(key))
    return "sparkle";
  if (/epilation|cire|wax/.test(key)) return "razor";
  return "sparkle";
}
