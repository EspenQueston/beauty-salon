"""Le taux du jour, pour une visiteuse du mini-site.

---------------------------------------------------------------------------
Ce que cette route n'est pas
---------------------------------------------------------------------------

Elle ne change rien. Le salon facture dans sa devise, point. Ce qu'elle
permet, c'est qu'une visiteuse qui lit « 280 ¥ » depuis Brazzaville sache
que cela fait environ 23 900 francs — sans quitter la page pour aller
chercher un convertisseur, et sans que le salon ait quoi que ce soit a
faire.

C'est une aide a la lecture, et l'ecran le dit : le montant converti est
prefixe d'un « ≈ » et accompagne d'une mention. Confondre les deux ferait
croire a un prix ferme dans une devise que le salon n'encaisse pas.

---------------------------------------------------------------------------
Pourquoi les devises proposees sont fermees
---------------------------------------------------------------------------

Aux trois que la plateforme connait, et jamais a ce que demande l'appelant.
Une route publique qui accepte n'importe quel code ferait de nous un
convertisseur universel gratuit, adosse a une cle d'API payante - et le
premier robot venu epuiserait le quota du salon.

Le cache de `devises.taux` fait le reste : douze heures, partagees par tous
les visiteurs de tous les salons.
"""

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import IsTenantResolved

from .models import Tenant
from .services.devises import TauxIndisponible, taux


class PublicRateView(APIView):
    """Combien vaut la devise de ce salon dans une autre."""

    permission_classes = [AllowAny, IsTenantResolved]
    throttle_scope = "public_read"

    def get(self, request):
        tenant = Tenant.objects.filter(pk=request.tenant_id).first()
        if tenant is None:
            return Response(
                {"detail": "Salon introuvable.", "code": "tenant_not_found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        cible = (request.query_params.get("vers") or "").upper()
        connues = {code for code, _ in Tenant.Currency.choices}
        if cible not in connues:
            return Response(
                {
                    "detail": "Devise non proposée.",
                    "code": "devise_inconnue",
                    "choices": sorted(connues),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if cible == tenant.currency:
            return Response({"de": tenant.currency, "vers": cible, "taux": "1"})

        try:
            facteur = taux(tenant.currency, cible)
        except TauxIndisponible as exc:
            # 503 : la demande est bonne, c'est le service de taux qui ne
            # repond pas. L'ecran retombe alors sur la devise du salon, ce
            # qui est toujours exact.
            return Response(
                {"detail": str(exc), "code": "taux_indisponible"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(
            {"de": tenant.currency, "vers": cible, "taux": str(facteur)}
        )
