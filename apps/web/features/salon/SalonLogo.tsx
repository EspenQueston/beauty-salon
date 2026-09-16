/**
 * Logo du salon, débarrassé de son fond blanc.
 *
 * ---------------------------------------------------------------------------
 * Le problème
 * ---------------------------------------------------------------------------
 *
 * Les logos arrivent presque toujours en JPEG ou en PNG aplati, avec un fond
 * blanc cuit dans l'image. Posé sur un haut de page sombre ou sur une teinte
 * de marque, ce carré blanc se détache comme un autocollant : c'est la
 * première chose qu'on voit, et elle dit « gabarit non fini ».
 *
 * On ne peut pas détourer une image raster de façon fiable côté navigateur —
 * un détourage automatique mangerait les parties claires du logo lui-même.
 *
 * ---------------------------------------------------------------------------
 * La solution
 * ---------------------------------------------------------------------------
 *
 * `mix-blend-multiply` : chaque pixel est multiplié par le fond. Le blanc
 * (valeur 1) laisse le fond intact — il devient donc *invisible* — tandis que
 * les traits foncés du logo restent foncés. Le carré blanc disparaît sans
 * qu'aucun pixel du dessin ne soit touché.
 *
 * Le fond est volontairement **toujours clair**, y compris en mode sombre :
 * multiplier sur un fond noir écraserait le logo entier. Il est teinté par la
 * couleur du salon, ce qui raccorde le logo au reste de la page au lieu de le
 * laisser flotter.
 *
 * Un logo déjà transparent (PNG à canal alpha) traverse ce traitement sans
 * dommage : il n'a pas de blanc à neutraliser.
 */

import type { MediaAsset } from "@/lib/types";

export function SalonLogo({
  logo,
  name,
  className = "size-12",
  rounded = "rounded-xl",
}: {
  logo: MediaAsset | null;
  name: string;
  className?: string;
  rounded?: string;
}) {
  // Sans logo, l'initiale fait office de marque : un emplacement vide en dit
  // moins qu'une lettre.
  if (!logo) {
    return (
      <span
        aria-hidden
        className={`salon-gradient flex shrink-0 items-center justify-center font-semibold text-white ${className} ${rounded}`}
      >
        {name.slice(0, 1).toUpperCase()}
      </span>
    );
  }

  return (
    <span
      className={`relative flex shrink-0 items-center justify-center overflow-hidden ${className} ${rounded}`}
      style={{
        // Teinte claire dérivée de la couleur du salon : elle raccorde le
        // logo à la page, et reste assez claire pour que la multiplication
        // préserve le dessin.
        background: "color-mix(in srgb, var(--salon-primary) 10%, white)",
      }}
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={logo.url}
        alt={logo.alt_text || name}
        className="size-full object-contain mix-blend-multiply"
      />
    </span>
  );
}
