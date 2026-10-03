"""Traitements periodiques de facturation, et les e-mails d'abonnement."""

import logging
from decimal import Decimal

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def run_billing_cycle():
    """Fait avancer les abonnements : fin d'essai, emission, impayes.

    Quotidienne et idempotente : la relancer dans la journee ne facture
    jamais deux fois la meme periode.
    """
    from .services import run_billing_cycle as run

    return run()


@shared_task
def envoyer_rappels_abonnement():
    """Rappels de fin d'essai, d'echeance, de grace et de fermeture.

    Horaire, et sans double envoi : chaque rappel est inscrit une fois par
    fin de periode (voir `SubscriptionReminder`).
    """
    from .rappels import envoyer_rappels

    return envoyer_rappels()


@shared_task(bind=True, max_retries=3, default_retry_delay=120)
def envoyer_courrier_abonnement(self, genre: str, tenant_id: str, demande_id: str | None = None):
    """Un e-mail d'evenement : paiement recu, valide, refuse ; geste d'admin.

    Retente en cas de panne du serveur de courrier : un « paiement valide »
    perdu, c'est une propriétaire qui croit encore son salon ferme.
    """
    from apps.common.db import bypass_tenant_context, tenant_context

    from . import courriers
    from .models import Subscription, SubscriptionPaymentRequest

    try:
        with bypass_tenant_context(), tenant_context(tenant_id):
            if demande_id:
                demande = SubscriptionPaymentRequest.objects.select_related(
                    "plan", "tenant", "subscription__tenant", "invoice"
                ).get(pk=demande_id)
                salon = demande.tenant
                composer = {
                    "paiement_recu": courriers.paiement_recu,
                    "paiement_a_verifier": courriers.paiement_a_verifier,
                    "paiement_valide": courriers.paiement_valide,
                    "paiement_refuse": courriers.paiement_refuse,
                }.get(genre)
                if composer is None:
                    raise ValueError(f"Courrier inconnu : {genre}")
                # L'alerte a l'equipe est une tache a part : une nouvelle
                # tentative ne renvoie pas l'accuse de reception au salon.
                destinataires = (
                    courriers.verificateurs()
                    if genre == "paiement_a_verifier"
                    else courriers.proprietaires(tenant_id)
                )
                courriers.envoyer(composer(demande), destinataires, salon)
                return

            abonnement = Subscription.objects.select_related("plan", "tenant").get(
                tenant_id=tenant_id
            )
            courriers.envoyer(
                courriers.geste(abonnement, genre),
                courriers.proprietaires(tenant_id),
                abonnement.tenant,
            )
    except ValueError:
        logger.exception("Courrier d'abonnement inconnu : %s.", genre)
    except Exception as exc:  # noqa: BLE001 - on retente, sans perdre la trace
        logger.exception("Echec du courrier d'abonnement %s pour %s.", genre, tenant_id)
        raise self.retry(exc=exc) from exc


@shared_task
def annoncer_changement_de_tarif(prix_id: str, ancien: str):
    """Annonce un prix modifie aux salons qui reglent dans cette devise.

    Les salons suspendus ou resilies ne sont pas concernes. Un salon par
    passage de boucle, dans son contexte : les abonnements sont sous RLS.
    """
    from django.utils import timezone

    from apps.common.db import bypass_tenant_context, tenant_context
    from apps.tenants.models import Tenant

    from . import courriers
    from .models import PlanPrice, Subscription

    prix = PlanPrice.objects.select_related("plan").filter(pk=prix_id).first()
    if prix is None or not prix.active or prix.amount == Decimal(ancien):
        return 0

    courrier = courriers.tarif_modifie(prix, Decimal(ancien), timezone.now())
    envoyes = 0
    for tenant in Tenant.objects.all():
        with bypass_tenant_context(), tenant_context(tenant.id):
            concerne = (
                Subscription.objects.filter(tenant_id=tenant.id, currency=prix.currency)
                .exclude(status__in=(Subscription.Status.SUSPENDED, Subscription.Status.CANCELLED))
                .exists()
            )
        if not concerne:
            continue
        try:
            if courriers.envoyer(courrier, courriers.proprietaires(tenant.id), tenant):
                envoyes += 1
        except Exception:  # noqa: BLE001 - un salon injoignable n'arrete pas les autres
            logger.exception("Annonce de tarif non envoyee a %s.", tenant.id)

    logger.info("Changement de tarif annonce a %s salon(s).", envoyes)
    return envoyes
