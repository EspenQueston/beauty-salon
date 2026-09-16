"use client";

/**
 * Horaires d'ouverture, congés et fermetures exceptionnelles.
 *
 * Deux notions distinctes, volontairement séparées à l'écran :
 *   - la grille hebdomadaire, qui se répète ;
 *   - les exceptions, qui visent une date précise.
 *
 * Une ligne sans prestataire vaut pour tout le salon ; une ligne nominative
 * prime sur celle du salon pour la personne concernée.
 */

import { useState } from "react";

import { dashboardFetch } from "@/lib/dashboard";
import { shortTime, weekdayLabel } from "@/lib/format";
import {
  Badge,
  Button,
  Card,
  DangerButton,
  EmptyState,
  ErrorState,
  Field,
  GhostButton,
  PageHeader,
  SectionTitle,
  Skeleton,
  inputClass,
} from "@/features/ui";
import { useToast } from "@/features/ui/Toast";
import { Icon } from "./icons";
import { useDashboard } from "./DashboardShell";
import { ServiceFit } from "./ServiceFit";
import { rows, useResource, type Page } from "./useResource";

interface BusinessHours {
  id: string;
  staff_member: string | null;
  weekday: number;
  starts_at: string;
  ends_at: string;
}

interface ScheduleException {
  id: string;
  staff_member: string | null;
  kind: "blocked" | "leave" | "extra_opening";
  starts_at: string;
  ends_at: string;
  reason: string;
}

interface StaffMember {
  id: string;
  name: string;
}

const KINDS = [
  { value: "leave", label: "Congé", tone: "info" as const },
  { value: "blocked", label: "Créneau bloqué", tone: "warning" as const },
  { value: "extra_opening", label: "Ouverture exceptionnelle", tone: "success" as const },
];

const KIND_BY_VALUE = Object.fromEntries(KINDS.map((kind) => [kind.value, kind]));

export function Schedule() {
  const { membership } = useDashboard();
  const tenantId = membership.tenant.id;
  const timeZone = membership.tenant.timezone;
  const canEdit = ["owner", "manager"].includes(membership.role);

  const hours = useResource<Page<BusinessHours>>("/api/v1/business-hours/", tenantId);
  const staff = useResource<Page<StaffMember>>(
    "/api/v1/staff-members/?page_size=100",
    tenantId,
  );
  const exceptions = useResource<Page<ScheduleException>>(
    `/api/v1/availability-exceptions/?from=${new Date().toISOString()}`,
    tenantId,
  );

  const hourRows = rows(hours.data);
  const staffRows = rows(staff.data);

  return (
    <section>
      <PageHeader
        title="Horaires"
        description={`Ce sont ces heures qui décident des créneaux proposés à vos clientes. Heure locale du salon (${timeZone}).`}
      />

      {(hours.error || exceptions.error) && (
        <ErrorState>Impossible de charger les horaires.</ErrorState>
      )}

      {hours.data === null && !hours.error ? (
        <Skeleton rows={4} />
      ) : (
        <WeeklyGrid
          tenantId={tenantId}
          hours={hourRows}
          staff={staffRows}
          canEdit={canEdit}
          onChange={hours.reload}
        />
      )}

      {/* Juste sous la grille : c'est en regardant ses plages qu'on
          comprend pourquoi une prestation n'apparaît nulle part, et c'est
          ici qu'on la corrige. */}
      <ServiceFit tenantId={tenantId} />

      <ExceptionList
        tenantId={tenantId}
        exceptions={rows(exceptions.data)}
        loaded={exceptions.data !== null}
        staff={staffRows}
        timeZone={timeZone}
        canEdit={canEdit}
        onChange={exceptions.reload}
      />

      {!canEdit && (
        <p className="mt-6 text-sm text-muted">
          Seuls le propriétaire et le gérant peuvent modifier les horaires.
        </p>
      )}
    </section>
  );
}

