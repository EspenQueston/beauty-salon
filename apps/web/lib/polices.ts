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
  Cormorant_Garamond,
  DM_Serif_Display,
  Josefin_Sans,
  Lora,
  Montserrat,
  Nunito,
  Playfair_Display,
  Poppins,
} from "next/font/google";

const playfair = Playfair_Display({ subsets: ["latin"], variable: "--police-playfair", preload: false });
const cormorant = Cormorant_Garamond({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--police-cormorant",
  preload: false,
});
const dmSerif = DM_Serif_Display({
  subsets: ["latin"],
  weight: "400",
  variable: "--police-dm-serif",
  preload: false,
});
const lora = Lora({ subsets: ["latin"], variable: "--police-lora", preload: false });
const montserrat = Montserrat({ subsets: ["latin"], variable: "--police-montserrat", preload: false });
const poppins = Poppins({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--police-poppins",
  preload: false,
});
const josefin = Josefin_Sans({ subsets: ["latin"], variable: "--police-josefin", preload: false });
const nunito = Nunito({ subsets: ["latin"], variable: "--police-nunito", preload: false });

const POLICES: Record<string, { variable: string; famille: string }> = {
  playfair: { variable: playfair.variable, famille: "var(--police-playfair)" },
  cormorant: { variable: cormorant.variable, famille: "var(--police-cormorant)" },
  "dm-serif": { variable: dmSerif.variable, famille: "var(--police-dm-serif)" },
  lora: { variable: lora.variable, famille: "var(--police-lora)" },
  montserrat: { variable: montserrat.variable, famille: "var(--police-montserrat)" },
  poppins: { variable: poppins.variable, famille: "var(--police-poppins)" },
  josefin: { variable: josefin.variable, famille: "var(--police-josefin)" },
  nunito: { variable: nunito.variable, famille: "var(--police-nunito)" },
};

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
