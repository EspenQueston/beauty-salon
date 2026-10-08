"""Expiration et abandons : traitements réexécutables sans double avantage."""

from django.db import transaction
from django.utils import timezone

from apps.common.db import bypass_tenant_context, tenant_context

from .models import RecompenseClient, Remise


def entretenir():
    from apps.billing import kkiapay
    from apps.billing import services as billing
    from apps.billing.models import KkiapayIntent, SubscriptionPaymentRequest

    from . import clients, services

    maintenant = timezone.now()
    for iid in list(
        KkiapayIntent.objects.filter(statut="en_attente", expire_le__lte=maintenant).values_list(
            "pk", flat=True
        )
    ):
        kkiapay.expirer(iid)
    paiements = (
        Remise.objects.using("admin")
        .filter(statut="reservee", demande__isnull=False)
        .values_list("demande_id", "demande__tenant_id")
        .distinct()
    )
    for did, tid in list(paiements):
        with bypass_tenant_context(), tenant_context(tid):
            d = SubscriptionPaymentRequest.objects.select_for_update().get(pk=did)
            if d.status == "pending" and services.reservation_expiree(d, maintenant):
                billing.refuser_paiement(
                    d.pk,
                    administrateur=None,
                    motif="Réservation de remise expirée : paiement abandonné",
                )
    n = 0
    tenants = (
        RecompenseClient.all_tenants.using("admin")
        .filter(statut="disponible", expire_le__lte=maintenant)
        .values_list("tenant_id", flat=True)
        .distinct()
    )
    for tid in list(tenants):
        with bypass_tenant_context(), tenant_context(tid), transaction.atomic():
            for r in RecompenseClient.objects.select_for_update().filter(
                statut="disponible", expire_le__lte=maintenant
            ):
                r.statut = "expiree"
                r.save(update_fields=["statut", "updated_at"])
                clients.journal(r, "expiration")
                n += 1
    return {"recompenses_client_expirees": n}
