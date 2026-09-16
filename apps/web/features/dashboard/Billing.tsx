"use client";

/**
 * Abonnement et factures du salon.
 *
 * En lecture seule, et volontairement : aucune passerelle de paiement n'est
 * branchée, le règlement se fait hors ligne et se constate côté plateforme.
 * L'écran dit donc clairement ce qui est dû, quand, et comment payer —
 * plutôt que d'afficher un bouton qui ne mènerait nulle part.
 */

import { useEffect, useState } from "react";

import { DashboardError, dashboardFetch } from "@/lib/dashboard";
import { formatPrice } from "@/lib/format";
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
import { useDashboard } from "./DashboardShell";
import { rows, useResource, type Page } from "./useResource";

interface Subscription {
  id: string;
  plan: { code: string; name: string; description: string };
  status: "trialing" | "active" | "past_due" | "cancelled";
  price_amount: string;
  currency: string;
  trial_ends_at: string | null;
  days_left_in_trial: number | null;
  current_period_start: string;
  current_period_end: string;
  setup_fee_amount: string;
  setup_fee_paid: boolean;
}

interface Invoice {
  id: string;
  number: string;
  label: string;
  amount: string;
  currency: string;
  status: "draft" | "issued" | "paid" | "void";
  issued_at: string;
  due_at: string;
  paid_at: string | null;
  payment_method: string;
  is_overdue: boolean;
}

type Tone = "neutral" | "success" | "warning" | "danger" | "info" | "salon";

const SUBSCRIPTION: Record<string, { label: string; tone: Tone }> = {
  trialing: { label: "Période d'essai", tone: "info" },
  active: { label: "Actif", tone: "success" },
  past_due: { label: "Impayé", tone: "danger" },
  cancelled: { label: "Résilié", tone: "neutral" },
};

const INVOICE: Record<string, { label: string; tone: Tone }> = {
  draft: { label: "Brouillon", tone: "neutral" },
  issued: { label: "À régler", tone: "warning" },
  paid: { label: "Réglée", tone: "success" },
  void: { label: "Annulée", tone: "neutral" },
};

const METHODS: Record<string, string> = {
  cash: "espèces",
  mobile_money: "Mobile Money",
  transfer: "virement",
  other: "autre",
};

