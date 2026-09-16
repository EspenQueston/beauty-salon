"""Cycle de vie des abonnements et des factures.

Rien n'est preleve automatiquement : aucun prestataire de paiement n'est
branche, et le document conditionne cette integration a la validation d'un
partenaire par pays. Ce module se contente donc de ce qui a de la valeur des
maintenant — savoir qui doit quoi, depuis quand, et constater les
reglements — en laissant l'encaissement hors ligne.
"""

import logging
from datetime import timedelta
from decimal import Decimal

from django.db import connection, transaction
from django.utils import timezone

from apps.common.db import tenant_context
from apps.tenants.models import Tenant

from .models import Invoice, Plan, Subscription

logger = logging.getLogger(__name__)

TRIAL_DAYS = 30
PAYMENT_TERMS_DAYS = 15

# Duree d'un cycle. Un mois calendaire varie ; 30 jours suffit tant qu'on
# facture a terme echu et qu'aucun prelevement automatique n'est en jeu.
PERIOD_DAYS = 30


class BillingError(Exception):
    """Operation de facturation refusee."""


def start_trial(tenant: Tenant, *, plan: Plan | None = None) -> Subscription:
    """Ouvre la periode d'essai d'un salon qui vient de s'inscrire."""
    plan = plan or Plan.objects.filter(code=Plan.Code.TRIAL, active=True).first()
    if plan is None:
        raise BillingError("Aucune offre d'essai n'est configurée.")

    now = timezone.now()
    ends = now + timedelta(days=TRIAL_DAYS)

    with tenant_context(tenant.id):
        existing = Subscription.objects.filter(tenant=tenant).first()
        if existing is not None:
            return existing

        return Subscription.objects.create(
            tenant=tenant,
            plan=plan,
            status=Subscription.Status.TRIALING,
            price_amount=Decimal("0"),
            currency=tenant.currency,
            trial_ends_at=ends,
            current_period_start=now,
            current_period_end=ends,
        )


def next_invoice_number() -> str:
    """Numero de facture, tire d'une sequence PostgreSQL.

    Le compteur porte sur toute la plateforme et non par salon : c'est elle
    qui vend, sa numerotation doit donc etre continue d'un client a l'autre.

    Compter les lignes existantes ne marcherait pas ici : les politiques RLS
    masquent les factures des autres salons, et une transaction ouverte cache
    celles qu'on vient d'ecrire. La sequence, elle, est atomique et
    indifferente aux deux.
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT nextval('billing_invoice_number_seq')")
        sequence = cursor.fetchone()[0]
    return f"F{sequence:06d}"


@transaction.atomic
def issue_invoice(subscription: Subscription, *, label: str = "") -> Invoice:
    """Emet la facture de la periode ecoulee et ouvre la suivante."""
    now = timezone.now()
    invoice = Invoice.objects.create(
        tenant_id=subscription.tenant_id,
        subscription=subscription,
        number=next_invoice_number(),
        period_start=subscription.current_period_start,
        period_end=subscription.current_period_end,
        amount=subscription.price_amount,
        currency=subscription.currency,
        label=label or f"Abonnement {subscription.plan.name}",
        status=Invoice.Status.ISSUED,
        issued_at=now,
        due_at=now + timedelta(days=PAYMENT_TERMS_DAYS),
    )

    subscription.current_period_start = subscription.current_period_end
    subscription.current_period_end = subscription.current_period_end + timedelta(
        days=PERIOD_DAYS
    )
    subscription.save(
        update_fields=["current_period_start", "current_period_end", "updated_at"]
    )
    return invoice


def mark_invoice_paid(
    invoice: Invoice, *, method: str, reference: str = ""
) -> Invoice:
    if invoice.status == Invoice.Status.PAID:
        raise BillingError("Cette facture est déjà réglée.")
    if invoice.status == Invoice.Status.VOID:
        raise BillingError("Cette facture est annulée.")

    invoice.status = Invoice.Status.PAID
    invoice.paid_at = timezone.now()
    invoice.payment_method = method
    invoice.payment_reference = reference
    invoice.save(
        update_fields=[
            "status",
            "paid_at",
            "payment_method",
            "payment_reference",
            "updated_at",
        ]
    )

    # L'abonnement devient une charge du salon, sans qu'il ait a la saisir.
    #
    # C'est une depense comme le loyer : il la subit, il ne la decide pas. Ce
    # serait absurde que le seul poste que la plateforme connait au centime
    # pres soit le seul que le salon doive recopier a la main.
    from apps.finance.services import record_subscription_expense

    record_subscription_expense(invoice)

    # Et la recette de la plateforme, de son cote du registre.
    from apps.platformledger.services import record_subscription_income

    record_subscription_income(invoice)

    # Un salon suspendu pour impaye retrouve son service des le reglement.
    subscription = invoice.subscription
    if subscription.status == Subscription.Status.PAST_DUE:
        subscription.status = Subscription.Status.ACTIVE
        subscription.save(update_fields=["status", "updated_at"])

    return invoice


def run_billing_cycle(now=None) -> dict:
    """Balaye les salons et fait avancer leur abonnement.

    Trois actions, toutes idempotentes :
      - fin d'essai : l'abonnement passe en actif et sa premiere facture part ;
      - periode echue : une facture est emise ;
      - facture en retard : l'abonnement passe en impaye.

    Concue pour tourner tous les jours sans etat externe : relancer la tache
    deux fois le meme jour ne facture pas deux fois.
    """
    now = now or timezone.now()
    issued = converted = overdue = 0

    for tenant_id in Tenant.objects.exclude(
        status=Tenant.Status.SUSPENDED
    ).values_list("id", flat=True):
        with tenant_context(tenant_id):
            subscription = (
                Subscription.objects.select_related("plan", "tenant")
                .filter(tenant_id=tenant_id)
                .first()
            )
            if subscription is None or not subscription.is_running:
                continue

            if (
                subscription.status == Subscription.Status.TRIALING
                and subscription.trial_ends_at
                and subscription.trial_ends_at <= now
            ):
                subscription.status = Subscription.Status.ACTIVE
                subscription.save(update_fields=["status", "updated_at"])
                converted += 1

            if subscription.current_period_end <= now and subscription.price_amount > 0:
                issue_invoice(subscription)
                issued += 1

            late = Invoice.objects.filter(
                subscription=subscription,
                status=Invoice.Status.ISSUED,
                due_at__lt=now,
            ).exists()
            if late and subscription.status == Subscription.Status.ACTIVE:
                subscription.status = Subscription.Status.PAST_DUE
                subscription.save(update_fields=["status", "updated_at"])
                overdue += 1

    logger.info(
        "Cycle de facturation : %s facture(s), %s conversion(s), %s impaye(s).",
        issued,
        converted,
        overdue,
    )
    return {"issued": issued, "converted": converted, "overdue": overdue}
