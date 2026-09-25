/** Palette unique pour l'aperçu, l'inscription et l'espace salon. */
export const PALETTES = [
  { cle: "rose", name: "Rose poudré", primary: "#B4436C", accent: "#F7D9E1", surface: "#FCF7F9" },
  { cle: "orNuit", name: "Or et nuit", primary: "#1F2937", accent: "#E9C46A", surface: "#FBF8F1" },
  { cle: "terracotta", name: "Terracotta", primary: "#9C4221", accent: "#F6D5C0", surface: "#FDF7F3" },
  { cle: "emeraude", name: "Émeraude", primary: "#0F766E", accent: "#CDEDE7", surface: "#F4FAF9" },
  { cle: "violet", name: "Violet", primary: "#6D28D9", accent: "#E4D8FB", surface: "#F9F7FE" },
  { cle: "bleuNuit", name: "Bleu nuit", primary: "#1E3A8A", accent: "#D6E0FA", surface: "#F6F8FD" },
  { cle: "cacao", name: "Cacao", primary: "#5C3A21", accent: "#E8D5C0", surface: "#FBF7F3" },
  { cle: "corail", name: "Corail", primary: "#C2410C", accent: "#FDDCC8", surface: "#FFF8F4" },
  { cle: "prune", name: "Prune", primary: "#86198F", accent: "#F3D5F5", surface: "#FDF6FE" },
  { cle: "encreMenthe", name: "Encre et menthe", primary: "#134E4A", accent: "#B9E7DC", surface: "#F2FAF8" },
] as const;

export type PaletteCle = (typeof PALETTES)[number]["cle"];

export function paletteDepuisCouleurs(theme: Record<string, string> | null): PaletteCle | "" {
  if (!theme) return "";
  return PALETTES.find((palette) =>
    palette.primary.toLowerCase() === theme.primary?.toLowerCase() &&
    palette.accent.toLowerCase() === theme.accent?.toLowerCase() &&
    palette.surface.toLowerCase() === theme.surface?.toLowerCase()
  )?.cle ?? "";
}
