/**
 * Les langues du produit, et la forme qu'elles prennent dans une URL.
 *
 * ---------------------------------------------------------------------------
 * Le français n'a pas de préfixe, l'anglais en a un
 * ---------------------------------------------------------------------------
 *
 *   blondrose.com/prestations       → français
 *   blondrose.com/en/prestations    → anglais
 *
 * C'est la stratégie dite « as-needed ». Elle a été choisie contre la
 * symétrie — `/fr/…` et `/en/…` — pour une raison qui n'est pas esthétique :
 * un mini-site se partage sur WhatsApp, et les liens déjà envoyés doivent
 * continuer de fonctionner tels quels. Les préfixer tous obligerait à une
 * redirection permanente sur chaque adresse existante, et un lien qui rebondit
 * est un lien qu'on perd sur une connexion lente.
 *
 * Chaque langue garde donc une adresse propre, partageable et indexable, et
 * les pages se déclarent l'une l'autre par `hreflang` — ce que Google demande
 * pour ne pas les prendre pour des doublons.
 *
 * ---------------------------------------------------------------------------
 * Le préfixe n'existe que dans la barre d'adresse
 * ---------------------------------------------------------------------------
 *
 * `proxy.ts` le retire avant de réécrire, et le repose sous forme de segment
 * `[locale]` en tête du chemin interne. Les pages ne voient donc jamais
 * `/en/…` : elles voient `locale`, ce que Next sert à tout composant serveur
 * par `next/root-params`.
 *
 * Ce fichier ne dépend de rien — ni de Next, ni de React. Il est lu par le
 * proxy, qui s'exécute au bord, autant que par les composants.
 */

export const LANGUES = ["fr", "en"] as const;

export type Langue = (typeof LANGUES)[number];

/** Celle qui ne porte pas de préfixe. */
export const LANGUE_PAR_DEFAUT: Langue = "fr";

/** Le nom de chaque langue, écrit dans cette langue. */
export const NOM_LANGUE: Record<Langue, string> = {
  fr: "Français",
  en: "English",
};

/**
 * Le nom du cookie.
 *
 * `NEXT_LOCALE` est la convention que partagent Next et les bibliothèques
 * d'internationalisation ; la respecter évite qu'un jour deux mécanismes se
 * contredisent sur la même machine.
 */
export const COOKIE_LANGUE = "NEXT_LOCALE";

/** Un an : un choix de langue n'est pas une session. */
export const DUREE_COOKIE = 60 * 60 * 24 * 365;

export function estLangue(valeur: string | undefined | null): valeur is Langue {
  return !!valeur && (LANGUES as readonly string[]).includes(valeur);
}

/** Ce que la langue ajoute devant un chemin. Vide pour le français. */
export function prefixe(langue: Langue): string {
  return langue === LANGUE_PAR_DEFAUT ? "" : `/${langue}`;
}

/**
 * Sépare un chemin public en (langue, reste).
 *
 * `/en/prestations` → `{ langue: "en", reste: "/prestations" }`
 * `/prestations`    → `{ langue: null, reste: "/prestations" }`
 *
 * `langue: null` et non `"fr"` : l'absence de préfixe n'est pas un choix de
 * français, c'est une absence de choix. Le proxy a encore le cookie et
 * l'en-tête `Accept-Language` à consulter avant de trancher.
 */
export function decouper(chemin: string): { langue: Langue | null; reste: string } {
  const segments = chemin.split("/");
  // `chemin` commence par « / », donc `segments[0]` est vide.
  const premier = segments[1];
  if (!estLangue(premier)) return { langue: null, reste: chemin };

  const reste = "/" + segments.slice(2).join("/");
  return { langue: premier, reste: reste === "/" ? "/" : reste.replace(/\/$/, "") };
}

/**
 * Le même chemin, dit dans une autre langue.
 *
 * Sert au sélecteur de langue — qui doit rester sur la page où l'on est — et
 * aux balises `hreflang`.
 */
export function traduireChemin(chemin: string, vers: Langue): string {
  const { reste } = decouper(chemin);
  const base = prefixe(vers);
  if (reste === "/") return base || "/";
  return `${base}${reste}`;
}

/**
 * La langue préférée d'un navigateur, d'après `Accept-Language`.
 *
 * Volontairement rudimentaire : on ne cherche pas la meilleure correspondance
 * pondérée, seulement la première langue reconnue dans l'ordre déclaré. Un
 * `fr-CA` compte pour du français, un `en-GB` pour de l'anglais.
 *
 * Renvoie `null` quand rien n'est reconnu, ce qui n'est pas la même chose que
 * « français » : l'appelant décide quoi faire d'une absence de préférence.
 */
export function langueDemandee(entete: string | null): Langue | null {
  if (!entete) return null;

  for (const morceau of entete.split(",")) {
    const etiquette = morceau.split(";")[0].trim().toLowerCase();
    const racine = etiquette.split("-")[0];
    if (estLangue(racine)) return racine;
  }
  return null;
}
