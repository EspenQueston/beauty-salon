"use client";

/**
 * Les prestations qui ne rentrent dans aucune plage — et celles qui n'en
 * remplissent qu'une partie.
 *
 * ---------------------------------------------------------------------------
 * Le silence que cet écran remplace
 * ---------------------------------------------------------------------------
 *
 * Un salon déclare ouvrir de 9 h 30 à 13 h, puis ne reçoit jamais une seule
 * réservation du matin sur sa prestation phare. Rien ne le lui dit. Il
 * conclut à une panne, ou pire, à des clientes qui ne viennent plus.
 *
 * La cause est arithmétique : une pose de 4 h n'entre pas dans une matinée
 * de 3 h 30. Le moteur a raison de ne rien proposer — c'est l'écran qui
 * avait tort de se taire.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi ici et pas à la réservation
 * ---------------------------------------------------------------------------
 *
 * Parce que c'est ici que ça se corrige. Prévenir la cliente qu'il n'y a
 * rien le matin ne lui sert à rien : elle ne peut ni allonger la matinée ni
 * raccourcir la pose. Le salon, lui, peut ouvrir trente minutes plus tôt.
 *
 * ---------------------------------------------------------------------------
 * Le calcul
 * ---------------------------------------------------------------------------
 *
 * Pour chaque prestation active, on compare sa durée à la longueur de chaque
 * plage. Deux niveaux de gravité, et un seul mérite d'alarmer :
 *
 *   - **aucune plage ne l'accueille** : la prestation est invisible à la
 *     réservation. C'est un défaut, il s'affiche en ambre ;
 *   - **certaines plages seulement** : c'est souvent voulu — on ne pose pas
 *     des tresses de 4 h en fin d'après-midi. Mention discrète, pas d'alerte.
 */

import { useTranslations } from "next-intl";
import { useMemo } from "react";

import { formatDuration } from "@/lib/format";
import { Badge, Card, SectionTitle } from "@/features/ui";
import { useFormats } from "./formats";
import { rows, useResource, type Page } from "./useResource";

interface Hours {
  id: string;
  staff_member: string | null;
  weekday: number;
  starts_at: string;
  ends_at: string;
}

interface Service {
  id: string;
  name: string;
  duration_minutes: number;
  active: boolean;
}

/** « lundi »… / « Monday »…, du lundi (0) au dimanche (6), tirés d'Intl. */
function nomsDesJours(region: string): string[] {
  const format = new Intl.DateTimeFormat(region, { weekday: "long", timeZone: "UTC" });
  // Le 5 janvier 2026 est un lundi.
  return Array.from({ length: 7 }, (_, i) => format.format(new Date(Date.UTC(2026, 0, 5 + i))));
}

type Traduire = ReturnType<typeof useTranslations>;

/** « 09:30:00 » → minutes depuis minuit. */
function minutes(value: string): number {
  const [h, m] = value.split(":");
  return Number(h) * 60 + Number(m);
}

/**
 * Regroupe des jours en une tournure lisible, préposition comprise.
 *
 * La préposition fait partie du regroupement : « du mardi au samedi » et
 * « le mardi » ne prennent pas la même, et la coller dans le gabarit
 * produisait « les mardi à samedi ».
 */
function humanDays(days: number[], t: Traduire, region: string): string {
  const DAYS = nomsDesJours(region);
  const sorted = [...new Set(days)].sort((a, b) => a - b);
  if (sorted.length === 0) return "";
  if (sorted.length === 1) return t("jours.un", { jour: DAYS[sorted[0]] });

  // Suite continue d'au moins trois jours : on la dit comme telle.
  const continuous = sorted.every(
    (day, index) => index === 0 || day === sorted[index - 1] + 1,
  );
  if (continuous && sorted.length > 2) {
    return t("jours.plage", {
      debut: DAYS[sorted[0]],
      fin: DAYS[sorted[sorted.length - 1]],
    });
  }

  const liste = new Intl.ListFormat(region, { type: "conjunction" }).format(
    sorted.map((day) => DAYS[day]),
  );
  return t("jours.liste", { liste });
}

