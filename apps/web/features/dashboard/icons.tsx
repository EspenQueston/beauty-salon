/**
 * Icônes de navigation.
 *
 * Dessinées à la main plutôt qu'importées d'une librairie : neuf traits ne
 * justifient pas une dépendance de plusieurs centaines de kilo-octets sur des
 * réseaux mobiles facturés à la donnée.
 */

import type { ReactNode } from "react";

export type IconName =
  | "bag"
  | "calendar"
  | "users"
  | "sparkles"
  | "scissors"
  | "clock"
  | "image"
  | "team"
  | "store"
  | "receipt"
  | "external"
  | "menu"
  | "plus"
  | "check"
  | "star"
  | "chevron-left"
  | "chevron-right"
  | "grid"
  | "bell"
  | "trend"
  | "wallet"
  | "logout"
  | "search"
  | "panel"
  | "edit"
  // Postes de dépense, lisibles d'un coup d'œil dans le tableau des comptes.
  | "percent"
  | "truck"
  | "megaphone"
  | "tool"
  | "bolt"
  | "eye"
  | "sliders"
  | "close"
  | "scan";

const PATHS: Record<IconName, ReactNode> = {
  edit: (
    <>
      <path d="M4 20h4L19 9a2.1 2.1 0 0 0-3-3L5 17z" />
      <path d="M14.5 7.5 16.5 9.5" />
    </>
  ),
  search: (
    <>
      <circle cx="11" cy="11" r="6.5" />
      <path d="m16 16 4.5 4.5" />
    </>
  ),
  panel: (
    <>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M9.5 4v16" />
    </>
  ),
  grid: (
    <>
      <rect x="3" y="3" width="7.5" height="7.5" rx="1.6" />
      <rect x="13.5" y="3" width="7.5" height="7.5" rx="1.6" />
      <rect x="3" y="13.5" width="7.5" height="7.5" rx="1.6" />
      <rect x="13.5" y="13.5" width="7.5" height="7.5" rx="1.6" />
    </>
  ),
  bell: (
    <>
      <path d="M18 16V11a6 6 0 1 0-12 0v5l-1.6 2.4h15.2z" />
      <path d="M10 21a2.2 2.2 0 0 0 4 0" />
    </>
  ),
  trend: (
    <>
      <path d="M3.5 16.5 9 11l3.5 3.5L20.5 6" />
      <path d="M15.5 6h5v5" />
    </>
  ),
  wallet: (
    <>
      <rect x="3" y="6" width="18" height="13" rx="2.4" />
      <path d="M3 10h18" />
      <circle cx="16.5" cy="14.5" r="1.2" />
    </>
  ),
  logout: (
    <>
      <path d="M14 4.5H6.5A1.5 1.5 0 0 0 5 6v12a1.5 1.5 0 0 0 1.5 1.5H14" />
      <path d="M17 8.5 20.5 12 17 15.5M20 12H10" />
    </>
  ),
  calendar: (
    <>
      <rect x="3" y="5" width="18" height="16" rx="2" />
      <path d="M3 10h18M8 3v4M16 3v4" />
    </>
  ),
  users: (
    <>
      <circle cx="9" cy="8" r="3.2" />
      <path d="M3.5 20a5.5 5.5 0 0 1 11 0" />
      <path d="M16 5.2a3.2 3.2 0 0 1 0 5.6M17.5 14.4A5.5 5.5 0 0 1 20.5 20" />
    </>
  ),
  sparkles: (
    <>
      <path d="M12 3.5 13.7 8.3 18.5 10 13.7 11.7 12 16.5 10.3 11.7 5.5 10 10.3 8.3z" />
      <path d="M18 16.5l.7 1.8 1.8.7-1.8.7-.7 1.8-.7-1.8-1.8-.7 1.8-.7z" />
    </>
  ),
  scissors: (
    <>
      <circle cx="6" cy="6" r="2.6" />
      <circle cx="6" cy="18" r="2.6" />
      <path d="M8.2 7.6 20 18M20 6 8.2 16.4" />
    </>
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5.2l3.2 1.9" />
    </>
  ),
  image: (
    <>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <circle cx="8.5" cy="9.5" r="1.6" />
      <path d="m4 17 4.5-4.5a2 2 0 0 1 2.8 0L20 21" />
    </>
  ),
  team: (
    <>
      <circle cx="12" cy="7" r="3.2" />
      <path d="M5.5 20a6.5 6.5 0 0 1 13 0" />
    </>
  ),
  // Un sac, pas une devanture : la boutique vend des articles, elle ne
  // represente pas le salon lui-meme - c'est `store` qui porte cela.
  bag: (
    <>
      <path d="M5 8h14l-1 12H6z" />
      <path d="M9 8V6a3 3 0 0 1 6 0v2" />
    </>
  ),
  store: (
    <>
      <path d="M4 9.5V20h16V9.5" />
      <path d="M3 9.5 5 4h14l2 5.5a3 3 0 0 1-6 0 3 3 0 0 1-6 0 3 3 0 0 1-6 0z" />
      <path d="M10 20v-5h4v5" />
    </>
  ),
  receipt: (
    <>
      <path d="M6 3h12v18l-3-1.8-3 1.8-3-1.8L6 21z" />
      <path d="M9.5 8.5h5M9.5 12.5h5" />
    </>
  ),
  external: (
    <>
      <path d="M14 4h6v6" />
      <path d="M20 4 11 13" />
      <path d="M18 14v5a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 4 19V8a1.5 1.5 0 0 1 1.5-1.5H10" />
    </>
  ),
  menu: <path d="M4 7h16M4 12h16M4 17h16" />,
  "chevron-left": <path d="m14.5 5-7 7 7 7" />,
  "chevron-right": <path d="m9.5 5 7 7-7 7" />,
  plus: <path d="M12 5v14M5 12h14" />,
  check: <path d="M20 6 9 17l-5-5" />,
  star: (
    <path d="m12 4 2.4 5.1 5.6.7-4.1 3.9 1.1 5.5L12 16.6 6.9 19.2 8 13.7 3.9 9.8l5.6-.7z" />
  ),
  percent: (
    <>
      <path d="M19 5 5 19" />
      <circle cx="7.5" cy="7.5" r="2.5" />
      <circle cx="16.5" cy="16.5" r="2.5" />
    </>
  ),
  truck: (
    <>
      <path d="M3 7.5h10.5v8H3zM13.5 10.5H17l3 3v2h-6.5z" />
      <circle cx="7" cy="17.5" r="1.8" />
      <circle cx="16.5" cy="17.5" r="1.8" />
    </>
  ),
  megaphone: (
    <>
      <path d="M4 10.5v3a1.5 1.5 0 0 0 1.5 1.5H8l7 4V5L8 9H5.5A1.5 1.5 0 0 0 4 10.5z" />
      <path d="M18.5 9.5a3.5 3.5 0 0 1 0 5" />
    </>
  ),
  tool: (
    <>
      <path d="M14.5 3.5a4.5 4.5 0 0 0-5.6 5.8L3.7 14.5a2 2 0 0 0 2.8 2.8l5.2-5.2a4.5 4.5 0 0 0 5.8-5.6l-2.6 2.6-2.4-.6-.6-2.4z" />
      <path d="m15 15 5 5" />
    </>
  ),
  bolt: <path d="M13.5 3 5.5 13.5h5L10 21l8.5-10.5h-5z" />,
  eye: (
    <>
      <path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z" />
      <circle cx="12" cy="12" r="3" />
    </>
  ),
  sliders: (
    <>
      <path d="M5 4v6M5 14v6M12 4v3M12 11v9M19 4v9M19 17v3" />
      <path d="M3 12h4M10 9h4M17 15h4" />
    </>
  ),
  close: <path d="M6 6 18 18M18 6 6 18" />,
  // Les quatre coins d'une mire, et le trait du lecteur : c'est le geste de
  // viser, pas l'objet visé — un QR dessiné serait illisible à 16 pixels.
  scan: (
    <>
      <path d="M4 8.5V6a2 2 0 0 1 2-2h2.5M15.5 4H18a2 2 0 0 1 2 2v2.5M20 15.5V18a2 2 0 0 1-2 2h-2.5M8.5 20H6a2 2 0 0 1-2-2v-2.5" />
      <path d="M3.5 12h17" />
    </>
  ),
};

export function Icon({
  name,
  className = "size-5",
}: {
  name: IconName;
  className?: string;
}) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      className={className}
    >
      {PATHS[name]}
    </svg>
  );
}
