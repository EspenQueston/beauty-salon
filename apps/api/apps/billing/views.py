"""Abonnement vu par le salon : l'etat, les offres, le paiement.

Le salon consulte son abonnement, choisit une offre, paie hors ligne et
declare son paiement. Il ne modifie jamais son abonnement lui-meme : seule
l'approbation d'un administrateur ouvre une periode.

La facturation regarde le proprietaire, pas l'equipe : une prestataire n'a
pas a voir ce que le salon paie a la plateforme. Seul l'etat de l'acces est
lisible par tous les membres — c'est lui qui explique a chacun pourquoi le
tableau de bord est en lecture seule.
"""

from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Membership
from apps.common.permissions import HasTenantRole, IsTenantMember

from . import services
from .models import (
    Invoice,
    PlatformPaymentMethod,
    Subscription,
    SubscriptionPaymentRequest,
    type_du_qr,
)
from .serializers import (
    InvoiceSerializer,
    MoyenDeReglementSerializer,
    PaymentRequestCreateSerializer,
    PaymentRequestSerializer,
    SubscriptionSerializer,
    acces_en_donnees,
)

OWNERS = (Membership.Role.OWNER,)


class _ProprietaireSeulement:
    permission_classes = [IsTenantMember, HasTenantRole]
    required_roles = OWNERS
    safe_roles = OWNERS


class SubscriptionView(_ProprietaireSeulement, APIView):
    def get(self, request):
        subscription = get_object_or_404(
            Subscription.objects.select_related("plan", "tenant"),
            tenant_id=request.tenant_id,
        )
        return Response(SubscriptionSerializer(subscription, context={"request": request}).data)


class AccesView(APIView):
    """L'etat de l'acces, pour tous les membres du salon.

    C'est ce que lit la banniere du tableau de bord : « essai jusqu'au… »,
    « lecture seule depuis le… ». Ni montant ni moyen de paiement ici.
    """

    permission_classes = [IsTenantMember]

    def get(self, request):
        abonnement = (
            Subscription.objects.select_related("plan").filter(tenant_id=request.tenant_id).first()
        )
        acces = services.acces_de(abonnement)
        membership = getattr(request, "membership", None)
        proprietaire = bool(membership and membership.role == Membership.Role.OWNER)
        return Response(
            {
                **acces_en_donnees(acces),
                "statut": abonnement.status if abonnement else "",
                "statut_libelle": abonnement.get_status_display() if abonnement else "",
                "offre": abonnement.plan.name if abonnement else "",
                "offre_code": abonnement.plan.code if abonnement else "",
                # Pour le bouton « Passer à l'annuel » de la barre du haut.
                # Proprietaire seulement : elle porte des prix, et ce que le
                # salon paie a la plateforme ne regarde pas l'equipe.
                "montee_en_gamme": services.montee_en_gamme(abonnement) if proprietaire else None,
                "paiement_en_attente": bool(
                    abonnement
                    and abonnement.payment_requests.filter(
                        status=SubscriptionPaymentRequest.Status.PENDING
                    ).exists()
                ),
                "peut_payer": proprietaire,
            }
        )