export function ServiceFit({ tenantId }: { tenantId: string }) {
  const t = useTranslations("pro.prestations.compatibilite");
  const { region } = useFormats();
  const hours = useResource<Page<Hours>>("/api/v1/business-hours/", tenantId);
  const services = useResource<Page<Service>>(
    "/api/v1/services/?page_size=200",
    tenantId,
  );

  const report = useMemo(() => {
    const blocks = rows(hours.data)
      .filter((row) => row.staff_member === null)
      .map((row) => ({
        weekday: row.weekday,
        length: minutes(row.ends_at) - minutes(row.starts_at),
        label: `${row.starts_at.slice(0, 5)}–${row.ends_at.slice(0, 5)}`,
      }));

    if (blocks.length === 0) return null;

    const longest = Math.max(...blocks.map((block) => block.length));

    return rows(services.data)
      .filter((service) => service.active)
      .map((service) => {
        const refused = blocks.filter(
          (block) => block.length < service.duration_minutes,
        );
        return {
          service,
          refused,
          // Aucune plage ne l'accueille : la prestation est introuvable à la
          // réservation, quel que soit le jour.
          impossible: service.duration_minutes > longest,
          refusedDays: humanDays(refused.map((block) => block.weekday), t, region),
          sameBlock: new Set(refused.map((block) => block.label)).size === 1,
        };
      })
      .filter((entry) => entry.refused.length > 0)
      .sort((a, b) => Number(b.impossible) - Number(a.impossible));
  }, [hours.data, services.data, t, region]);

  // Rien à signaler : l'écran reste silencieux plutôt que d'afficher une
  // carte vide qui ne dit que « tout va bien ».
  if (!report || report.length === 0) return null;

  const blocking = report.filter((entry) => entry.impossible);

  return (
    <Card className="mt-6">
      <SectionTitle>{t("titre")}</SectionTitle>
      <p className="-mt-2 mb-4 text-sm text-muted">{t("intro")}</p>

      {/* Deux colonnes dès le téléphone : ces lignes sont courtes, et une
          seule colonne allongerait la liste sans rien gagner. */}
      <ul className="grid grid-cols-2 gap-2.5">
        {report.map((entry) => (
          <li
            key={entry.service.id}
            className={`rounded-xl border p-3 ${
              entry.impossible
                ? "border-l-4 border-l-amber-500 border-y-line border-r-line bg-surface"
                : "border-line bg-surface-muted/40"
            }`}
          >
            <p className="flex flex-wrap items-center gap-1.5 text-sm font-medium text-ink">
              <span className="min-w-0 truncate">{entry.service.name}</span>
              <span className="tabular shrink-0 text-xs font-normal text-subtle">
                {formatDuration(entry.service.duration_minutes)}
              </span>
            </p>

            {entry.impossible ? (
              <>
                <Badge tone="warning">{t("jamais")}</Badge>
                <p className="mt-1.5 text-xs leading-relaxed text-muted">{t("jamaisAide")}</p>
              </>
            ) : (
              <p className="mt-1 text-xs leading-relaxed text-muted">
                {/* La plage n'est nommée que si elle est la même partout :
                    « 09:30–13:00 et similaires » ne disait rien d'utile
                    quand les plages différaient réellement. */}
                {entry.sameBlock
                  ? t("pasProposeePlage", {
                      jours: entry.refusedDays,
                      plage: entry.refused[0].label,
                    })
                  : t("pasProposee", { jours: entry.refusedDays })}
              </p>
            )}
          </li>
        ))}
      </ul>

      {blocking.length > 0 && (
        <p className="mt-3.5 border-t border-line pt-3 text-xs text-muted">
          {t.rich("conseil", {
            ecran: (texte) => <span className="text-ink">{texte}</span>,
          })}
        </p>
      )}
    </Card>
  );
}
