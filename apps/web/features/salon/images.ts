/**
 * Des photos à la taille de l'écran.
 *
 * Une vignette de 170 pixels téléchargeait l'original du salon — jusqu'à
 * 1600 × 2400, plusieurs centaines de kilo-octets par photo. Sur un
 * téléphone en 3G, facturé à la donnée, c'était l'essentiel du poids de la
 * page et la raison de sa lenteur.
 *
 * L'API publie, pour chaque photo, des copies WebP réduites (`variants`,
 * indexées par largeur). On en tire un `srcset` : le navigateur choisit la
 * plus petite qui suffit à l'emplacement (`sizes`) et à la densité de
 * l'écran. L'original reste la dernière option, pour les grands écrans.
 */

import { illustrationUrl } from "@/lib/illustrations";

interface Source {
  url: string;
  width?: number | null;
  variants?: Record<string, string>;
}

/** Le `srcset` d'une photo du salon, ou `undefined` sans copie réduite. */
export function srcSetDe(asset: Source): string | undefined {
  const entrees = Object.entries(asset.variants ?? {})
    .map(([largeur, url]) => [Number(largeur), url] as const)
    .filter(([largeur]) => Number.isFinite(largeur) && largeur > 0)
    .sort(([a], [b]) => a - b)
    .map(([largeur, url]) => `${url} ${largeur}w`);
  if (entrees.length === 0) return undefined;
  if (asset.width) entrees.push(`${asset.url} ${asset.width}w`);
  return entrees.join(", ");
}

/** Les attributs d'un `<img>` : `src`, et `srcSet` + `sizes` quand il y en a. */
export function photo(asset: Source, sizes: string) {
  const srcSet = srcSetDe(asset);
  return srcSet ? { src: asset.url, srcSet, sizes } : { src: asset.url };
}

/** Le `srcset` d'une illustration d'ambiance, aux mêmes proportions. */
export function srcSetIllustration(id: string, ratio?: number): string {
  return [640, 1024, 1600]
    .map((largeur) => `${illustrationUrl(id, { width: largeur, ratio })} ${largeur}w`)
    .join(", ");
}

/** Emplacements courants, pour que `sizes` dise la vérité au navigateur. */
export const TAILLES = {
  pleineLargeur: "100vw",
  // Deux colonnes sur téléphone, trois à quatre ensuite.
  grille: "(min-width: 1024px) 25vw, (min-width: 640px) 33vw, 50vw",
  cartes: "(min-width: 1024px) 33vw, 50vw",
  moitie: "(min-width: 1024px) 50vw, 100vw",
  vignette: "160px",
  pastille: "64px",
} as const;
