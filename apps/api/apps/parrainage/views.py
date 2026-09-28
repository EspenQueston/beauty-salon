"""Le parrainage vu par le parrain : son code, ses filleuls, ses remises.

Trois portes, chacune filtree sur qui la pousse :

  - `/api/v1/parrainage` : le proprietaire d'un salon ;
  - `/api/v1/public/client/parrainage` : une cliente, depuis son espace ;
  - `/api/v1/account/parrainage/<code>` : le formulaire d'inscription, qui
    verifie un code avant l'envoi.

Du filleul, le parrain ne voit que le nom public du salon, le statut du
parrainage et sa date : ni coordonnees, ni chiffres, ni motif de refus
detaille (qui dirait ce que la detection de fraude a reconnu).
"""

from __future__ import annotations

from decimal import Decimal

from django.db.models import Q
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Membership
from apps.clients.views import IsClient
from apps.common.permissions import HasTenantRole, IsTenantMember

from . import services
from .models import Parrainage, Remise

STATUT_VISIBLE = {
    Parrainage.Statut.EN_VERIFICATION: "en_verification",
    Parrainage.Statut.ADMISSIBLE: "admissible",
    Parrainage.Statut.REFUSE: "non_retenu",
    Parrainage.Statut.INVALIDE: "non_retenu",
}


def _pct(valeur) -> str:
    """« 10 », « 12.5 » : jamais « 1E+1 » (Decimal.normalize seul)."""
    return f"{Decimal(valeur).normalize():f}"


def _regles() -> dict:
    return {
        "pourcentage": _pct(services.POURCENTAGE),
        "plafond": _pct(services.PLAFOND_PAR_PAIEMENT),
        "validite_mois": 12,
        "delai_jours": services.DELAI_ADMISSIBILITE.days,
        "recompenses_paiement_max": services.REMISES_PAIEMENT_MAX,
    }


def _filleuls(parrainages) -> list[dict]:
    return [
        {
            "nom": p.filleul.name,
            "statut": STATUT_VISIBLE[p.statut],
            "date": p.cree_le,
            "admissible_le": p.admissible_le,
        }
        for p in parrainages.select_related("filleul")
    ]


def _remises(remises) -> list[dict]:
    return [
        {
            "id": str(r.id),
            "pourcentage": _pct(r.pourcentage),
            "statut": r.statut,
            "declencheur": r.declencheur,
            "filleul": r.filleul_nom,
            "cree_le": r.cree_le,
            "expire_le": r.expire_le,
            "utilisee_le": r.utilisee_le,
            "montant_deduit": str(r.montant_deduit) if r.montant_deduit is not None else None,
            "devise": r.devise,
            "origine": "salon" if r.beneficiaire_tenant_id else "compte",
        }
        for r in remises.order_by("-cree_le")[:100]
    ]


def _resume(prochaines) -> dict:
    return {
        "pourcentage_prochain_paiement": _pct(sum((r.pourcentage for r in prochaines), 0)),
        "remises_prochain_paiement": len(prochaines),
    }


class ParrainageSalonView(APIView):
    """Le parrainage du salon, pour son proprietaire."""

    permission_classes = [IsTenantMember, HasTenantRole]
    required_roles = (Membership.Role.OWNER,)
    safe_roles = (Membership.Role.OWNER,)

    def get(self, request):
        if not services.actif():
            return Response({"actif": False})
        from apps.tenants.models import Tenant

        code = services.code_du_salon(Tenant.objects.get(pk=request.tenant_id))
        remises = Remise.objects.filter(
            Q(beneficiaire_tenant_id=request.tenant_id) | Q(beneficiaire_user_id=request.user.pk)
        )
        return Response(
            {
                "actif": True,
                "code": code.code,
                "lien": services.lien(code),
                "regles": _regles(),
                "filleuls": _filleuls(
                    Parrainage.objects.filter(parrain_tenant_id=request.tenant_id)
                ),
                "remises": _remises(remises),
                "resume": _resume(services.utilisables(request.tenant_id, request.user)),
            }
        )


class ParrainageClienteView(APIView):
    """Le parrainage d'une cliente : son code, et ce qu'il lui a rapporte."""

    permission_classes = [IsClient]

    def get(self, request):
        if not services.actif():
            return Response({"actif": False})
        code = services.code_de_l_utilisateur(request.user)
        return Response(
            {
                "actif": True,
                "code": code.code,
                "lien": services.lien(code),
                "regles": _regles(),
                "filleuls": _filleuls(Parrainage.objects.filter(parrain_user_id=request.user.pk)),
                "remises": _remises(Remise.objects.filter(beneficiaire_user_id=request.user.pk)),
                # Une remise de cliente s'utilise sur l'abonnement d'un salon
                # qu'elle possede : on lui dit si c'est deja son cas.
                "possede_un_salon": Membership.objects.filter(
                    user=request.user,
                    role=Membership.Role.OWNER,
                    status=Membership.Status.ACTIVE,
                ).exists(),
            }
        )


class VerifierCodeView(APIView):
    """Le formulaire d'inscription verifie un code avant l'envoi.

    Ne revele du parrain que ce qui est deja public : le nom d'un salon. Le
    nom d'une cliente marraine ne sort pas d'ici.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "referral_check"

    def get(self, request, code):
        trouve = services.resoudre(code) if services.actif() else None
        if trouve is None:
            return Response({"valide": False})
        return Response(
            {
                "valide": True,
                "code": trouve.code,
                "type": trouve.type_parrain,
                "salon": trouve.tenant.name if trouve.tenant_id else "",
            }
        )
