/**
 * Les traductions envoyées au navigateur, section par section.
 *
 * `NextIntlClientProvider` sans `messages` sérialise le catalogue entier dans
 * chaque page : 174 Ko de français pour la page d'accueil, qui n'en lit que
 * quelques sections — l'essentiel des 285 Ko de son HTML, téléchargés avant
 * tout affichage sur téléphone. La racine n'envoie donc que ce que la page
 * d'accueil utilise ; l'espace pro, les mini-sites et la page hors ligne
 * reprennent le catalogue complet dans leur propre fournisseur (un
 * fournisseur imbriqué remplace celui du dessus, il ne s'y ajoute pas).
 */

import { getMessages } from "next-intl/server";

/** Les sections lues par les composants client de la page d'accueil. */
export const SECTIONS_ACCUEIL = ["accueil", "commun", "conversion", "langue", "site", "theme"] as const;

export async function messagesDe(sections: readonly string[]) {
  const tout = await getMessages();
  return Object.fromEntries(sections.filter((s) => s in tout).map((s) => [s, tout[s]]));
}
