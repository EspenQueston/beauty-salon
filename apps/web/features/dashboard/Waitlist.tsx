"use client";

/**
 * La file de rappel du salon.
 *
 * Elle ne réserve rien et ne distribue rien automatiquement : c'est une
 * liste de gens à rappeler. Attribuer un créneau libéré à la première
 * inscrite donnerait des rendez-vous à des clientes qui ne les attendent
 * plus — et personne ne s'y présenterait.
 *
 * L'ordre d'affichage est l'ordre d'arrivée. C'est le seul défendable au
 * téléphone : « vous étiez la troisième » est une phrase qu'on peut dire.
 */

import { dashboardFetch } from "@/lib/dashboard";
import {
  Badge,
  Card,
  EmptyState,
  ErrorState,
  GhostButton,
  PageHeader,
  Skeleton,
} from "@/features/ui";
import { useToast } from "@/features/ui/Toast";
import { useDashboard } from "./DashboardShell";
import { rows, useResource, type Page } from "./useResource";

interface Entry {
  id: string;
  service_name: string;
  staff_member_name: string;
  full_name: string;
  phone: string;
  email: string;
  preferred_from: string;
  preferred_to: string;
  note: string;
  status: "waiting" | "contacted" | "booked" | "closed";
  contacted_at: string | null;
  created_at: string;
}

export function Waitlist() {
  const { membership } = useDashboard();
  const toast = useToast();
  const tenantId = membership.tenant.id;
  const timeZone = membership.tenant.timezone;
  const canEdit = ["owner", "manager", "receptionist"].includes(
    membership.role,
  );

  const entries = useResource<Page<Entry>>("/api/v1/waitlist/", tenantId);
  const list = rows(entries.data);

  const dateFormat = new Intl.DateTimeFormat("fr-FR", {
    day: "numeric",
    month: "short",
    timeZone,
  });

  async function act(
    entry: Entry,
    path: string,
    body: object,
    success: string,
  ) {
    const ok = await toast.run(
      () =>
        dashboardFetch(
          `/api/v1/waitlist/${entry.id}/${path}/`,
          { method: "POST", body: JSON.stringify(body) },
          tenantId,
        ),
      { success },
    );
    if (ok) entries.reload();
  }

  return (
    <section>
      <PageHeader
        title="Liste d'attente"
        description="Les clientes à rappeler quand une place se libère. Rien n'est réservé pour elles."
      />

      {entries.error && (
        <ErrorState>Impossible de charger la liste.</ErrorState>
      )}
      {entries.data === null && !entries.error && <Skeleton rows={3} />}

      {entries.data !== null && list.length === 0 && (
        <EmptyState title="Personne n'attend">
          Quand votre agenda est plein, vos clientes peuvent demander à être
          rappelées depuis votre mini-site. Elles apparaîtront ici.
        </EmptyState>
      )}

      <ol className="space-y-2.5">
        {list.map((entry, position) => (
          <li key={entry.id}>
            <Card>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="flex flex-wrap items-center gap-2 font-medium text-ink">
                    <span className="tabular text-subtle">#{position + 1}</span>
                    {entry.full_name}
                    {entry.status === "contacted" && (
                      <Badge tone="neutral">Contactée</Badge>
                    )}
                  </p>
                  <p className="mt-0.5 text-sm text-muted">
                    {entry.service_name}
                    {entry.staff_member_name && ` · ${entry.staff_member_name}`}
                  </p>
                  <p className="mt-0.5 text-sm text-subtle">
                    Souhaite entre le{" "}
                    {dateFormat.format(new Date(entry.preferred_from))} et le{" "}
                    {dateFormat.format(new Date(entry.preferred_to))}
                  </p>
                  {entry.note && (
                    <p className="mt-1 border-l-2 border-line-strong pl-2 text-sm italic text-muted">
                      {entry.note}
                    </p>
                  )}
                </div>

                {/* Le téléphone est le geste : il est cliquable, pas
                    seulement affiché. */}
                <div className="flex flex-col items-start gap-1.5 sm:items-end">
                  <a
                    href={`tel:${entry.phone}`}
                    className="tabular text-sm font-medium text-salon hover:underline"
                  >
                    {entry.phone}
                  </a>
                  {entry.email && (
                    <a
                      href={`mailto:${entry.email}`}
                      className="text-xs text-muted hover:underline"
                    >
                      {entry.email}
                    </a>
                  )}
                </div>
              </div>

              {canEdit && (
                <div className="mt-3 flex flex-wrap gap-1.5 border-t border-line pt-3">
                  {entry.status === "waiting" && (
                    <GhostButton
                      type="button"
                      onClick={() =>
                        act(
                          entry,
                          "contacted",
                          {},
                          `${entry.full_name} marquée comme contactée.`,
                        )
                      }
                    >
                      J&apos;ai rappelé
                    </GhostButton>
                  )}
                  <GhostButton
                    type="button"
                    onClick={() =>
                      act(
                        entry,
                        "close",
                        { booked: true },
                        "Rendez-vous pris : demande classée.",
                      )
                    }
                  >
                    Rendez-vous pris
                  </GhostButton>
                  <GhostButton
                    type="button"
                    onClick={() => act(entry, "close", {}, "Demande classée.")}
                  >
                    Classer
                  </GhostButton>
                </div>
              )}
            </Card>
          </li>
        ))}
      </ol>
    </section>
  );
}
