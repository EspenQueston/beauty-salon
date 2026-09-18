"""Changer la devise d'un salon, en deux temps.

---------------------------------------------------------------------------
Pourquoi deux temps
---------------------------------------------------------------------------

Un `GET` montre ce que le basculement ferait — le taux retenu, combien de
lignes changeraient, et ce que devient la prestation la plus chere. Un
`POST` l'execute.

Ce n'est pas une precaution de principe. Convertir un catalogue est
irreversible en pratique : le taux d'aujourd'hui n'est pas celui de demain,
donc revenir en arriere ne rend pas les prix d'origine. Une gerante doit
voir « 25 000 F devient 294 ¥ » avant d'accepter, parce que c'est cette
ligne-la — pas un taux a quatre decimales — qui lui fait reperer qu'elle
s'est trompee de sens.

---------------------------------------------------------------------------
Le pays decide de la suggestion, jamais du basculement
---------------------------------------------------------------------------

Un salon declare son pays a l'inscription, et l'ecran en deduit la devise
attendue : yuan pour la Chine, franc CFA pour le Congo-Brazzaville, franc
congolais pour la RDC. Quand la devise en place ne correspond pas, la route
le signale — c'est le cas d'un salon qui s'est trompe au moment de son
inscription, et il n'a aujourd'hui aucun moyen de s'en apercevoir.

Elle le *signale*. Elle ne bascule rien toute seule : un salon chinois qui
facture en francs a peut-etre une raison, et decider a sa place de convertir
tout son catalogue serait une correction plus grave que l'erreur.
"""

from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Membership
from apps.common.permissions import HasTenantRole, IsTenantMember

from .models import Tenant
from .services.conversion import DeviseRefusee, apercu, convertir
from .services.devises import TauxIndisponible

MANAGERS = (Membership.Role.OWNER, Membership.Role.MANAGER)
EVERYONE = (*MANAGERS, Membership.Role.RECEPTIONIST, Membership.Role.STAFF)

# Ce que le pays du salon laisse attendre.
#
# Une correspondance, pas une regle : elle sert a poser une question
# (« votre salon est en Chine, faut-il passer en yuans ? »), jamais a
# imposer une reponse.
DEVISE_ATTENDUE = {
    Tenant.Country.CHINA: Tenant.Currency.CNY,
    Tenant.Country.CONGO: Tenant.Currency.XAF,
    Tenant.Country.DRC: Tenant.Currency.CDF,
}


class BasculeSerializer(serializers.Serializer):
    currency = serializers.ChoiceField(choices=Tenant.Currency.choices)


class SalonCurrencyView(APIView):
    """La devise du salon : ce qu'elle est, ce qu'elle deviendrait."""

    permission_classes = [IsTenantMember, HasTenantRole]
    required_roles = MANAGERS
    safe_roles = EVERYONE

    def get(self, request):
        tenant = Tenant.objects.get(pk=request.tenant_id)
        attendue = DEVISE_ATTENDUE.get(tenant.country)

        corps = {
            "currency": tenant.currency,
            "country": tenant.country,
            "expected": attendue,
            # Le detecteur, reduit a ce qu'il peut affirmer : « ces deux
            # reglages ne concordent pas ». Ce qu'il faut en faire reste a
            # la gerante.
            "mismatch": bool(attendue and attendue != tenant.currency),
            "choices": [
                {"value": code, "label": str(libelle)}
                for code, libelle in Tenant.Currency.choices
            ],
        }

        cible = request.query_params.get("vers")
        if cible:
            try:
                corps["preview"] = apercu(tenant, cible)
            except DeviseRefusee as exc:
                return Response(
                    {"detail": str(exc), "code": "devise_refusee"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            except TauxIndisponible as exc:
                # 503 et non 400 : ce n'est pas la demande qui est mauvaise,
                # c'est nous qui ne pouvons pas y repondre maintenant.
                return Response(
                    {"detail": str(exc), "code": "taux_indisponible"},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )

        return Response(corps)

    def post(self, request):
        payload = BasculeSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        tenant = Tenant.objects.get(pk=request.tenant_id)

        try:
            resultat = convertir(tenant, payload.validated_data["currency"])
        except DeviseRefusee as exc:
            return Response(
                {"detail": str(exc), "code": "devise_refusee"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except TauxIndisponible as exc:
            return Response(
                {"detail": str(exc), "code": "taux_indisponible"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(resultat, status=status.HTTP_200_OK)