class OffresView(_ProprietaireSeulement, APIView):
    """Ce que le salon peut acheter, et comment le payer.

    Pays par pays, devise par devise : les prix configures, l'economie de
    l'annee face a douze mois, et les moyens de reglement utilisables. Une
    devise sans prix ou sans moyen n'apparait pas.
    """

    def get(self, request):
        from apps.tenants.models import Tenant

        tenant = Tenant.objects.filter(pk=request.tenant_id).first()
        pays = []
        for entree in services.catalogue_de_paiement():
            pays.append(
                {
                    "code": entree["code"],
                    "nom": entree["nom"],
                    "devises": [
                        {
                            "code": devise["code"],
                            "nom": devise["nom"],
                            "plans": [
                                {
                                    "code": offre["plan"].code,
                                    "nom": offre["plan"].name,
                                    "description": offre["plan"].description,
                                    "mois": offre["plan"].billing_months,
                                    "montant": str(offre["montant"]),
                                }
                                for offre in devise["plans"]
                            ],
                            "economie": (
                                {
                                    "montant": str(devise["economie"]["montant"]),
                                    "pourcentage": devise["economie"]["pourcentage"],
                                    "douze_mois": str(devise["economie"]["douze_mois"]),
                                }
                                if devise["economie"]
                                else None
                            ),
                            "moyens": MoyenDeReglementSerializer(
                                devise["moyens"], many=True, context={"request": request}
                            ).data,
                        }
                        for devise in entree["devises"]
                    ],
                }
            )
        return Response(
            {
                "pays": pays,
                # Pour preselectionner ce qui correspond au salon.
                "suggestion": {
                    "pays": getattr(tenant, "country", ""),
                    "devise": getattr(tenant, "currency", ""),
                },
            }
        )


class QrCodeView(_ProprietaireSeulement, APIView):
    """Le QR code d'un moyen de reglement, pour les proprietaires de salon.

    Le fichier vit sous `prive/` : il ne sort que par ici. Un moyen inactif ou
    incomplet ne montre plus son QR code, meme a qui en garde l'adresse.
    """

    def get(self, request, pk):
        moyen = PlatformPaymentMethod.objects.filter(pk=pk).first()
        if (
            moyen is None
            or not moyen.est_utilisable
            or moyen.kind not in PlatformPaymentMethod.QR_KINDS
            or not moyen.qr_image
        ):
            raise Http404("QR code indisponible.")
        try:
            fichier = moyen.qr_image.open("rb")
        except FileNotFoundError as erreur:
            raise Http404("QR code introuvable.") from erreur
        # Le type vient de la liste des extensions permises, jamais d'une
        # devinette sur le nom : un fichier servi comme page HTML sur le
        # domaine de l'API lirait la session de qui l'ouvre.
        reponse = FileResponse(fichier, content_type=type_du_qr(moyen.qr_image.name))
        reponse["Cache-Control"] = "private, max-age=300"
        reponse["X-Content-Type-Options"] = "nosniff"
        return reponse


class PaiementsView(_ProprietaireSeulement, APIView):
    """L'historique des paiements du salon, et la declaration d'un paiement."""

    throttle_scope = "subscription_payment"

    def get_throttles(self):
        # Lire son historique ne compte pas ; seul l'envoi est borne.
        return super().get_throttles() if self.request.method == "POST" else []

    def get(self, request):
        demandes = SubscriptionPaymentRequest.objects.select_related("plan", "proof")
        return Response(
            PaymentRequestSerializer(demandes, many=True, context={"request": request}).data
        )

    def post(self, request):
        entree = PaymentRequestCreateSerializer(data=request.data)
        entree.is_valid(raise_exception=True)
        donnees = entree.validated_data
        try:
            demande = services.soumettre_paiement(
                tenant_id=request.tenant_id,
                utilisateur=request.user,
                code_offre=donnees["plan"],
                pays=donnees["country"].upper(),
                devise=donnees["currency"].upper(),
                moyen_id=donnees["method"],
                reference=donnees["reference"],
                preuve=donnees.get("proof"),
            )
        except services.PaiementRefuse as refus:
            code_http = (
                status.HTTP_409_CONFLICT
                if refus.code in ("demande_en_attente", "reference_deja_utilisee")
                else status.HTTP_400_BAD_REQUEST
            )
            return Response({"detail": str(refus), "code": refus.code}, status=code_http)

        demande = SubscriptionPaymentRequest.objects.select_related("plan", "proof").get(
            pk=demande.pk
        )
        return Response(
            PaymentRequestSerializer(demande, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class InvoiceViewSet(_ProprietaireSeulement, mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = InvoiceSerializer
    pagination_class = None

    def get_queryset(self):
        return Invoice.objects.select_related("subscription")
