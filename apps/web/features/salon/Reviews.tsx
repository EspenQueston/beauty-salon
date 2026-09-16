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

import { formatDate } from "@/lib/format";
import type { PublicReview, RatingSummary } from "@/lib/types";
import { Stars } from "./Stars";
import { SURFACE } from "./ui";
import { Reveal } from "@/features/ui/Reveal";

export function RatingBadge({ rating }: { rating: RatingSummary }) {
  if (rating.average == null || rating.count === 0) return null;

  return (
    <span className="inline-flex items-center gap-2 rounded-full bg-white/15 px-3.5 py-1.5 text-sm backdrop-blur">
      <Stars value={rating.average} size="size-3.5" />
      <span className="tabular font-semibold">{rating.average.toFixed(1)}</span>
      <span className="opacity-80">
        · {rating.count} avis
      </span>
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
  if (reviews.length === 0) return null;

  return (
    <div>
      {rating.average != null && (
        <div
          className={`${SURFACE} mb-6 flex flex-wrap items-center gap-x-6 gap-y-3 p-5`}
        >
          <div className="flex items-baseline gap-2">
            <span className="tabular text-4xl font-semibold text-[var(--site-ink)]">
              {rating.average.toFixed(1)}
            </span>
            <span className="text-[var(--site-muted)]">/ 5</span>
          </div>
          <div>
            <Stars value={rating.average} size="size-5" />
            <p className="mt-1 text-sm text-[var(--site-muted)]">
              {rating.count} avis vérifié{rating.count > 1 ? "s" : ""}
            </p>
          </div>
          <p className="ml-auto max-w-xs text-xs leading-relaxed text-[var(--site-subtle)]">
            Chaque avis est rattaché à un rendez-vous réellement honoré. Le
            salon ne peut ni les modifier ni les supprimer.
          </p>
        </div>
      )}

      {/*
        Quatre colonnes sur grand écran, une seule sur téléphone.

        C'est la seule grille de cartes du mini-site qui reste à une colonne
        sous 640 px, et c'est délibéré : un avis porte un texte libre, non
        tronqué. Serré dans une demi-largeur de téléphone, un commentaire de
        deux phrases donne quinze lignes et une carte deux fois plus haute que
        sa voisine. Les cartes de prestation et d'équipe, elles, tiennent des
        libellés courts — d'où les deux colonnes partout ailleurs.

        Le commentaire précédent annonçait « deux colonnes dès le petit
        écran » au-dessus d'un `grid-cols-1` : il décrivait une intention, pas
        le code.
      */}
      <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {reviews.map((review, index) => (
          <Reveal as="li" key={review.id} delay={Math.min(index, 6) * 70}>
            {/*
              Traitement en citation plutôt qu'en carte de commentaire.

              Le guillemet ouvrant, en grand et dans la couleur du salon,
              dit avant lecture que ces mots ne sont pas ceux du salon mais
              ceux d'une cliente. C'est toute la valeur d'un avis, et une
              carte neutre la laissait deviner.

              Il est décoratif : le texte se lit sans lui, et un lecteur
              d'écran n'annonce pas un guillemet.
            */}
            <article className={`${SURFACE} lift relative flex h-full flex-col p-4 sm:p-5`}>
              <span
                aria-hidden
                className="pointer-events-none absolute right-3 top-1 select-none font-serif text-5xl leading-none text-[var(--salon-primary)]/15 sm:text-6xl"
              >
                &ldquo;
              </span>

              <Stars value={review.rating} />

              {/*
                Les deux critères les plus bas, et eux seuls.

                Cinq lignes de détail sur une carte de témoignage la
                transformeraient en tableau, et personne ne lit un tableau sur
                une vitrine. Les deux plus basses notes sont ce qu'une future
                cliente cherche réellement : ce sur quoi elle risque d'être
                déçue. Les taire serait de la mise en scène.
              */}
              {review.detail.length > 0 && (
                <ul className="mt-2 flex flex-wrap gap-x-3 gap-y-1">
                  {[...review.detail]
                    .sort((a, b) => a.rating - b.rating)
                    .slice(0, 2)
                    .map((critere) => (
                      <li
                        key={critere.field}
                        className="flex items-center gap-1 text-[0.7rem] text-[var(--site-subtle)]"
                      >
                        <span>{critere.label}</span>
                        <Stars value={critere.rating} size="size-2.5" />
                      </li>
                    ))}
                </ul>
              )}

              {review.comment && (
                <p className="relative mt-3 flex-1 text-[0.85rem] leading-relaxed text-[var(--site-ink)] sm:text-sm">
                  {review.comment}
                </p>
              )}

              <footer className="mt-4 border-t border-[var(--site-line)] pt-3">
                <p className="text-sm font-medium text-[var(--site-ink)]">
                  {review.author_name}
                </p>
                <p className="mt-0.5 text-xs text-[var(--site-subtle)]">
                  {review.service_name} · {formatDate(review.created_at, timeZone)}
                </p>
              </footer>
            </article>
          </Reveal>
        ))}
      </ul>
    </div>
  );
}