export function Billing() {
  const { membership } = useDashboard();
  const tenantId = membership.tenant.id;
  const isOwner = membership.role === "owner";

  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [error, setError] = useState<string | null>(null);

  const invoices = useResource<Page<Invoice>>("/api/v1/invoices/", tenantId, {
    enabled: isOwner,
  });

  useEffect(() => {
    if (!isOwner) return;
    let cancelled = false;

    dashboardFetch<Subscription>("/api/v1/subscription", {}, tenantId)
      .then((data) => {
        if (!cancelled) setSubscription(data);
      })
      .catch((caught) => {
        if (cancelled) return;
        setError(
          caught instanceof DashboardError && caught.status === 404
            ? "Aucun abonnement n'est encore rattaché à ce salon. L'équipe Beauty Salon s'en charge à la validation."
            : "Chargement impossible.",
        );
      });

    return () => {
      cancelled = true;
    };
  }, [tenantId, isOwner]);

  if (!isOwner) {
    return (
      <section>
        <PageHeader title="Abonnement" />
        <EmptyState title="Réservé au propriétaire">
          La facturation n&apos;est visible que par la personne qui possède le
          salon.
        </EmptyState>
      </section>
    );
  }

  const dateFormat = new Intl.DateTimeFormat("fr-FR", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });

  const invoiceRows = rows(invoices.data);
  const unpaid = invoiceRows.filter((invoice) => invoice.status === "issued");
  const overdue = unpaid.filter((invoice) => invoice.is_overdue);
  const due = unpaid.reduce((total, invoice) => total + Number(invoice.amount), 0);

  return (
    <section>
      <PageHeader
        title="Abonnement"
        description="Votre offre, vos factures, et ce qu'il reste à régler."
      />

      {error && <ErrorState>{error}</ErrorState>}
      {invoices.error && <ErrorState>Impossible de charger les factures.</ErrorState>}

      {subscription === null && !error && <Skeleton rows={3} />}

      {subscription && (
        <>
          <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3 sm:gap-4">
            <StatTile
              label="Offre"
              value={subscription.plan.name}
              hint={
                Number(subscription.price_amount) > 0
                  ? `${formatPrice(subscription.price_amount, subscription.currency)} par mois`
                  : "Gratuit"
              }
            />
            <StatTile
              label={
                subscription.status === "trialing"
                  ? "Fin de l'essai"
                  : "Période en cours jusqu'au"
              }
              value={dateFormat.format(
                new Date(
                  subscription.status === "trialing" && subscription.trial_ends_at
                    ? subscription.trial_ends_at
                    : subscription.current_period_end,
                ),
              )}
              hint={
                subscription.status === "trialing" &&
                subscription.days_left_in_trial !== null
                  ? `${subscription.days_left_in_trial} jour${subscription.days_left_in_trial > 1 ? "s" : ""} restant${subscription.days_left_in_trial > 1 ? "s" : ""}`
                  : undefined
              }
            />
            <StatTile
              label="Reste à régler"
              value={
                due > 0 ? formatPrice(due, subscription.currency) : "Rien à régler"
              }
              hint={
                overdue.length > 0
                  ? `${overdue.length} facture${overdue.length > 1 ? "s" : ""} en retard`
                  : undefined
              }
              tone={overdue.length > 0 ? "danger" : "neutral"}
            />
          </div>

          <Card className="mb-8">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="font-semibold text-ink">{subscription.plan.name}</p>
                <p className="mt-1 max-w-xl text-sm leading-relaxed text-muted">
                  {subscription.plan.description}
                </p>
              </div>
              <Badge tone={SUBSCRIPTION[subscription.status]?.tone ?? "neutral"}>
                {SUBSCRIPTION[subscription.status]?.label ?? subscription.status}
              </Badge>
            </div>

            {Number(subscription.setup_fee_amount) > 0 && (
              <p className="mt-4 flex flex-wrap items-center gap-2 text-sm text-muted">
                <span>
                  Frais de mise en route :{" "}
                  <span className="font-medium text-ink">
                    {formatPrice(subscription.setup_fee_amount, subscription.currency)}
                  </span>
                </span>
                <Badge tone={subscription.setup_fee_paid ? "success" : "warning"}>
                  {subscription.setup_fee_paid ? "Réglés" : "À régler"}
                </Badge>
              </p>
            )}

            {subscription.status === "trialing" && (
              <p className="mt-4 rounded-lg bg-info-bg p-3 text-sm text-info">
                Votre essai est en cours. Aucune facture n&apos;est émise avant
                sa fin : rien ne s&apos;interrompt sans que vous le sachiez.
              </p>
            )}

            {subscription.status === "past_due" && (
              <p className="mt-4 rounded-lg bg-danger-bg p-3 text-sm text-danger">
                Une facture reste à régler. Contactez l&apos;équipe Beauty Salon
                pour reprendre un service normal — votre mini-site et vos
                rendez-vous restent accessibles entre-temps.
              </p>
            )}
          </Card>
        </>
      )}

      <SectionTitle>Factures</SectionTitle>

      {invoices.data === null && !invoices.error && <Skeleton rows={2} />}

      {invoiceRows.length === 0 && invoices.data !== null && (
        <EmptyState title="Aucune facture">
          Votre première facture sera émise à la fin de la période d&apos;essai.
        </EmptyState>
      )}

      <ul className="space-y-2.5">
        {invoiceRows.map((invoice) => {
          const late = invoice.is_overdue && invoice.status === "issued";
          const state = INVOICE[invoice.status];
          return (
            <li key={invoice.id}>
              <Card>
                <div className="flex flex-wrap items-center gap-3">
                  <div className="min-w-0 flex-1">
                    <p className="font-medium text-ink">
                      <span className="tabular">{invoice.number}</span>
                      <span className="font-normal text-muted"> — {invoice.label}</span>
                    </p>
                    <p className="mt-0.5 text-sm text-muted">
                      Émise le {dateFormat.format(new Date(invoice.issued_at))}
                      {invoice.status === "issued" &&
                        ` · à régler avant le ${dateFormat.format(new Date(invoice.due_at))}`}
                      {invoice.paid_at &&
                        ` · réglée le ${dateFormat.format(new Date(invoice.paid_at))}` +
                          (invoice.payment_method
                            ? ` en ${METHODS[invoice.payment_method] ?? invoice.payment_method}`
                            : "")}
                    </p>
                  </div>

                  <span className="tabular font-semibold text-ink">
                    {formatPrice(invoice.amount, invoice.currency)}
                  </span>

                  <Badge tone={late ? "danger" : (state?.tone ?? "neutral")}>
                    {late ? "En retard" : (state?.label ?? invoice.status)}
                  </Badge>
                </div>
              </Card>
            </li>
          );
        })}
      </ul>

      <p className="mt-6 max-w-2xl text-sm leading-relaxed text-muted">
        Le règlement se fait hors ligne — Mobile Money, espèces ou virement.
        Votre facture est marquée comme réglée dès réception, et vous en êtes
        averti par e-mail.
      </p>
    </section>
  );
}
