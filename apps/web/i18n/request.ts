/**
 * Ce que `next-intl` doit savoir à chaque requête.
 *
 * La langue vient du segment `[locale]`, lu par `next/root-params` : c'est un
 * paramètre **racine**, donc disponible dans n'importe quel composant serveur
 * sans le faire descendre de props en props. Rien d'autre ne la détermine ici
 * — le cookie et `Accept-Language` ont déjà été consultés par `proxy.ts`, qui
 * a posé le segment en conséquence.
 *
 * Le repli n'est pas décoratif : `[locale]` attrape aussi les chemins inconnus
 * (`/robots.txt`, `/quelquechose`). Sans lui, une adresse fautive ferait
 * chercher `messages/robots.txt.json` et lever une erreur de module — une
 * page 500 là où un 404 est attendu.
 */

import { locale as segment } from "next/root-params";
import { getRequestConfig } from "next-intl/server";

import { estLangue, LANGUE_PAR_DEFAUT } from "./langues";

export default getRequestConfig(async () => {
  const brut = await segment();
  const locale = estLangue(brut) ? brut : LANGUE_PAR_DEFAUT;

  return {
    locale,
    messages: (await import(`../messages/${locale}.json`)).default,
  };
});
