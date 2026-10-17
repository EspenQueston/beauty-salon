"""Cas B : premier paiement confirmé, délai de sécurité, droit à usage unique."""

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.common.db import bypass_tenant_context, tenant_context

from .models import EvenementParrainage, Parrainage, PolitiquePlateforme, Remise


def journal(obj, action, **details):
    EvenementParrainage.objects.create(
        cas="B",
        tenant_id=obj.beneficiaire_tenant_id,
        ressource=obj.pk,
        action=action,
        details=details,
    )


def politique():
    p = PolitiquePlateforme.objects.filter(pk=1, active=True).first()
    if p:
        try:
            p.full_clean()
        except ValidationError:
            return None
    return p


def conditions(p):
    return {
        "cooling_jours": p.cooling_jours,
        "cooling_mode": p.cooling_mode,
        "validite_jours": p.validite_jours,
        "reservation_heures": p.reservation_heures,
        "apres_remboursement": p.apres_remboursement,
    }


def fin_cooling(demande, confirmation, p):
    if p.cooling_mode == "demi_periode":
        if not demande.period_start or not demande.period_end:
            return None
        return confirmation + (demande.period_end - demande.period_start) / 2
    return confirmation + timedelta(days=p.cooling_jours)


@transaction.atomic
def paiement_confirme(demande, maintenant=None):
    from apps.billing.models import Plan, SubscriptionPaymentRequest

    maintenant = maintenant or timezone.now()
    if demande.status != SubscriptionPaymentRequest.Status.APPROVED:
        return
    if demande.plan.group not in (Plan.Groupe.STANDARD, Plan.Groupe.PRO):
        return
    if demande.billing_months not in (1, 12) or demande.etat_encaissement != "confirme":
        return
    parrainage = Parrainage.objects.select_for_update().filter(filleul_id=demande.tenant_id).first()
    if not parrainage or parrainage.statut in ("refuse", "invalide"):
        return
    # Le premier paiement admissible est fige même si les paramètres sont encore absents.
    premier = (
        SubscriptionPaymentRequest.objects.filter(
            tenant_id=demande.tenant_id,
            status="approved",
            plan__group__in=("standard", "pro"),
            billing_months__in=(1, 12),
        )
        .order_by("reviewed_at", "created_at")
        .first()
    )
    if not premier or premier.pk != demande.pk:
        return
    if parrainage.statut != Parrainage.Statut.ADMISSIBLE:
        parrainage.statut = Parrainage.Statut.ADMISSIBLE
        parrainage.admissible_le = maintenant
        parrainage.save(update_fields=["statut", "admissible_le", "maj_le"])
        EvenementParrainage.objects.create(
            cas="B",
            tenant_id=demande.tenant_id,
            ressource=parrainage.pk,
            action="paiement_confirme",
            details={"paiement": str(demande.pk)},
        )
    if parrainage.type_parrain != Parrainage.TypeParrain.SALON or not parrainage.parrain_tenant_id:
        return  # Récompense cliente non définie : aucun avantage inventé.
    if (
        Remise.objects.filter(parrainage=parrainage)
        .exclude(reference=f"premier_paiement:{parrainage.pk}")
        .exists()
    ):
        return  # Les droits historiques restent acquis sans nouvelle récompense pour ce filleul.
    p = politique()
    # Une seule récompense par filleul. Aucun paiement ultérieur n'en crée une seconde.
    r, cree = Remise.objects.get_or_create(
        reference=f"premier_paiement:{parrainage.pk}",
        defaults={
            "parrainage": parrainage,
            "beneficiaire_tenant_id": parrainage.parrain_tenant_id,
            "filleul_nom": parrainage.filleul.name,
            "declencheur": Remise.Declencheur.PAIEMENT,
            "pourcentage": 10,
            "statut": Remise.Statut.EN_ATTENTE,
            "paiement_declencheur": demande,
            "paiement_confirme_le": maintenant,
            "disponible_le": fin_cooling(demande, maintenant, p) if p else None,
            "conditions": conditions(p) if p else {},
        },
    )
    if cree:
        journal(r, "creation", paiement=str(demande.pk), configuration_complete=bool(p))


def paiement_admissible(r):
    from apps.billing.models import SubscriptionPaymentRequest

    if not r.paiement_declencheur_id:
        return "absent"
    with bypass_tenant_context(), tenant_context(r.parrainage.filleul_id):
        p = SubscriptionPaymentRequest.objects.filter(pk=r.paiement_declencheur_id).first()
        if not p or p.status != "approved":
            return "annule"
        return p.etat_encaissement


@transaction.atomic
def avancer(rid, maintenant=None):
    from apps.tenants.models import Tenant

    maintenant = maintenant or timezone.now()
    r = Remise.objects.select_for_update(of=("self",)).select_related("parrainage").get(pk=rid)
    if r.statut not in (Remise.Statut.EN_ATTENTE, Remise.Statut.SUSPENDUE):
        return False
    if not r.parrainage_id or r.parrainage.statut == "invalide":
        r.statut = Remise.Statut.ANNULEE
        r.save(update_fields=["statut"])
        journal(r, "annulation", motif="parrainage_invalidé")
        return False
    etat = paiement_admissible(r)
    if etat in ("annule", "rembourse", "absent"):
        r.statut = Remise.Statut.ANNULEE
        r.annulee_le = maintenant
        r.save(update_fields=["statut", "annulee_le"])
        journal(r, "annulation", motif=etat)
        return False
    if etat == "conteste":
        if r.statut != Remise.Statut.SUSPENDUE:
            r.statut = Remise.Statut.SUSPENDUE
            r.save(update_fields=["statut"])
            journal(r, "suspension", motif=etat)
        return False
    p = politique()
    if not p:
        return False
    Tenant.objects.select_for_update().get(pk=r.beneficiaire_tenant_id)
    if not r.conditions:
        r.conditions = conditions(p)
        with bypass_tenant_context(), tenant_context(r.parrainage.filleul_id):
            r.disponible_le = fin_cooling(r.paiement_declencheur, r.paiement_confirme_le, p)
        r.save(update_fields=["conditions", "disponible_le"])
    if not r.disponible_le or r.disponible_le > maintenant:
        if r.statut == Remise.Statut.SUSPENDUE:
            r.statut = Remise.Statut.EN_ATTENTE
            r.save(update_fields=["statut"])
            journal(r, "resolution_contestation")
        return False
    # Plafond du nombre de récompenses explicite ; bloquer, jamais inventer un cumul.
    deja = Remise.objects.filter(
        beneficiaire_tenant_id=r.beneficiaire_tenant_id,
        paiement_declencheur__isnull=False,
        statut__in=("disponible", "reservee", "utilisee", "expiree"),
    ).count()
    if deja >= p.recompenses_max_par_parrain:
        return False
    r.statut = Remise.Statut.DISPONIBLE
    r.disponible_le = maintenant
    r.expire_le = maintenant + timedelta(days=r.conditions["validite_jours"])
    r.save(update_fields=["statut", "disponible_le", "expire_le"])
    journal(r, "disponibilite", expire_le=r.expire_le.isoformat())
    return True


def evaluer(maintenant=None):
    from .services import expirer

    maintenant = maintenant or timezone.now()
    ids = Remise.objects.filter(
        statut__in=("en_attente", "suspendue"), paiement_declencheur__isnull=False
    ).values_list("pk", flat=True)
    disponibles = sum(avancer(rid, maintenant) for rid in list(ids))
    return {"admissibles": disponibles, "revues": 0, "expirees": expirer(maintenant)}
