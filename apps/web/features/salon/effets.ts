/**
 * Les effets de l'accueil des mini-sites, réglés en un seul endroit.
 *
 * Deux familles :
 *
 *   - le **ciel** : particules et étoiles filantes derrière le contenu de la
 *     page, sous le haut de page — qui, lui, garde ses seules photos
 *     (`CielEtoile.tsx`) ;
 *   - les **entrées** : l'apparition des blocs et la cascade des cartes
 *     (`Reveal`, réglé pour l'accueil dans `globals.css`, section « Accueil
 *     des mini-sites »).
 *
 * Les couleurs et l'intensité ne sont pas ici : elles dépendent du thème du
 * salon et du mode clair/sombre, donc de variables CSS (`--ciel-etoile`,
 * `--ciel-intensite`), lues par le moteur au montage et à chaque changement
 * de mode. Les durées d'entrée sont aussi des variables CSS
 * (`--entree-duree`, `--entree-distance`, `--entree-echelle`, `--entree-flou`) :
 * le navigateur les applique avant même que le JavaScript ne charge.
 */

/*
 * Une seule zone aujourd'hui : le fond de la page sous le haut de page. Le
 * type reste ouvert pour qu'une autre zone puisse avoir ses propres réglages.
 */
export type ZoneCiel = "page";

export const CIEL = {
  /**
   * Profondeur. Chaque particule reçoit une profondeur entre 0 (lointaine)
   * et 1 (proche) ; taille, opacité, vitesse et parallaxe en dépendent. Le
   * tirage favorise les lointaines (`profondeurExposant` > 1) : un ciel où
   * tout est proche n'a plus de fond.
   */
  profondeurExposant: 1.7,
  /** Rayon en pixels CSS, de la plus lointaine à la plus proche. */
  rayon: [0.45, 1.7] as const,
  /** Opacité, de la plus lointaine à la plus proche (avant intensité). */
  opacite: [0.18, 0.78] as const,
  /** Part de la hauteur parcourue en une seconde, au premier plan. */
  vitesse: 0.016,
  /** Dérive horizontale, relative à la vitesse verticale. */
  derive: 0.35,
  /**
   * Décalage au défilement, en fraction du défilement, au premier plan. Le
   * ciel est fixe derrière la page : en défilant, les particules proches
   * glissent plus vite que les lointaines — c'est là que la profondeur se lit.
   */
  parallaxe: 0.3,
  /** Pulsation du scintillement, en radians par seconde. */
  scintillement: [0.5, 1.5] as const,
  /** Amplitude du scintillement (0 : fixe, 1 : s'éteint complètement). */
  scintillementAmplitude: 0.38,

  /** Une particule pour tant de pixels² d'écran, plafonnée. */
  densite: {
    bureau: { pixelsParEtoile: 5200, max: 230 },
    mobile: { pixelsParEtoile: 9500, max: 85 },
  },
  /** Au-dessous de cette largeur, réglages « mobile ». */
  largeurMobile: 640,
  /** Images par seconde visées : un téléphone n'a pas besoin de 60. */
  imagesParSeconde: { bureau: 60, mobile: 24 },
  /** Densité de pixels plafonnée : au-delà, le coût monte sans rien voir de plus. */
  ratioMax: { bureau: 2, mobile: 1.25 },

  /**
   * Fondu vertical, par zone : l'opacité des particules selon leur hauteur
   * à l'écran, en paliers [position, opacité], la position en fraction de la
   * hauteur. Plus discret en haut, sous la barre de navigation.
   *
   * Calculé par particule plutôt que par un masque CSS : un masque sur un
   * canvas animé oblige le navigateur à repeindre le calque à chaque image —
   * c'était l'essentiel du coût sur téléphone.
   */
  fondu: {
    page: [[0, 0.35], [0.14, 1], [1, 1]] as const,
  },

  /** Étoiles filantes, par zone : intervalle aléatoire entre deux, en secondes. */
  filantes: {
    page: [6, 13] as const,
    /** Plus rares sur téléphone. */
    facteurMobile: 1.6,
    /** Durée de vie, en secondes. */
    duree: [0.7, 1.1] as const,
    /** Longueur de la traînée, en pixels CSS (réduite de 30 % sur téléphone). */
    trainee: [110, 190] as const,
    /** Inclinaison sous l'horizontale, en degrés. */
    angle: [16, 32] as const,
    /** Vitesse, en largeurs d'écran par seconde. */
    vitesse: [0.55, 0.85] as const,
  },
} as const;

/** Cascade des cartes : décalage entre deux cartes, plafonné. */
export const ENTREE = {
  // 70 ms se confondait avec une apparition simultanée : à 110 ms, on voit
  // les cartes arriver l'une après l'autre.
  cascadeMs: 110,
  /** Au-delà de ce rang, la carte n'attend plus : on lirait l'animation. */
  cascadeMax: 5,
} as const;

/** Le délai d'entrée d'une carte selon son rang dans sa grille. */
export function delaiCascade(rang: number, max: number = ENTREE.cascadeMax): number {
  return Math.min(Math.max(rang, 0), max) * ENTREE.cascadeMs;
}

/*
 * L'interrupteur de pause et la lecture de `prefers-reduced-motion` vivent
 * dans `fondPause.ts` : ce sont des hooks, et ce module-ci est aussi lu par
 * des composants serveur (la cascade des cartes).
 */
