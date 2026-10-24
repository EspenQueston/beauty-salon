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

export type CountryCode =
  | "CG" | "CD" | "CN"
  | "BJ" | "BF" | "CI" | "TG" | "SN" | "NE"
  | "CM" | "GH" | "GN" | "KE" | "ML" | "MW" | "NG" | "RW" | "TZ" | "UG" | "ZM";

const BY_TIMEZONE: Record<string, CountryCode> = {
  "Africa/Brazzaville": "CG",
  "Africa/Kinshasa": "CD",
  "Africa/Lubumbashi": "CD",
  "Africa/Porto-Novo": "BJ",
  "Africa/Ouagadougou": "BF",
  "Africa/Abidjan": "CI",
  "Africa/Lome": "TG",
  "Africa/Dakar": "SN",
  "Africa/Niamey": "NE",
  "Africa/Douala": "CM",
  "Africa/Accra": "GH",
  "Africa/Conakry": "GN",
  "Africa/Nairobi": "KE",
  "Africa/Bamako": "ML",
  "Africa/Blantyre": "MW",
  "Africa/Lagos": "NG",
  "Africa/Kigali": "RW",
  "Africa/Dar_es_Salaam": "TZ",
  "Africa/Kampala": "UG",
  "Africa/Lusaka": "ZM",
  "Asia/Shanghai": "CN",
  "Asia/Chongqing": "CN",
  "Asia/Harbin": "CN",
  "Asia/Urumqi": "CN",
  "Asia/Macau": "CN",
  "Asia/Hong_Kong": "CN",
};

export const DEFAULT_COUNTRY: CountryCode = "CG";

export function guessCountry(): CountryCode {
  return countryFromTimezone() ?? DEFAULT_COUNTRY;
}

/**
 * Le pays que le fuseau désigne vraiment, ou `null`.
 *
 * Sans repli : là où `guessCountry` doit remplir un champ quoi qu'il arrive,
 * la grille tarifaire de l'accueil préfère ne rien supposer — un visiteur à
 * Paris n'a pas à voir les prix du Congo en dollars.
 */
export function countryFromTimezone(): CountryCode | null {
  if (typeof Intl === "undefined") return null;

  try {
    const zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    if (zone && BY_TIMEZONE[zone]) return BY_TIMEZONE[zone];

    // Repli par région : un fuseau chinois non listé reste la Chine.
    if (zone?.startsWith("Asia/")) return "CN";
    if (zone?.startsWith("Africa/")) return DEFAULT_COUNTRY;
  } catch {
    // Intl indisponible ou fuseau illisible : aucune supposition plutôt
    // qu'une supposition hasardeuse.
  }
  return null;
}
