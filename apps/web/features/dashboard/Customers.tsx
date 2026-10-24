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

import { useTranslations } from "next-intl";
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
import { useFormats } from "./formats";
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

/** Le ton de chaque statut ; le libellé vient de `pro.clientes.statut`. */
const STATUS_TONES: Record<string, "success" | "danger" | "warning" | "neutral"> = {
  completed: "success",
  confirmed: "neutral",
  requested: "warning",
  checked_in: "neutral",
  cancelled: "neutral",
  no_show: "danger",
};

type Filter = "all" | "recurring";

export function Customers() {
  const t = useTranslations("pro.clientes");
  const { region } = useFormats();
  const { membership } = useDashboard();
  const tenantId = membership.tenant.id;
  const timeZone = membership.tenant.timezone;
  const currency = membership.tenant.currency;

  const [customers, setCustomers] = useState<Customer[] | null>(null);
  const [error, setError] = useState(false);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [open, setOpen] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    // Petit délai : évite une requête par touche frappée.
    const handle = setTimeout(() => {
      const query = search ? `&search=${encodeURIComponent(search)}` : "";
      const recurring =
        filter === "recurring" ? "&recurring=true&ordering=visits" : "";
      dashboardFetch<{ results: Customer[] }>(
        `/api/v1/customers/?page_size=50${query}${recurring}`,
        {},
        tenantId,
      )
        .then((page) => {
          if (cancelled) return;
          setCustomers(page.results);
          setError(false);
        })
        .catch(() => {
          if (!cancelled) setError(true);
        });
    }, 250);

    return () => {
      cancelled = true;
      clearTimeout(handle);
    };
  }, [search, filter, tenantId]);

  const dateFormat = new Intl.DateTimeFormat(region, {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone,
  });

  return (
    <section>
      <PageHeader
        title={t("titre")}
        description={t("description")}
      />

      <div className="mb-5 flex flex-col gap-2 sm:flex-row sm:items-center">
        <input
          type="search"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder={t("recherche")}
          aria-label={t("rechercheAria")}
          className={`${inputClass} sm:max-w-sm`}
        />

        <div className="flex rounded-lg border border-line bg-surface p-0.5 sm:ml-auto">
          {(
            [
              ["all", t("filtres.toutes")],
              ["recurring", t("filtres.habituees")],
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

      {error && <ErrorState>{t("erreur")}</ErrorState>}
      {customers === null && !error && <Skeleton rows={4} />}

      {customers?.length === 0 && (
        <EmptyState
          title={
            search
              ? t("vide.rechercheTitre")
              : filter === "recurring"
                ? t("vide.habitueesTitre")
                : t("vide.titre")
          }
        >
          {search
            ? t("vide.recherche")
            : filter === "recurring"
              ? t("vide.habituees")
              : t("vide.corps")}
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
                      <Badge tone="success">{t("habituee")}</Badge>
                    )}
                    {customer.no_show_count >= 2 && (
                      <Badge tone="danger">
                        {t("absencesBadge", { n: customer.no_show_count })}
                      </Badge>
                    )}
                  </p>
                  <p className="mt-0.5 text-sm text-muted">
                    {customer.phone}
                    {customer.email && ` · ${customer.email}`}
                  </p>
                  {customer.last_booking_at && (
                    <p className="mt-0.5 text-sm text-subtle">
                      {t("dernier", {
                        date: dateFormat.format(new Date(customer.last_booking_at)),
                      })}
                    </p>
                  )}
                </div>

                <div className="flex flex-col items-end gap-2">
                  {customer.marketing_consent && (
                    <Badge tone="success">{t("offres")}</Badge>
                  )}
                </div>
              </div>

              {/* Trois compteurs côte à côte, en deux colonnes dès le
                  téléphone : ils se lisent ensemble ou pas du tout. */}
              <dl className="mt-3 grid grid-cols-3 gap-2 border-t border-line pt-3">
                <Counter
                  label={t("compteurs.venues", { n: customer.visit_count })}
                  value={customer.visit_count}
                />
                <Counter
                  label={t("compteurs.annulations", { n: customer.cancelled_count })}
                  value={customer.cancelled_count}
                />
                <Counter
                  label={t("compteurs.absences", { n: customer.no_show_count })}
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
                    name={
                      open === customer.id ? "chevron-left" : "chevron-right"
                    }
                    className={`size-3.5 transition-transform ${
                      open === customer.id ? "rotate-90" : ""
                    }`}
                  />
                  {open === customer.id
                    ? t("masquer")
                    : t("voir", { n: customer.booking_count })}
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
  const t = useTranslations("pro.clientes");
  const { region } = useFormats();
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

  const format = new Intl.DateTimeFormat(region, {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone,
  });

  if (failed) {
    return <p className="mt-3 text-sm text-danger">{t("historiqueIndisponible")}</p>;
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
        const status = {
          label: row.status in STATUS_TONES ? t(`statut.${row.status}`) : row.status,
          tone: STATUS_TONES[row.status] ?? ("neutral" as const),
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
                {formatPrice(row.total_amount, currency, region)}
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
