"""Constater un remboursement ou litige effectif, sans initier de transfert."""

from django.utils import timezone

from apps.common.db import bypass_tenant_context, tenant_context
from apps.parrainage.models import EvenementParrainage, Remise

from .models import SubscriptionPaymentRequest
from .services import PaiementRefuse, _tenant_de_la_demande


def constater(demande_id, *, administrateur, etat, motif):
    if not administrateur or not administrateur.has_perm(
        "billing.review_subscriptionpaymentrequest"
    ):
        raise PaiementRefuse("Autorisation de vérification requise.", "permission_refusee")
    if (
        etat not in dict(SubscriptionPaymentRequest._meta.get_field("etat_encaissement").choices)
        or len((motif or "").strip()) < 10
    ):
        raise PaiementRefuse(
            "Indiquez un état valide et un motif de dix caractères au moins.", "motif_requis"
        )
    tid = _tenant_de_la_demande(demande_id)
    if not tid:
        raise PaiementRefuse("Ce paiement n’existe pas.", "demande_inconnue")
    with bypass_tenant_context(), tenant_context(tid):
        d = SubscriptionPaymentRequest.objects.select_for_update().get(pk=demande_id)
        if d.status != "approved":
            raise PaiementRefuse(
                "Seul un paiement confirmé peut faire l’objet de ce constat.",
                "paiement_non_confirme",
            )
        if d.etat_encaissement == etat:
            return d
        from apps.parrainage.cycles import avancer

        ids = list(
            Remise.objects.filter(
                paiement_declencheur=d, statut__in=("en_attente", "suspendue")
            ).values_list("pk", flat=True)
        )
        # Rattraper une tâche tardive avant le nouveau constat : un droit dont
        # le cooling est déjà écoulé reste acquis selon les conditions validées.
        for rid in ids:
            avancer(rid, timezone.now())
        avant = d.etat_encaissement
        d.etat_encaissement = etat
        d.save(update_fields=["etat_encaissement", "updated_at"])
        EvenementParrainage.objects.create(
            cas="B",
            tenant_id=tid,
            ressource=d.pk,
            action="etat_encaissement",
            details={
                "avant": avant,
                "apres": etat,
                "motif": motif.strip(),
                "acteur": str(administrateur.pk),
            },
        )
        # Disponibilité déjà acquise : maintien selon la politique validée.
        for rid in ids:
            avancer(rid, timezone.now())
        return d
