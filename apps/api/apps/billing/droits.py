"""Les droits d'un salon : Standard ou Pro, et chaque fonction Pro.

---------------------------------------------------------------------------
Cote serveur, toujours
---------------------------------------------------------------------------

Masquer un bouton ne protege rien : une requete se fabrique. Chaque route
et chaque action Pro passe donc par `ExigeFonctionPro`, qui relit ici, a
chaque requete, ce que l'abonnement du salon ouvre.

---------------------------------------------------------------------------
Les regles
---------------------------------------------------------------------------

  - le groupe effectif est celui de l'offre de la periode en cours ; une
    descente programmee ne compte qu'a partir de la fin de la periode Pro ;
  - l'essai donne Standard ;
  - une fonction Pro est ouverte si le salon est Pro, si son acces est
    ouvert (delai de grace compris) et si l'administration n'a pas coupe la
    fonction pour tous ;
  - Pro terminee ou descendue : les fonctions se mettent en pause. Les
    reglages restent en base et reviennent au retour a Pro.
"""

from __future__ import annotations

from datetime import datetime

from django.utils import timezone
from rest_framework.permissions import BasePermission

from .models import Plan, ProCapability, Subscription
from .services import acces_de

FONCTIONS = tuple(code for code, _ in ProCapability.Code.choices)


def groupe_effectif(
    abonnement: Subscription | None, maintenant: datetime | None = None
) -> str | None:
    """« standard », « pro », ou None quand l'acces est ferme."""
    maintenant = maintenant or timezone.now()
    if abonnement is None:
        return Plan.Groupe.STANDARD
    if not acces_de(abonnement, maintenant).ouvert:
        return None
    if abonnement.status == Subscription.Status.TRIALING:
        return Plan.Groupe.STANDARD
    if (
        abonnement.scheduled_plan_id
        and maintenant >= abonnement.current_period_end
        and abonnement.scheduled_plan is not None
    ):
        return abonnement.scheduled_plan.group
    return abonnement.plan.group


def fonctions_actives() -> set[str]:
    """Les fonctions Pro que l'administration n'a pas coupees."""
    return set(ProCapability.objects.filter(active=True).values_list("code", flat=True))


def fonctions_du_salon(tenant_id, maintenant: datetime | None = None) -> dict[str, bool]:
    """Chaque fonction Pro, ouverte ou non pour ce salon. A appeler dans son contexte."""
    abonnement = (
        Subscription.objects.select_related("plan", "scheduled_plan")
        .filter(tenant_id=tenant_id)
        .first()
    )
    pro = groupe_effectif(abonnement, maintenant) == Plan.Groupe.PRO
    actives = fonctions_actives() if pro else set()
    return {code: pro and code in actives for code in FONCTIONS}


def a_la_fonction(tenant_id, code: str) -> bool:
    return fonctions_du_salon(tenant_id).get(code, False)


class ExigeFonctionPro(BasePermission):
    """Refuse l'acces si le salon n'a pas la fonction Pro de la vue.

    La vue declare `fonction_pro = ProCapability.Code.XXX`. Le refus dit
    pourquoi, avec un code stable que le tableau de bord traduit en
    invitation a passer a Pro.
    """

    message = "Cette fonction fait partie de l'offre Pro."
    code = "offre_pro_requise"

    def has_permission(self, request, view) -> bool:
        code = getattr(view, "fonction_pro", None)
        tenant_id = getattr(request, "tenant_id", None)
        if not code or not tenant_id:
            return False
        return a_la_fonction(tenant_id, code)
