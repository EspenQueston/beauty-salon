/**
 * Normalisation d'une adresse de mini-site.
 *
 * Elle vit à un seul endroit parce que trois écrans la calculent — la
 * vérification du haut de page, l'aperçu, et le formulaire d'inscription — et
 * qu'une divergence entre eux se verrait au pire moment : l'adresse annoncée
 * libre ne serait pas celle réellement demandée au serveur.
 *
 * Les règles sont celles du backend : minuscules, sans accent, tirets, et
 * jamais de tiret en bordure.
 */

export const SLUG_MAX = 40;

/** Longueur en dessous de laquelle on ne consulte pas le serveur. */
export const SLUG_MIN = 3;

export function toSlug(value: string): string {
  return value
    .toLowerCase()
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, SLUG_MAX);
}
