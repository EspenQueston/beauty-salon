"use client";

/**
 * Réalisations du salon : photos et vidéos courtes.
 *
 * C'est la section qui convainc. Un tarif rassure, une photo décide — la
 * cliente veut voir des tresses déjà faites, pas lire qu'on en fait.
 *
 * Trois choix qui comptent sur les réseaux mobiles visés :
 *
 *   - les vidéos ne se chargent pas toutes seules (`preload="metadata"`) ;
 *     une grille de six vidéos en lecture automatique coûterait plusieurs
 *     dizaines de mégaoctets à quelqu'un qui paie sa donnée ;
 *   - la visionneuse ne charge le média en grand qu'à l'ouverture ;
 *   - la mosaïque est irrégulière mais déterministe : elle donne du rythme
 *     sans dépendre du format réel des fichiers, qu'on ne connaît pas
 *     toujours.
 */

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { Reveal } from "@/features/ui/Reveal";
import { isVideo, type MediaAsset } from "@/lib/types";
import { SalonIcon } from "./icons";
import { photo, TAILLES } from "./images";

/** Motif de tailles répété : la 1re et la 6e occupent deux colonnes. */
function spanOf(index: number): string {
  const position = index % 6;
  if (position === 0) return "sm:col-span-2 sm:row-span-2";
  if (position === 5) return "sm:col-span-2";
  return "";
}

export function GalleryGrid({
  assets,
  salonName,
}: {
  assets: MediaAsset[];
  salonName: string;
}) {
  const t = useTranslations("salon");
  const [openIndex, setOpenIndex] = useState<number | null>(null);

  const close = useCallback(() => setOpenIndex(null), []);

  const move = useCallback(
    (delta: number) =>
      setOpenIndex((current) =>
        current === null
          ? null
          : (current + delta + assets.length) % assets.length,
      ),
    [assets.length],
  );

  // Clavier : échappement pour fermer, flèches pour parcourir. Une galerie
  // qu'on ne peut quitter qu'à la souris piège qui navigue au clavier.
  useEffect(() => {
    if (openIndex === null) return;

    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
      if (event.key === "ArrowRight") move(1);
      if (event.key === "ArrowLeft") move(-1);
    };

    document.addEventListener("keydown", onKey);
    // Le fond ne doit pas défiler derrière la visionneuse.
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = previous;
    };
  }, [openIndex, close, move]);

  const open = openIndex === null ? null : assets[openIndex];

  return (
    <>
      <ul className="grid auto-rows-[10rem] grid-cols-2 gap-3 sm:auto-rows-[12rem] sm:grid-cols-4">
        {assets.map((asset, index) => (
          /*
            L'apparition est portee par le <li> lui-meme via `as`.

            Envelopper la tuile dans un <div> casserait la grille : c'est le
            <li> qui porte les classes de colonne, et un intermediaire lui
            volerait sa place. Le decalage est plafonne a huit tuiles, sinon
            la quarantieme photo attendrait trois secondes pour rien.
          */
          <Reveal
            as="li"
            key={asset.id}
            delay={Math.min(index, 8) * 60}
            className={spanOf(index)}
          >
            {/*
              La légende est sous le média, pas dessus.

              Superposée, elle n'apparaissait qu'au survol — donc jamais sur
              un téléphone, où il n'y a pas de survol, et où se trouve la
              majorité des visiteuses. Et posée sur une photo dont on ne
              contrôle ni la luminosité ni le cadrage, sa lisibilité était une
              loterie. Sur une bande unie, elle se lit toujours.
            */}
            <button
              type="button"
              onClick={() => setOpenIndex(index)}
              className="group flex size-full flex-col overflow-hidden rounded-2xl bg-[var(--site-surface)] text-left ring-1 ring-[var(--site-line)] transition hover:ring-[var(--salon-primary)]"
              aria-label={
                asset.alt_text ||
                t("galerie.altNumerotee", { n: index + 1, salon: salonName })
              }
            >
              <span className="relative min-h-0 flex-1 overflow-hidden bg-black/[0.05]">
                {isVideo(asset) ? (
                  <>
                    <video
                      src={asset.url}
                      preload="metadata"
                      muted
                      playsInline
                      className="size-full object-cover transition-transform duration-500 group-hover:scale-105"
                    />
                    <span className="absolute inset-0 flex items-center justify-center bg-black/25">
                      <span className="flex size-12 items-center justify-center rounded-full bg-white/90 text-[var(--salon-ink-white)] shadow-lg transition-transform duration-300 group-hover:scale-110">
                        <SalonIcon name="play" className="size-6" filled />
                      </span>
                    </span>
                  </>
                ) : (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    {...photo(asset, TAILLES.grille)}
                    alt={
                      asset.alt_text || t("galerie.alt", { salon: salonName })
                    }
                    loading="lazy"
                    className="size-full object-cover transition-transform duration-500 group-hover:scale-105"
                  />
                )}
              </span>

              {asset.alt_text && (
                <span className="line-clamp-2 shrink-0 px-2.5 py-2 text-[0.72rem] font-medium leading-snug text-[var(--site-muted)] sm:text-xs">
                  {asset.alt_text}
                </span>
              )}
            </button>
          </Reveal>
        ))}
      </ul>

      {open && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label={open.alt_text || t("galerie.simple")}
          onClick={close}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 p-4 backdrop-blur-sm"
        >
          <button
            type="button"
            onClick={close}
            aria-label="Fermer"
            className="absolute right-4 top-4 flex size-11 items-center justify-center rounded-full bg-white/10 text-white transition hover:bg-white/20"
          >
            <SalonIcon name="close" className="size-5" />
          </button>

          {assets.length > 1 && (
            <>
              <button
                type="button"
                onClick={(event) => {
                  event.stopPropagation();
                  move(-1);
                }}
                aria-label={t("precedente")}
                className="absolute left-3 flex size-11 items-center justify-center rounded-full bg-white/10 text-white transition hover:bg-white/20"
              >
                <SalonIcon name="arrow" className="size-5 rotate-180" />
              </button>
              <button
                type="button"
                onClick={(event) => {
                  event.stopPropagation();
                  move(1);
                }}
                aria-label={t("suivante")}
                className="absolute right-3 flex size-11 items-center justify-center rounded-full bg-white/10 text-white transition hover:bg-white/20"
              >
                <SalonIcon name="arrow" className="size-5" />
              </button>
            </>
          )}

          <figure
            onClick={(event) => event.stopPropagation()}
            className="max-h-full w-full max-w-3xl"
          >
            {isVideo(open) ? (
              <video
                key={open.id}
                src={open.url}
                controls
                autoPlay
                playsInline
                className="max-h-[78svh] w-full rounded-2xl bg-black object-contain"
              />
            ) : (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                key={open.id}
                {...photo(open, TAILLES.pleineLargeur)}
                alt={open.alt_text || t("galerie.alt", { salon: salonName })}
                className="max-h-[78svh] w-full rounded-2xl object-contain"
              />
            )}

            <figcaption className="mt-3 flex items-center justify-between gap-4 text-sm text-white/80">
              <span>{open.alt_text}</span>
              <span className="tabular shrink-0 text-white/60">
                {(openIndex ?? 0) + 1} / {assets.length}
              </span>
            </figcaption>
          </figure>
        </div>
      )}
    </>
  );
}
