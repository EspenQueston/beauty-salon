/**
 * L'adresse publique d'une page, et ses sœurs dans les autres langues.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi un en-tête plutôt qu'un paramètre
 * ---------------------------------------------------------------------------
 *
 * Une page du mini-site reçoit son chemin **interne** —
 * `/fr/s/blondrose.com/prestations` — et n'a aucun moyen de remonter à celui
 * qu'affiche la barre d'adresse : `/prestations`. Le proxy, lui, voit les
 * deux ; il pose donc le chemin public dans un en-tête de requête.
 *
 * C'est celui-là qu'il faut, et pas un autre : une page qui se déclare
 * canonique sous son adresse interne ne serait jamais indexée, et des
 * `hreflang` qui pointent vers des chemins internes ne désignent rien.
 *
 * ---------------------------------------------------------------------------
 * Canonique et `hreflang` doivent s'accorder
 * ---------------------------------------------------------------------------
 *
 * Les deux se contredisent facilement, et Google tranche alors en ignorant
 * les `hreflang`. Une page anglaise qui se déclare canonique vers la page
 * française dit « je suis un doublon » : la version anglaise disparaît de
 * l'index, quelles que soient les balises de langue posées à côté.
 *
 * Chaque page est donc canonique **d'elle-même, dans sa langue**, et liste
 * ses sœurs séparément. `x-default` désigne le français, qui est la version
 * servie à qui ne demande rien de précis.
 */

import type { Metadata } from "next";

import { LANGUES, prefixe, type Langue } from "./langues";

/** L'en-tête où le proxy dépose le chemin public, préfixe de langue ôté. */
export const ENTETE_CHEMIN = "x-chemin-public";

/**
 * Les balises d'adresse d'une page, pour un hôte et un chemin donnés.
 *
 * `hote` est le sous-domaine du salon ou le domaine de la plateforme, sans
 * protocole. `chemin` commence par une barre oblique et ne porte pas de
 * langue.
 */
export function adresses(
  hote: string,
  chemin: string,
  langue: Langue,
): Metadata["alternates"] {
  const url = (l: Langue) => {
    const base = `https://${hote}${prefixe(l)}`;
    return chemin === "/" ? `${base}/` : `${base}${chemin}`;
  };

  const langues: Record<string, string> = {};
  for (const l of LANGUES) langues[l] = url(l);
  // `x-default` : ce qu'on sert à qui n'a demandé aucune langue en
  // particulier. C'est l'adresse sans préfixe, donc le français.
  langues["x-default"] = url("fr");

  return { canonical: url(langue), languages: langues };
}
