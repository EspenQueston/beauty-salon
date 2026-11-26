import type { ReactNode } from "react";
import { Reveal } from "@/features/ui/Reveal";

/**
 * Le ton d'une section de la page d'accueil.
 *
 * Quatre tons, tous dans la teinte de la marque — c'est ce qui rend la page
 * cohérente : on ne passe jamais d'un gris froid à un rose chaud.
 *
 *   - `base`    le fond de la page ;
 *   - `nuance`  un neutre chaud (quelques pour cent de rose), en alternance
 *               avec la base pour rythmer la lecture sans bordures ;
 *   - `vedette` le seul bandeau immersif, prune profond, texte blanc ;
 *   - l'appel final, rose plein, est porté par `home-callout`.
 *
 * Le ton est choisi section par section, et non par un compteur CSS
 * (`nth-of-type`) : une section qui n'apparaît que sous condition décalait
 * toute l'alternance, et deux fonds identiques finissaient côte à côte.
 */
export type TonSection = "base" | "nuance" | "vedette";

/** Full-width background, with the same readable content width as the hero. */
export function HomeSection({
  id,
  children,
  className = "",
  ton = "base",
}: {
  id: string;
  children: ReactNode;
  className?: string;
  ton?: TonSection;
}) {
  return <Reveal as="section" variant="section" id={id} className={`home-section home-ton-${ton} scroll-mt-24 px-4 py-8 sm:px-6 sm:py-12 ${className}`}>
    <div className="mx-auto w-full max-w-7xl">{children}</div>
  </Reveal>;
}
