"use client";

/**
 * Le commentaire d'un avis, replié sur téléphone.
 *
 * Sur téléphone, les avis s'affichent sur deux colonnes : une demi-largeur
 * d'écran. Un commentaire de trois phrases y prend une quinzaine de lignes,
 * et sa carte devient deux fois plus haute que sa voisine. Il est donc
 * replié à quelques lignes, avec « Lire la suite » — qui n'apparaît que si
 * le texte dépasse réellement, mesuré dans la page et non deviné au nombre
 * de caractères. À partir de 640 px, le texte s'affiche en entier.
 */

import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";

export function CommentaireAvis({ texte }: { texte: string }) {
  const t = useTranslations("salon");
  const ref = useRef<HTMLParagraphElement>(null);
  const [ouvert, setOuvert] = useState(false);
  const [depasse, setDepasse] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const mesurer = () => {
      // Replié, le texte deborde-t-il de ses lignes ? (1 px de marge pour
      // les arrondis de rendu.)
      if (!ouvert) setDepasse(el.scrollHeight > el.clientHeight + 1);
    };
    mesurer();
    const observateur = new ResizeObserver(mesurer);
    observateur.observe(el);
    return () => observateur.disconnect();
  }, [ouvert, texte]);

  return (
    <div className="relative mt-2 flex-1 sm:mt-3">
      <p
        ref={ref}
        className={`text-[0.78rem] leading-relaxed text-[var(--site-ink)] sm:text-sm ${
          ouvert ? "" : "line-clamp-5 sm:line-clamp-none"
        }`}
      >
        {texte}
      </p>
      {(depasse || ouvert) && (
        <button
          type="button"
          onClick={() => setOuvert((v) => !v)}
          aria-expanded={ouvert}
          className="mt-1 text-[0.72rem] font-semibold text-[var(--salon-ink,var(--salon-primary))] underline-offset-2 hover:underline sm:hidden"
        >
          {ouvert ? t("avisReduire") : t("avisLireSuite")}
        </button>
      )}
    </div>
  );
}
