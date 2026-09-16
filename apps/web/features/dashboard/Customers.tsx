"use client";

/**
 * Fichier clientes.
 *
 * C'est la donnée qui attache durablement un salon au produit : son
 * historique de rendez-vous. La recherche porte sur le nom et le téléphone,
 * les deux façons dont une réceptionniste retrouve quelqu'un au comptoir.
 *
 * ---------------------------------------------------------------------------
 * Ce que la fiche montre, et pourquoi dans cet ordre
 * ---------------------------------------------------------------------------
 *
 * Trois chiffres suffisent à décider quelque chose au téléphone :
 *
 *   - **venues** : le seul compteur qui dit « c'est une habituée » ;
 *   - **absences** : le seul qui justifie de demander un acompte ;
 *   - **annulations** : à part des absences, parce qu'une cliente qui
 *     prévient n'est pas une cliente qui ne vient pas. Les confondre
 *     reviendrait à punir celle qui a bien fait.
 *
 * L'historique détaillé, lui, se déplie à la demande : il est chargé par une
 * requête séparée, et l'inclure dans la liste multiplierait par vingt le
 * poids d'un écran qu'on ouvre à chaque appel.
 */

import { useEffect, useState } from "react";

import { dashboardFetch } from "@/lib/dashboard";
import {
  Badge,
  Card,
  EmptyState,
  ErrorState,
  PageHeader,
  Skeleton,
  inputClass,
} from "@/features/ui";
import { formatPrice } from "@/lib/format";
import { useDashboard } from "./DashboardShell";
import { Icon } from "./icons";

interface Customer {
  id: string;
  full_name: string;
  phone: string;
  email: string;
  marketing_consent: boolean;
  booking_count: number;
  visit_count: number;
  no_show_count: number;
  cancelled_count: number;
  last_booking_at: string | null;
}

interface HistoryRow {
  id: string;
  starts_at: string;
  status: string;
  service_name: string;
  staff_member_name: string;
  total_amount: string;
  options_snapshot: { name: string; price: string; minutes: number }[];
  internal_note: string;
}

const STATUS_LABELS: Record<string, { label: string; tone: "success" | "danger" | "warning" | "neutral" }> = {
  completed: { label: "Terminée", tone: "success" },
  confirmed: { label: "Confirmée", tone: "neutral" },
  requested: { label: "Demandée", tone: "warning" },
  checked_in: { label: "Arrivée", tone: "neutral" },
  cancelled: { label: "Annulée", tone: "neutral" },
  no_show: { label: "Absente", tone: "danger" },
};

type Filter = "all" | "recurring";