function WeeklyGrid({
  tenantId,
  hours,
  staff,
  canEdit,
  onChange,
}: {
  tenantId: string;
  hours: BusinessHours[];
  staff: StaffMember[];
  canEdit: boolean;
  onChange: () => void;
}) {
  const toast = useToast();
  const [scope, setScope] = useState("");

  const visible = hours.filter((row) => (row.staff_member ?? "") === scope);
  const openDays = new Set(visible.map((row) => row.weekday)).size;

  async function add(weekday: number) {
    const ok = await toast.run(
      () =>
        dashboardFetch(
          "/api/v1/business-hours/",
          {
            method: "POST",
            body: JSON.stringify({
              weekday,
              starts_at: "09:00",
              ends_at: "18:00",
              staff_member: scope || null,
            }),
          },
          tenantId,
        ),
      { success: `${weekdayLabel(weekday)} : 09:00 – 18:00 ajouté.` },
    );
    if (ok) onChange();
  }

  async function update(
    row: BusinessHours,
    field: "starts_at" | "ends_at",
    value: string,
  ) {
    if (!value || shortTime(row[field]) === value) return;
    await toast.run(
      () =>
        dashboardFetch(
          `/api/v1/business-hours/${row.id}/`,
          { method: "PATCH", body: JSON.stringify({ [field]: value }) },
          tenantId,
        ),
      { success: `${weekdayLabel(row.weekday)} mis à jour.` },
    );
    // Recharge dans les deux cas : après un refus, le champ doit retrouver
    // la valeur réellement enregistrée plutôt que la saisie rejetée.
    onChange();
  }

  async function remove(row: BusinessHours) {
    const ok = await toast.run(
      () =>
        dashboardFetch(
          `/api/v1/business-hours/${row.id}/`,
          { method: "DELETE" },
          tenantId,
        ),
      { success: `Plage du ${weekdayLabel(row.weekday).toLowerCase()} supprimée.` },
    );
    if (ok) onChange();
  }

  return (
    <Card className="mb-8">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="font-semibold text-ink">Semaine type</h2>
          <p className="mt-0.5 text-sm text-muted">
            {openDays === 0
              ? "Aucun jour ouvert : aucun créneau ne sera proposé."
              : `${openDays} jour${openDays > 1 ? "s" : ""} ouvert${openDays > 1 ? "s" : ""} sur 7.`}
          </p>
        </div>

        {staff.length > 0 && (
          <label className="text-sm">
            <span className="mb-1.5 block font-medium text-ink">Appliquer à</span>
            <select
              value={scope}
              onChange={(event) => setScope(event.target.value)}
              className={inputClass}
            >
              <option value="">Tout le salon</option>
              {staff.map((member) => (
                <option key={member.id} value={member.id}>
                  {member.name}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      {scope && (
        <p className="mb-4 rounded-lg bg-info-bg px-3 py-2 text-sm text-info">
          Ces horaires remplacent ceux du salon pour cette personne.
        </p>
      )}

      <ul className="divide-y divide-line">
        {[0, 1, 2, 3, 4, 5, 6].map((weekday) => {
          const dayRows = visible
            .filter((row) => row.weekday === weekday)
            .sort((a, b) => a.starts_at.localeCompare(b.starts_at));

          return (
            <li
              key={weekday}
              className="flex flex-wrap items-center gap-3 py-3 first:pt-0 last:pb-0"
            >
              <span className="w-24 shrink-0 text-sm font-medium text-ink">
                {weekdayLabel(weekday)}
              </span>

              {dayRows.length === 0 && (
                <span className="text-sm text-subtle">Fermé</span>
              )}

              {dayRows.map((row) => (
                <span
                  // La valeur serveur fait partie de la clé : après un refus,
                  // le champ est remonté et retrouve l'heure enregistrée au
                  // lieu de conserver la saisie rejetée.
                  key={`${row.id}:${row.starts_at}:${row.ends_at}`}
                  className="flex items-center gap-1.5 rounded-lg bg-surface-muted px-2 py-1"
                >
                  <input
                    type="time"
                    defaultValue={shortTime(row.starts_at)}
                    onBlur={(event) => update(row, "starts_at", event.target.value)}
                    disabled={!canEdit}
                    aria-label={`Ouverture du ${weekdayLabel(weekday).toLowerCase()}`}
                    className="tabular rounded-md border border-line bg-surface px-2 py-1 text-sm text-ink"
                  />
                  <span className="text-subtle">–</span>
                  <input
                    type="time"
                    defaultValue={shortTime(row.ends_at)}
                    onBlur={(event) => update(row, "ends_at", event.target.value)}
                    disabled={!canEdit}
                    aria-label={`Fermeture du ${weekdayLabel(weekday).toLowerCase()}`}
                    className="tabular rounded-md border border-line bg-surface px-2 py-1 text-sm text-ink"
                  />
                  {canEdit && (
                    <button
                      type="button"
                      onClick={() => remove(row)}
                      aria-label={`Supprimer la plage du ${weekdayLabel(weekday).toLowerCase()}`}
                      className="rounded px-1 text-lg leading-none text-subtle transition hover:text-danger"
                    >
                      ×
                    </button>
                  )}
                </span>
              ))}

              {canEdit && (
                <button
                  type="button"
                  onClick={() => add(weekday)}
                  className="ml-auto inline-flex items-center gap-1 rounded-lg px-2 py-1 text-sm font-medium text-salon transition hover:bg-salon-soft"
                >
                  <Icon name="plus" className="size-3.5" />
                  plage
                </button>
              )}
            </li>
          );
        })}
      </ul>

      <p className="mt-4 text-xs text-subtle">
        Deux plages sur un même jour créent une pause : 09:00–12:00 et
        14:00–18:00 ferment le déjeuner.
      </p>
    </Card>
  );
}

function ExceptionList({
  tenantId,
  exceptions,
  loaded,
  staff,
  timeZone,
  canEdit,
  onChange,
}: {
  tenantId: string;
  exceptions: ScheduleException[];
  loaded: boolean;
  staff: StaffMember[];
  timeZone: string;
  canEdit: boolean;
  onChange: () => void;
}) {
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState(false);
  const empty = {
    kind: "leave",
    staff_member: "",
    start_date: "",
    end_date: "",
    reason: "",
  };
  const [form, setForm] = useState(empty);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setPending(true);

    const ok = await toast.run(
      () =>
        dashboardFetch(
          "/api/v1/availability-exceptions/",
          {
            method: "POST",
            body: JSON.stringify({
              kind: form.kind,
              staff_member: form.staff_member || null,
              // Journées entières : du début du premier jour à la fin du dernier.
              starts_at: `${form.start_date}T00:00:00`,
              ends_at: `${form.end_date || form.start_date}T23:59:00`,
              reason: form.reason,
            }),
          },
          tenantId,
        ),
      {
        success: `${KIND_BY_VALUE[form.kind]?.label ?? "Exception"} enregistré. Les créneaux concernés ne sont plus proposés.`,
      },
    );

    setPending(false);
    if (ok) {
      setOpen(false);
      setForm(empty);
      onChange();
    }
  }

  async function remove(exception: ScheduleException) {
    const ok = await toast.run(
      () =>
        dashboardFetch(
          `/api/v1/availability-exceptions/${exception.id}/`,
          { method: "DELETE" },
          tenantId,
        ),
      { success: "Exception supprimée." },
    );
    if (ok) onChange();
  }

  const dateFormat = new Intl.DateTimeFormat("fr-FR", {
    day: "numeric",
    month: "long",
    timeZone,
  });

  return (
    <div>
      <SectionTitle
        action={
          canEdit && (
            <GhostButton type="button" onClick={() => setOpen((value) => !value)}>
              {open ? "Fermer" : "Ajouter"}
            </GhostButton>
          )
        }
      >
        Congés et fermetures à venir
      </SectionTitle>

      {open && (
        <Card className="mb-4">
          <form onSubmit={submit}>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Type">
                <select
                  value={form.kind}
                  onChange={(event) => setForm({ ...form, kind: event.target.value })}
                  className={inputClass}
                >
                  {KINDS.map((kind) => (
                    <option key={kind.value} value={kind.value}>
                      {kind.label}
                    </option>
                  ))}
                </select>
              </Field>

              <Field label="Concerne">
                <select
                  value={form.staff_member}
                  onChange={(event) =>
                    setForm({ ...form, staff_member: event.target.value })
                  }
                  className={inputClass}
                >
                  <option value="">Tout le salon</option>
                  {staff.map((member) => (
                    <option key={member.id} value={member.id}>
                      {member.name}
                    </option>
                  ))}
                </select>
              </Field>

              <Field label="Du">
                <input
                  type="date"
                  value={form.start_date}
                  onChange={(event) =>
                    setForm({ ...form, start_date: event.target.value })
                  }
                  required
                  className={inputClass}
                />
              </Field>

              <Field label="Au" hint="Laissez vide pour une seule journée.">
                <input
                  type="date"
                  value={form.end_date}
                  min={form.start_date || undefined}
                  onChange={(event) => setForm({ ...form, end_date: event.target.value })}
                  className={inputClass}
                />
              </Field>

              <Field
                label="Motif"
                hint="Visible par votre équipe uniquement."
                className="sm:col-span-2"
              >
                <input
                  value={form.reason}
                  onChange={(event) => setForm({ ...form, reason: event.target.value })}
                  placeholder="Congés annuels"
                  className={inputClass}
                />
              </Field>
            </div>

            <div className="mt-5 flex flex-wrap gap-2">
              <Button type="submit" pending={pending}>
                Enregistrer
              </Button>
              <GhostButton type="button" onClick={() => setOpen(false)}>
                Annuler
              </GhostButton>
            </div>
          </form>
        </Card>
      )}

      {!loaded && <Skeleton rows={2} />}

      {loaded && exceptions.length === 0 && (
        <EmptyState title="Aucune fermeture prévue">
          Ajoutez vos congés à l&apos;avance : les créneaux concernés
          disparaissent aussitôt du mini-site.
        </EmptyState>
      )}

      <ul className="space-y-2.5">
        {exceptions.map((exception) => {
          const kind = KIND_BY_VALUE[exception.kind];
          return (
            <li key={exception.id}>
              <Card>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="flex flex-wrap items-center gap-2">
                      <Badge tone={kind?.tone ?? "neutral"}>
                        {kind?.label ?? exception.kind}
                      </Badge>
                      {exception.reason && (
                        <span className="font-medium text-ink">{exception.reason}</span>
                      )}
                    </p>
                    <p className="mt-1.5 text-sm text-muted">
                      {dateFormat.format(new Date(exception.starts_at))} →{" "}
                      {dateFormat.format(new Date(exception.ends_at))}
                      {exception.staff_member
                        ? ` · ${staff.find((s) => s.id === exception.staff_member)?.name ?? "prestataire"}`
                        : " · tout le salon"}
                    </p>
                  </div>

                  {canEdit && (
                    <DangerButton type="button" onClick={() => remove(exception)}>
                      Supprimer
                    </DangerButton>
                  )}
                </div>
              </Card>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
