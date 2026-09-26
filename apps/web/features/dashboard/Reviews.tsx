"use client";

/**
 * Avis reçus, côté salon.
 *
 * En lecture seule, et l'écran l'explique plutôt que de laisser deviner.
 * Un salon capable de retirer les avis qui le dérangent ne publierait que
 * des cinq étoiles, et la note cesserait d'informer qui que ce soit — donc
 * de valoir quelque chose pour lui. La modération appartient à l'équipe
 * plateforme, joignable en cas d'avis manifestement abusif.
 */

import { useMemo } from "react";

import { formatDate } from "@/lib/format";
import {
  Badge,
  Card,
  EmptyState,
  ErrorState,
  PageHeader,
  SectionTitle,
  Skeleton,
  StatTile,
} from "@/features/ui";
import { Icon } from "./icons";
import { useDashboard } from "./DashboardShell";
import { rows, useResource, type Page } from "./useResource";

interface Review {
  id: string;
  author_name: string;
  rating: number;
  detail: { field: string; label: string; rating: number }[];
  comment: string;
  status: "published" | "hidden";
  service_name: string;
  staff_member_name: string | null;
  booking_starts_at: string;
  created_at: string;
}

export function Reviews() {
  const { membership } = useDashboard();
  const tenantId = membership.tenant.id;
  const timeZone = membership.tenant.timezone;

  const reviews = useResource<Page<Review>>("/api/v1/reviews/", tenantId);
  const all = useMemo(() => rows(reviews.data), [reviews.data]);

  const published = all.filter((review) => review.status === "published");
  const average =
    published.length > 0
      ? published.reduce((total, review) => total + review.rating, 0) /
        published.length
      : null;

  // Répartition des notes : elle dit s'il s'agit d'un salon régulier ou d'un
  // salon qui alterne enthousiasme et déception.
  const spread = [5, 4, 3, 2, 1].map((score) => ({
    score,
    count: published.filter((review) => review.rating === score).length,
  }));

  return (
    <section>
      <PageHeader
        title="Avis"
        description="Ce que vos clientes disent après leur rendez-vous. Chaque avis est rattaché à une prestation réellement honorée."
      />

      {reviews.error && (
        <ErrorState>Impossible de charger les avis.</ErrorState>
      )}
      {reviews.data === null && !reviews.error && <Skeleton rows={3} />}

      {all.length === 0 && reviews.data !== null && (
        <EmptyState title="Aucun avis pour l'instant">
          Une demande d&apos;avis part automatiquement par e-mail quelques
          heures après chaque prestation terminée. Les premiers arriveront
          d&apos;eux-mêmes.
        </EmptyState>
      )}

      {published.length > 0 && (
        <>
          <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3 sm:gap-4">
            <StatTile
              label="Note moyenne"
              value={average ? `${average.toFixed(1)} / 5` : "—"}
              hint={`sur ${published.length} avis publié${published.length > 1 ? "s" : ""}`}
            />
            <StatTile
              label="Cinq étoiles"
              value={String(spread[0].count)}
              hint={
                published.length > 0
                  ? `${Math.round((spread[0].count / published.length) * 100)} % des avis`
                  : undefined
              }
            />
            <StatTile
              label="Trois étoiles ou moins"
              value={String(
                spread
                  .filter((row) => row.score <= 3)
                  .reduce((t, r) => t + r.count, 0),
              )}
              hint="à lire en priorité"
              tone={
                spread
                  .filter((row) => row.score <= 3)
                  .reduce((t, r) => t + r.count, 0) > 0
                  ? "danger"
                  : "neutral"
              }
            />
          </div>

          <Card className="mb-8">
            <SectionTitle>Répartition</SectionTitle>
            <ul className="space-y-2">
              {spread.map((row) => {
                const share =
                  published.length > 0
                    ? (row.count / published.length) * 100
                    : 0;
                return (
                  <li key={row.score} className="flex items-center gap-3">
                    <span className="tabular w-10 shrink-0 text-sm text-muted">
                      {row.score} ★
                    </span>
                    <span className="h-2 flex-1 overflow-hidden rounded-full bg-surface-muted">
                      <span
                        className="block h-full rounded-full bg-salon transition-[width] duration-500"
                        style={{ width: `${share}%` }}
                      />
                    </span>
                    <span className="tabular w-8 shrink-0 text-right text-sm text-muted">
                      {row.count}
                    </span>
                  </li>
                );
              })}
            </ul>
          </Card>
        </>
      )}

      <ul className="space-y-3">
        {all.map((review) => (
          <li key={review.id}>
            <Card className="lift">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="flex flex-wrap items-center gap-2">
                    <span className="flex items-center gap-0.5 text-salon">
                      {[1, 2, 3, 4, 5].map((step) => (
                        <Icon
                          key={step}
                          name="star"
                          className={`size-4 ${step <= review.rating ? "" : "opacity-25"}`}
                        />
                      ))}
                    </span>
                    <span className="font-medium text-ink">
                      {review.author_name}
                    </span>
                    {review.status === "hidden" && (
                      <Badge tone="warning">Masqué par la plateforme</Badge>
                    )}
                  </p>

                  <p className="mt-1 text-sm text-subtle">
                    {review.service_name}
                    {review.staff_member_name &&
                      ` · ${review.staff_member_name}`}
                    {" · "}
                    {formatDate(review.booking_starts_at, timeZone)}
                  </p>

                  {/*
                    Le détail par critère, sur deux colonnes dès le téléphone.

                    C'est la partie exploitable de l'avis. « 3 sur 5 » ne dit
                    pas quoi réparer ; « ponctualité 2, résultat 5 » dit
                    exactement quoi changer demain matin — et ce n'est pas la
                    même personne qui s'en occupe.
                  */}
                  {review.detail.length > 0 && (
                    <dl className="mt-3 grid max-w-xl grid-cols-2 gap-x-4 gap-y-1.5">
                      {review.detail.map((critere) => (
                        <div
                          key={critere.field}
                          className="flex items-center justify-between gap-2 border-b border-line pb-1.5"
                        >
                          <dt className="min-w-0 truncate text-xs text-muted">
                            {critere.label}
                          </dt>
                          <dd
                            className="flex shrink-0 items-center gap-0.5 text-salon"
                            aria-label={`${critere.rating} sur 5`}
                          >
                            {[1, 2, 3, 4, 5].map((step) => (
                              <Icon
                                key={step}
                                name="star"
                                className={`size-3 ${step <= critere.rating ? "" : "opacity-25"}`}
                              />
                            ))}
                          </dd>
                        </div>
                      ))}
                    </dl>
                  )}

                  {review.comment && (
                    <p className="mt-3 max-w-2xl leading-relaxed text-ink">
                      {review.comment}
                    </p>
                  )}
                </div>
              </div>
            </Card>
          </li>
        ))}
      </ul>

      {all.length > 0 && (
        <p className="mt-6 max-w-2xl text-sm leading-relaxed text-muted">
          Vous ne pouvez ni modifier ni supprimer un avis : c&apos;est ce qui
          leur donne leur valeur aux yeux de vos clientes. Un avis manifestement
          abusif peut être signalé à l&apos;équipe Beauty Salon, qui décide de
          le retirer.
        </p>
      )}
    </section>
  );
}