export function Customers() {
  const { membership } = useDashboard();
  const tenantId = membership.tenant.id;
  const timeZone = membership.tenant.timezone;
  const currency = membership.tenant.currency;

  const [customers, setCustomers] = useState<Customer[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [open, setOpen] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    // Petit délai : évite une requête par touche frappée.
    const handle = setTimeout(() => {
      const query = search ? `&search=${encodeURIComponent(search)}` : "";
      const recurring = filter === "recurring" ? "&recurring=true&ordering=visits" : "";
      dashboardFetch<{ results: Customer[] }>(
        `/api/v1/customers/?page_size=50${query}${recurring}`,
        {},
        tenantId,
      )
        .then((page) => {
          if (cancelled) return;
          setCustomers(page.results);
          setError(null);
        })
        .catch(() => {
          if (!cancelled) setError("Impossible de charger les clientes.");
        });
    }, 250);

    return () => {
      cancelled = true;
      clearTimeout(handle);
    };
  }, [search, filter, tenantId]);

  const dateFormat = new Intl.DateTimeFormat("fr-FR", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone,
  });

  return (
    <section>
      <PageHeader
        title="Clientes"
        description="Constitué automatiquement à chaque réservation. Ces données sont les vôtres."
      />

      <div className="mb-5 flex flex-col gap-2 sm:flex-row sm:items-center">
        <input
          type="search"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Rechercher par nom ou téléphone"
          aria-label="Rechercher une cliente"
          className={`${inputClass} sm:max-w-sm`}
        />

        <div className="flex rounded-lg border border-line bg-surface p-0.5 sm:ml-auto">
          {(
            [
              ["all", "Toutes"],
              ["recurring", "Habituées"],
            ] as [Filter, string][]
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              aria-pressed={filter === key}
              onClick={() => setFilter(key)}
              className={`rounded-md px-3 py-1.5 text-sm transition ${
                filter === key
                  ? "bg-salon font-medium text-white"
                  : "text-muted hover:text-ink"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {error && <ErrorState>{error}</ErrorState>}
      {customers === null && !error && <Skeleton rows={4} />}

      {customers?.length === 0 && (
        <EmptyState
          title={
            search
              ? "Aucun résultat"
              : filter === "recurring"
                ? "Pas encore d’habituées"
                : "Aucune cliente"
          }
        >
          {search
            ? "Essayez une autre orthographe, ou une partie du numéro."
            : filter === "recurring"
              ? "Une cliente entre ici dès son deuxième rendez-vous honoré."
              : "Votre fichier se remplira tout seul à la première réservation."}
        </EmptyState>
      )}

      <ul className="space-y-2.5">
        {customers?.map((customer) => (
          <li key={customer.id}>
            <Card>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="flex flex-wrap items-center gap-2 font-medium text-ink">
                    {customer.full_name}
                    {customer.visit_count >= 2 && (
                      <Badge tone="success">Habituée</Badge>
                    )}
                    {customer.no_show_count >= 2 && (
                      <Badge tone="danger">
                        {customer.no_show_count} absences
                      </Badge>
                    )}
                  </p>
                  <p className="mt-0.5 text-sm text-muted">
                    {customer.phone}
                    {customer.email && ` · ${customer.email}`}
                  </p>
                  {customer.last_booking_at && (
                    <p className="mt-0.5 text-sm text-subtle">
                      Dernier rendez-vous le{" "}
                      {dateFormat.format(new Date(customer.last_booking_at))}
                    </p>
                  )}
                </div>

                <div className="flex flex-col items-end gap-2">
                  {customer.marketing_consent && (
                    <Badge tone="success">Accepte les offres</Badge>
                  )}
                </div>
              </div>

              {/* Trois compteurs côte à côte, en deux colonnes dès le
                  téléphone : ils se lisent ensemble ou pas du tout. */}
              <dl className="mt-3 grid grid-cols-3 gap-2 border-t border-line pt-3">
                <Counter label="venues" value={customer.visit_count} />
                <Counter
                  label={customer.cancelled_count > 1 ? "annulations" : "annulation"}
                  value={customer.cancelled_count}
                />
                <Counter
                  label={customer.no_show_count > 1 ? "absences" : "absence"}
                  value={customer.no_show_count}
                  tone={customer.no_show_count > 0 ? "danger" : "neutral"}
                />
              </dl>

              {customer.booking_count > 0 && (
                <button
                  type="button"
                  onClick={() =>
                    setOpen((current) =>
                      current === customer.id ? null : customer.id,
                    )
                  }
                  aria-expanded={open === customer.id}
                  className="mt-3 flex items-center gap-1.5 text-sm text-muted transition hover:text-ink"
                >
                  <Icon
                    name={open === customer.id ? "chevron-left" : "chevron-right"}
                    className={`size-3.5 transition-transform ${
                      open === customer.id ? "rotate-90" : ""
                    }`}
                  />
                  {open === customer.id
                    ? "Masquer l’historique"
                    : `Voir les ${customer.booking_count} rendez-vous`}
                </button>
              )}

              {open === customer.id && (
                <History
                  customerId={customer.id}
                  tenantId={tenantId}
                  timeZone={timeZone}
                  currency={currency}
                />
              )}
            </Card>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Counter({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: number;
  tone?: "neutral" | "danger";
}) {
  return (
    <div>
      <dd
        className={`tabular text-lg font-semibold ${
          tone === "danger" && value > 0 ? "text-danger" : "text-ink"
        }`}
      >
        {value}
      </dd>
      <dt className="text-xs text-subtle">{label}</dt>
    </div>
  );
}

/**
 * Historique déplié.
 *
 * Chargé au premier dépliage seulement, et gardé ensuite : on ouvre et
 * referme la même fiche plusieurs fois pendant un appel, ce n'est pas une
 * raison pour redemander la même liste au serveur.
 */
function History({
  customerId,
  tenantId,
  timeZone,
  currency,
}: {
  customerId: string;
  tenantId: string;
  timeZone: string;
  currency: string;
}) {
  const [rows, setRows] = useState<HistoryRow[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    dashboardFetch<HistoryRow[]>(
      `/api/v1/customers/${customerId}/history/`,
      {},
      tenantId,
    )
      .then((data) => !cancelled && setRows(data))
      .catch(() => !cancelled && setFailed(true));

    return () => {
      cancelled = true;
    };
  }, [customerId, tenantId]);

  const format = new Intl.DateTimeFormat("fr-FR", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone,
  });

  if (failed) {
    return (
      <p className="mt-3 text-sm text-danger">Historique indisponible.</p>
    );
  }
  if (rows === null) {
    return (
      <div className="mt-3">
        <Skeleton rows={2} />
      </div>
    );
  }

  return (
    <ol className="mt-3 space-y-2 border-t border-line pt-3">
      {rows.map((row) => {
        const status = STATUS_LABELS[row.status] ?? {
          label: row.status,
          tone: "neutral" as const,
        };

        return (
          <li
            key={row.id}
            className="rounded-lg bg-surface-muted/60 p-2.5 text-sm"
          >
            <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
              <span className="min-w-0 font-medium text-ink">
                {row.service_name}
              </span>
              <Badge tone={status.tone}>{status.label}</Badge>
            </div>

            <p className="mt-0.5 text-muted">
              {format.format(new Date(row.starts_at))}
              {row.staff_member_name && ` · ${row.staff_member_name}`}
              {" · "}
              <span className="tabular">
                {formatPrice(row.total_amount, currency)}
              </span>
            </p>

            {row.options_snapshot?.length > 0 && (
              <p className="mt-1 text-xs text-subtle">
                {row.options_snapshot.map((option) => option.name).join(" · ")}
              </p>
            )}

            {/* La note interne suit la prestation, pas la cliente : « fond
                de tête sensible » ne veut rien dire sans savoir sur quelle
                pose c'est arrivé. */}
            {row.internal_note && (
              <p className="mt-1 border-l-2 border-line-strong pl-2 text-xs italic text-muted">
                {row.internal_note}
              </p>
            )}
          </li>
        );
      })}
    </ol>
  );
}
