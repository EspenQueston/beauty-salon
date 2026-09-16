/**
 * Pays le plus probable, déduit du fuseau horaire du navigateur.
 *
 * Le formulaire d'inscription proposait toujours le Congo-Brazzaville. C'est
 * juste pour une partie des salons visés, et faux pour toutes les autres :
 * une coiffeuse à Guangzhou devait corriger le pays, donc le fuseau et la
 * devise, avant même d'avoir tapé son nom.
 *
 * Le fuseau du navigateur est une meilleure supposition qu'une constante, et
 * il ne demande aucune permission — contrairement à la géolocalisation, qui
 * ouvrirait une boîte de dialogue pour un champ modifiable en un clic.
 *
 * Ça reste une **proposition** : le champ est visible, modifiable, et son
 * effet est écrit en clair sous lui. Une valeur par défaut qui se cache est
 * un piège ; une valeur par défaut qui s'annonce est un service.
 */

export type CountryCode = "CG" | "CD" | "CN";

const BY_TIMEZONE: Record<string, CountryCode> = {
  "Africa/Brazzaville": "CG",
  "Africa/Kinshasa": "CD",
  "Africa/Lubumbashi": "CD",
  "Asia/Shanghai": "CN",
  "Asia/Chongqing": "CN",
  "Asia/Harbin": "CN",
  "Asia/Urumqi": "CN",
  "Asia/Macau": "CN",
  "Asia/Hong_Kong": "CN",
};

export const DEFAULT_COUNTRY: CountryCode = "CG";

export function guessCountry(): CountryCode {
  if (typeof Intl === "undefined") return DEFAULT_COUNTRY;

  try {
    const zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    if (zone && BY_TIMEZONE[zone]) return BY_TIMEZONE[zone];

    // Repli par région : un fuseau chinois non listé reste la Chine.
    if (zone?.startsWith("Asia/")) return "CN";
    if (zone?.startsWith("Africa/")) return DEFAULT_COUNTRY;
  } catch {
    // Intl indisponible ou fuseau illisible : la valeur par défaut fait
    // aussi bien qu'une supposition hasardeuse.
  }
  return DEFAULT_COUNTRY;
}
