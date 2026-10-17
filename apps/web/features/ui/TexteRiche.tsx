"use client";

/**
 * Un texte d'assistant, avec ses liens cliquables et son gras.
 *
 * Voir `segmentsTexte.ts` : aucune chaîne n'est injectée comme HTML. Un lien vers
 * le même site (la page de réservation) s'ouvre dans l'onglet ; un lien
 * extérieur, dans un nouvel onglet.
 */

import { decouper } from "./segmentsTexte";

export function TexteRiche({
  texte,
  classeLien = "",
}: {
  texte: string;
  /** Couleur et soulignement propres à la bulle qui l'affiche. */
  classeLien?: string;
}) {
  const ici = typeof window === "undefined" ? "" : window.location.host;

  return (
    <>
      {decouper(texte).map((morceau, index) => {
        if (morceau.type === "gras") {
          return (
            <strong key={index} className="font-semibold">
              {morceau.texte}
            </strong>
          );
        }
        if (morceau.type === "lien") {
          const externe = new URL(morceau.href).host !== ici;
          return (
            <a
              key={index}
              href={morceau.href}
              {...(externe ? { target: "_blank", rel: "noopener noreferrer" } : {})}
              className={`break-words font-semibold underline decoration-2 underline-offset-2 transition hover:opacity-80 ${classeLien}`}
            >
              {morceau.texte}
            </a>
          );
        }
        return <span key={index}>{morceau.texte}</span>;
      })}
    </>
  );
}
