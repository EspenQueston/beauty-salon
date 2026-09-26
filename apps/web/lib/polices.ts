/**
 * Les polices proposées aux salons Pro — et elles seules.
 *
 * La liste est fermée, comme côté serveur (`apps/salons/personnalisation.py`) :
 * une clé inconnue retombe sur Geist. Chaque police est déclarée ici, au
 * niveau du module comme l'exige `next/font`, sans préchargement : elles
 * sont servies par le site lui-même, et le navigateur ne télécharge que
 * celle qu'une page utilise vraiment.
 */

import {
  Bodoni_Moda,
  Cinzel,
  Cormorant_Garamond,
  DM_Serif_Display,
  Dancing_Script,
  Fraunces,
  Great_Vibes,
  Italiana,
  Josefin_Sans,
  Libre_Baskerville,
  Lora,
  Manrope,
  Marcellus,
  Montserrat,
  Nunito,
  Outfit,
  Parisienne,
  Playfair_Display,
  Poppins,
  Quicksand,
  Raleway,
} from "next/font/google";

// Options ecrites en toutes lettres a chaque appel : le chargeur de
// `next/font` lit ces objets a la compilation et refuse les variables et
// les decompositions (`...`).

const playfair = Playfair_Display({ subsets: ["latin"], preload: false, variable: "--police-playfair" });
const cormorant = Cormorant_Garamond({ subsets: ["latin"], preload: false, weight: ["400", "500", "600", "700"],
  variable: "--police-cormorant",
});
const dmSerif = DM_Serif_Display({ subsets: ["latin"], preload: false, weight: "400", variable: "--police-dm-serif" });
const lora = Lora({ subsets: ["latin"], preload: false, variable: "--police-lora" });
const montserrat = Montserrat({ subsets: ["latin"], preload: false, variable: "--police-montserrat" });
const poppins = Poppins({ subsets: ["latin"], preload: false, weight: ["400", "500", "600", "700"],
  variable: "--police-poppins",
});
const josefin = Josefin_Sans({ subsets: ["latin"], preload: false, variable: "--police-josefin" });
const nunito = Nunito({ subsets: ["latin"], preload: false, variable: "--police-nunito" });
const raleway = Raleway({ subsets: ["latin"], preload: false, variable: "--police-raleway" });
const manrope = Manrope({ subsets: ["latin"], preload: false, variable: "--police-manrope" });
const outfit = Outfit({ subsets: ["latin"], preload: false, variable: "--police-outfit" });
const quicksand = Quicksand({ subsets: ["latin"], preload: false, variable: "--police-quicksand" });
const libreBaskerville = Libre_Baskerville({ subsets: ["latin"], preload: false, variable: "--police-libre-baskerville" });
const fraunces = Fraunces({ subsets: ["latin"], preload: false, variable: "--police-fraunces" });
const bodoni = Bodoni_Moda({ subsets: ["latin"], preload: false, variable: "--police-bodoni" });
const cinzel = Cinzel({ subsets: ["latin"], preload: false, variable: "--police-cinzel" });
const italiana = Italiana({ subsets: ["latin"], preload: false, weight: "400", variable: "--police-italiana" });
const marcellus = Marcellus({ subsets: ["latin"], preload: false, weight: "400", variable: "--police-marcellus" });
const greatVibes = Great_Vibes({ subsets: ["latin"], preload: false, weight: "400", variable: "--police-great-vibes" });
const dancing = Dancing_Script({ subsets: ["latin"], preload: false, variable: "--police-dancing-script" });
const parisienne = Parisienne({ subsets: ["latin"], preload: false, weight: "400", variable: "--police-parisienne" });

const POLICES: Record<string, { variable: string; famille: string }> = Object.fromEntries(
  (
    [
      ["playfair", playfair],
      ["cormorant", cormorant],
      ["dm-serif", dmSerif],
      ["lora", lora],
      ["montserrat", montserrat],
      ["poppins", poppins],
      ["josefin", josefin],
      ["nunito", nunito],
      ["raleway", raleway],
      ["manrope", manrope],
      ["outfit", outfit],
      ["quicksand", quicksand],
      ["libre-baskerville", libreBaskerville],
      ["fraunces", fraunces],
      ["bodoni", bodoni],
      ["cinzel", cinzel],
      ["italiana", italiana],
      ["marcellus", marcellus],
      ["great-vibes", greatVibes],
      ["dancing-script", dancing],
      ["parisienne", parisienne],
    ] as const
  ).map(([cle, police]) => [
    cle,
    { variable: police.variable, famille: `var(--police-${cle})` },
  ]),
);

/**
 * Les classes et les variables CSS qui posent les deux polices choisies.
 * Rien quand le salon garde Geist : la page reste exactement celle d'avant.
 */
export function stylePolices(titres?: string, texte?: string) {
  const choixTitres = titres ? POLICES[titres] : undefined;
  const choixTexte = texte ? POLICES[texte] : undefined;
  const classes = [choixTitres?.variable, choixTexte?.variable].filter(Boolean).join(" ");
  const style: Record<string, string> = {};
  if (choixTitres) style["--salon-police-titres"] = choixTitres.famille;
  if (choixTexte) style["--salon-police-texte"] = choixTexte.famille;
  return { classes, style };
}

/** Toutes les classes de police, pour l'aperçu de l'espace pro (téléchargées à l'usage). */
export const TOUTES_LES_POLICES = Object.values(POLICES)
  .map((police) => police.variable)
  .join(" ");

/** La pile CSS d'une police proposée ; celle du produit pour Geist ou une clé inconnue. */
export function familleDe(cle: string): string {
  return `${POLICES[cle]?.famille ?? "var(--font-sans)"}, system-ui, sans-serif`;
}
