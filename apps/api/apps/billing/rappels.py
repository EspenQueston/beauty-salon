"""Les rappels d'abonnement : lequel envoyer, a quel salon, et une seule fois.

---------------------------------------------------------------------------
Le calendrier
---------------------------------------------------------------------------

  - essai : J-7, J-3, la veille ;
  - periode payee : J-7, J-3, la veille — et J-30 pour l'annuel, dont le
    montant se prepare ;
  - le lendemain de l'echeance : debut du delai de grace ;
  - a la fin de la grace : les reservations se mettent en pause.

A chaque passage, un seul rappel au plus par salon : le plus proche de
l'echeance. Un salon qui arrive a J-2 sans avoir recu le J-7 (inscrit la
veille d'un essai court, periode prolongee...) recoit le J-3, pas les deux.

---------------------------------------------------------------------------
Ce qui fait taire les rappels
---------------------------------------------------------------------------

  - un paiement declare, en attente de verification : on ne presse pas
    quelqu'un qui a deja paye ;
  - une suspension ou une resiliation : c'est une decision, pas un oubli ;
  - la nuit : rien ne part hors de 8 h - 20 h, heure du salon. La tache est
    horaire, elle le retrouve le matin ;
  - une fermeture ancienne : un salon ferme depuis plus d'une semaine a deja
    ete prevenu, un deploiement ne doit pas le relancer.

Idempotence : un rappel est inscrit dans `SubscriptionReminder`, unique par
abonnement, genre et fin de periode. Une periode prolongee a une nouvelle fin,
donc un nouveau calendrier.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.common.db import bypass_tenant_context, tenant_context
from apps.tenants.models import Tenant

from . import courriers
from .models import Subscription, SubscriptionPaymentRequest, SubscriptionReminder
from .services import GRACE

logger = logging.getLogger(__name__)

HEURES_OUVREES = range(8, 20)
SEUILS_ESSAI = (7, 3, 1)
SEUILS_MENSUEL = (7, 3, 1)
SEUILS_ANNUEL = (30, 7, 3, 1)
FERMETURE_RECENTE = timedelta(days=7)


def genre_du_rappel(abonnement: Subscription, maintenant: datetime) -> str | None:
    """Le rappel du moment pour cet abonnement, ou None."""
    if abonnement.status in (Subscription.Status.SUSPENDED, Subscription.Status.CANCELLED):
        return None
    if abonnement.payment_requests.filter(
        status=SubscriptionPaymentRequest.Status.PENDING
    ).exists():
        return None

    fin = abonnement.current_period_end
    if maintenant < fin:
        jours = (fin - maintenant).total_seconds() / 86_400
        essai = abonnement.status == Subscription.Status.TRIALING
        if essai:
            seuils = SEUILS_ESSAI
        elif abonnement.plan.code == "yearly":
            seuils = SEUILS_ANNUEL
        else:
            seuils = SEUILS_MENSUEL
        atteints = [seuil for seuil in seuils if jours <= seuil]
        if not atteints:
            return None
        return f"{'trial' if essai else 'renewal'}_{min(atteints)}"

    if maintenant < fin + GRACE:
        return "grace"
    if maintenant - (fin + GRACE) <= FERMETURE_RECENTE:
        return "closed"
    return None


def envoyer_rappels(maintenant: datetime | None = None) -> dict:
    """Balaye les salons ; renvoie le nombre de rappels envoyes par genre."""
    maintenant = maintenant or timezone.now()
    envoyes: dict[str, int] = {}

    # Un salon suspendu par la plateforme n'a pas de rappel de paiement a
    # recevoir : sa fermeture est une decision, pas un oubli.
    salons = Tenant.objects.exclude(status=Tenant.Status.SUSPENDED).only(
        "id", "timezone", "name", "slug"
    )
    for tenant in salons:
        heure = maintenant.astimezone(ZoneInfo(tenant.timezone or "UTC")).hour
        if heure not in HEURES_OUVREES:
            continue
        try:
            genre = _rappeler(tenant, maintenant)
        except Exception:  # noqa: BLE001 - un salon en echec n'arrete pas les autres
            logger.exception("Rappel d'abonnement en echec pour %s.", tenant.id)
            continue
        if genre:
            envoyes[genre] = envoyes.get(genre, 0) + 1

    if envoyes:
        logger.info("Rappels d'abonnement envoyés : %s.", envoyes)
    return envoyes


def _rappeler(tenant: Tenant, maintenant: datetime) -> str | None:
    with bypass_tenant_context(), tenant_context(tenant.id):
        abonnement = (
            Subscription.objects.select_related("plan", "tenant")
            .filter(tenant_id=tenant.id)
            .first()
        )
        if abonnement is None:
            return None
        genre = genre_du_rappel(abonnement, maintenant)
        if genre is None:
            return None
        deja = SubscriptionReminder.objects.filter(
            subscription=abonnement, kind=genre, period_end=abonnement.current_period_end
        ).exists()
        if deja:
            return None

        # Envoyer d'abord, inscrire ensuite : un serveur de courrier en panne
        # laisse le rappel a refaire au passage suivant, au lieu de le marquer
        # parti alors qu'il ne l'est pas.
        destinataires = courriers.proprietaires(tenant.id)
        nombre = courriers.envoyer(
            courriers.rappel(abonnement, genre, maintenant), destinataires, abonnement.tenant
        )
        try:
            with transaction.atomic():
                SubscriptionReminder.objects.create(
                    tenant_id=tenant.id,
                    subscription=abonnement,
                    kind=genre,
                    period_end=abonnement.current_period_end,
                    recipients=nombre,
                )
        except IntegrityError:
            # Un autre passage l'a inscrit entre-temps : rien a faire.
            return None
        return genre
