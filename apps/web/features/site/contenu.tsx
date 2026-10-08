/**
 * Ce que la page d'accueil montre, et non ce qu'elle dit.
 *
 * ---------------------------------------------------------------------------
 * Le texte a déménagé
 * ---------------------------------------------------------------------------
 *
 * Ce fichier portait la copie de la page. Elle vit maintenant dans
 * `messages/fr.json` et `messages/en.json`, sous la clé `accueil` : une page
 * servie en deux langues ne peut pas garder ses phrases dans son code.
 *
 * Il reste ici ce qui ne se traduit pas — les tracés d'icônes — et les
 * **clés** qui relient une carte à son texte. Elles donnent aussi l'ordre
 * d'affichage, que le JSON ne garantit pas.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi les clés vivent encore dans un tableau
 * ---------------------------------------------------------------------------
 *
 * La page a deux mises en page — une grille sur grand écran, un rail et une
 * frise sur téléphone. Deux listes de clés finiraient par diverger : on
 * ajouterait un atout d'un côté et pas de l'autre, et personne ne regarde
 * jamais les deux largeurs en même temps.
 */

import type { ReactNode } from "react";

/** Un atout : sa clé dans le catalogue, et son icône. */
export interface Atout {
  cle: string;
  icone: ReactNode;
}

export const ATOUTS: Atout[] = [
  {
    cle: "vitrine",
    icone: (
      <>
        <rect x="3" y="4" width="18" height="16" rx="2" />
        <path d="M3 9h18" />
        <path d="M7 6.5h.01M10 6.5h.01" />
      </>
    ),
  },
  {
    cle: "agenda",
    icone: (
      <>
        <rect x="3" y="5" width="18" height="16" rx="2" />
        <path d="M3 10h18M8 3v4M16 3v4" />
        <path d="m9 15 2 2 4-4" />
      </>
    ),
  },
  {
    cle: "gestion",
    icone: (
      <>
        <circle cx="9" cy="8" r="3.2" />
        <path d="M3.5 20a5.5 5.5 0 0 1 11 0" />
        <path d="M16 5.2a3.2 3.2 0 0 1 0 5.6M17.5 14.4A5.5 5.5 0 0 1 20.5 20" />
      </>
    ),
  },
];

/** Les trois étapes, dans l'ordre où on les franchit. */
export const ETAPES = ["creer", "remplir", "partager"] as const;

/** Les questions, de la plus fréquente à la plus rare. */
export const QUESTIONS = [
  "prix",
  "miseEnLigne",
  "seule",
  "paiement",
  "donnees",
] as const;

/** L'icône d'une flèche vers la droite, reprise sur tous les appels. */
export function Fleche({ className = "size-4" }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      aria-hidden
      className={className}
    >
      <path d="M5 12h14M13 6l6 6-6 6" strokeLinecap="round" />
    </svg>
  );
}
