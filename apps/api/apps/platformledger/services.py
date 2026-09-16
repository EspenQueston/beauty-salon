"""Recettes de la plateforme, enregistrees toutes seules."""

from __future__ import annotations

from django.utils import timezone

from .models import PlatformEntry


def record_subscription_income(invoice) -> PlatformEntry | None:
    """Porte une facture d'abonnement reglee en recette de la plateforme.

    C'est le meme versement que la depense inscrite chez le salon, vu de
    l'autre cote du registre. Les deux lignes sont ecrites au meme moment,
    par le meme evenement - ce qui garantit qu'elles ne peuvent pas diverger.

    Idempotente : la facture fait office de cle.
    """
    if invoice.amount is None or invoice.amount <= 0:
        return None

    existing = PlatformEntry.objects.filter(invoice=invoice).first()
    if existing is not None:
        return existing

    tenant = getattr(invoice, "tenant", None)
    period = f" — {invoice.period_start:%m/%Y}" if invoice.period_start else ""

    return PlatformEntry.objects.create(
        kind=PlatformEntry.Kind.INCOME,
        category=PlatformEntry.IncomeCategory.SUBSCRIPTION,
        source=PlatformEntry.Source.SUBSCRIPTION,
        label=f"{getattr(tenant, 'name', 'Salon')}{period}",
        amount=invoice.amount,
        currency=invoice.currency,
        occurred_on=(invoice.paid_at or timezone.now()).date(),
        tenant=tenant,
        invoice=invoice,
        note=f"Facture {invoice.number}",
    )
