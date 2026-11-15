/**
 * Avis publiés, tels qu'une visiteuse les lit.
 *
 * Ils sont chargés côté serveur avec le reste de la page : une cliente qui
 * hésite ne doit pas voir un bloc vide se remplir après coup, c'est
 * exactement le moment où elle referme l'onglet.
 *
 * Le bloc n'apparaît pas s'il n'y a aucun avis. Un « Aucun avis pour le
 * moment » affiché en grand dessert le salon plus qu'il ne l'aide — le
 * silence est plus neutre que le vide annoncé.
 */

import { useTranslations } from "next-intl";

import { formatDate } from "@/lib/format";
import type { PublicReview, RatingSummary } from "@/lib/types";
import { Stars } from "./Stars";
import { SURFACE } from "./ui";
import { Reveal } from "@/features/ui/Reveal";
import { delaiCascade } from "./effets";
import { CommentaireAvis } from "./CommentaireAvis";

export function RatingBadge({ rating }: { rating: RatingSummary }) {
  if (rating.average == null || rating.count === 0) return null;

  return (
    <span className="inline-flex items-center gap-2 rounded-full bg-white/15 px-3.5 py-1.5 text-sm backdrop-blur">
      <Stars value={rating.average} size="size-3.5" />
      <span className="tabular font-semibold">{rating.average.toFixed(1)}</span>
      <span className="opacity-80">· {rating.count} avis</span>
    </span>
  );
}

export function ReviewList({
  reviews,
  rating,
  timeZone,
}: {
  reviews: PublicReview[];
  rating: RatingSummary;
  timeZone: string;
}) {
  const t = useTranslations("salon");
  if (reviews.length === 0) return null;

  return (
    <div>
      {rating.average != null && (
        <div
          className={`${SURFACE} mb-4 flex flex-wrap items-center gap-x-6 gap-y-2.5 p-3.5 sm:mb-6 sm:gap-y-3 sm:p-5`}
        >
          <div className="flex items-baseline gap-1.5 sm:gap-2">
            <span className="tabular text-3xl font-semibold text-[var(--site-ink)] sm:text-4xl">
              {rating.average.toFixed(1)}
            </span>
            <span className="text-sm text-[var(--site-muted)] sm:text-base">/ 5</span>
          </div>
          <div>
            <Stars value={rating.average} size="size-4 sm:size-5" />
            <p className="mt-1 text-xs text-[var(--site-muted)] sm:text-sm">
              {t("hero.avis", { n: rating.count })}
            </p>
          </div>
          <p className="w-full text-[0.7rem] leading-relaxed text-[var(--site-subtle)] sm:ml-auto sm:w-auto sm:max-w-xs sm:text-xs">
            {t("avisGarantie")}
          </p>
        </div>
      )}

      {/*
        Deux colonnes sur téléphone, comme les autres grilles du mini-site ;
        quatre sur grand écran.

        Un avis porte un texte libre : serré dans une demi-largeur de
        téléphone, un commentaire de deux phrases donnerait une carte deux
        fois plus haute que sa voisine. Il y est donc replié à quelques lignes
        avec « Lire la suite » (`CommentaireAvis`), et les cartes restent de
        hauteur comparable.
      */}
      <ul className="grid grid-cols-2 gap-2.5 sm:gap-3 lg:grid-cols-4">
        {reviews.map((review, index) => (
          <Reveal as="li" key={review.id} delay={delaiCascade(index)}>
            {/*
              Traitement en citation plutôt qu'en carte de commentaire.

              Le guillemet ouvrant, en grand et dans la couleur du salon,
              dit avant lecture que ces mots ne sont pas ceux du salon mais
              ceux d'une cliente. C'est toute la valeur d'un avis, et une
              carte neutre la laissait deviner.

              Il est décoratif : le texte se lit sans lui, et un lecteur
              d'écran n'annonce pas un guillemet.
            */}
            <article
              className={`${SURFACE} lift relative flex h-full flex-col p-3 sm:p-5`}
            >
              <span
                aria-hidden
                className="pointer-events-none absolute right-2.5 top-1 select-none font-serif text-4xl leading-none text-[var(--salon-primary)]/15 sm:right-3 sm:text-6xl"
              >
                &ldquo;
              </span>

              <Stars value={review.rating} size="size-3 sm:size-4" />

              {/*
                Les deux critères les plus bas, et eux seuls.

                Cinq lignes de détail sur une carte de témoignage la
                transformeraient en tableau, et personne ne lit un tableau sur
                une vitrine. Les deux plus basses notes sont ce qu'une future
                cliente cherche réellement : ce sur quoi elle risque d'être
                déçue. Les taire serait de la mise en scène.
              */}
              {review.detail.length > 0 && (
                <ul className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 sm:mt-2">
                  {[...review.detail]
                    .sort((a, b) => a.rating - b.rating)
                    .slice(0, 2)
                    .map((critere) => (
                      <li
                        key={critere.field}
                        className="flex items-center gap-1 text-[0.62rem] text-[var(--site-subtle)] sm:text-[0.7rem]"
                      >
                        <span>{critere.label}</span>
                        <Stars value={critere.rating} size="size-2.5" />
                      </li>
                    ))}
                </ul>
              )}

              {review.comment ? <CommentaireAvis texte={review.comment} /> : <div className="flex-1" />}

              <footer className="mt-3 border-t border-[var(--site-line)] pt-2.5 sm:mt-4 sm:pt-3">
                <p className="truncate text-[0.8rem] font-medium text-[var(--site-ink)] sm:text-sm">
                  {review.author_name}
                </p>
                <p className="mt-0.5 line-clamp-2 text-[0.66rem] text-[var(--site-subtle)] sm:text-xs">
                  {review.service_name} ·{" "}
                  {formatDate(review.created_at, timeZone)}
                </p>
              </footer>
            </article>
          </Reveal>
        ))}
      </ul>
    </div>
  );
}
