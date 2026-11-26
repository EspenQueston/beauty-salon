/**
 * Outils communs au filtre du catalogue, côté serveur comme côté navigateur.
 *
 * Hors de `CategorieRail.tsx` à dessein : ce fichier-là porte « use client »,
 * et une fonction exportée d'un module client n'est, pour un composant
 * serveur, qu'une référence — l'appeler au rendu de la page échoue. Les
 * pages ont besoin de `slugCategorie` pour écrire leurs ancres.
 */

import type { SalonIconName } from "./icons";

export type CategorieFiltre = {
  id: string;
  /** Identifiant lisible, repris dans l'adresse (`?categorie=ongles`). */
  slug: string;
  nom: string;
  icone: SalonIconName;
  compte: number;
};

/**
 * Un texte sans casse ni accents, pour comparer ce qu'on tape à ce qui est
 * écrit : « defrisage » doit trouver « Défrisage », et « TRESSES » les
 * tresses.
 */
export function normaliser(texte: string): string {
  return texte
    .toLowerCase()
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .trim();
}

/**
 * Identifiant lisible et stable d'une catégorie, pour l'adresse et les
 * ancres. Le même qu'avant ce filtre : un lien `/prestations#ongles`
 * partagé autrefois mène toujours au bon endroit.
 */
export function slugCategorie(nom: string): string {
  return normaliser(nom)
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}
