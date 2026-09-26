"""Le domaine personnalise, vu du tableau de bord (offre Pro).

Reserve au proprietaire : relier un domaine engage l'identite publique du
salon. Demander et verifier exigent l'offre Pro, cote serveur ; consulter et
retirer restent possibles sans elle — un salon redescendu a Standard doit
pouvoir voir son domaine en pause, et le retirer.
"""

from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Membership
from apps.billing.droits import ExigeFonctionPro
from apps.billing.models import ProCapability
from apps.common.permissions import HasTenantRole, IsTenantMember
from apps.tenants.models import Tenant

from . import personnalises
from .models import DomainClaim
from .services import platform_hostname

PROPRIETAIRE = (Membership.Role.OWNER,)


class _Proprietaire:
    permission_classes = [IsTenantMember, HasTenantRole]
    required_roles = PROPRIETAIRE
    safe_roles = PROPRIETAIRE


class _ProprietairePro:
    permission_classes = [IsTenantMember, HasTenantRole, ExigeFonctionPro]
    required_roles = PROPRIETAIRE
    safe_roles = PROPRIETAIRE
    fonction_pro = ProCapability.Code.CUSTOM_DOMAIN


class DemandeSerializer(serializers.Serializer):
    hostname = serializers.CharField(max_length=300)


def _en_donnees(demande: DomainClaim, tenant: Tenant) -> dict:
    relie = demande.status == DomainClaim.Status.CONNECTED
    return {
        "id": str(demande.id),
        "hostname": demande.hostname,
        "status": demande.status,
        "relie": relie,
        # Relie mais servi seulement si le salon a (encore) Pro.
        "en_pause": relie and not personnalises.domaine_perso_ouvert(demande.tenant_id),
        "derniere_erreur": demande.last_error,
        "verifie_le": demande.last_checked_at,
        "consignes": personnalises.consignes(demande, tenant.slug),
        "adresse_gratuite": platform_hostname(tenant.slug),
    }


class DomainesView(APIView):
    """GET : les domaines du salon. POST : en demander un (offre Pro)."""

    required_roles = PROPRIETAIRE
    safe_roles = PROPRIETAIRE
    fonction_pro = ProCapability.Code.CUSTOM_DOMAIN

    def get_permissions(self):
        # Consulter : proprietaire. Demander : proprietaire, et offre Pro.
        permissions = [IsTenantMember(), HasTenantRole()]
        if self.request.method == "POST":
            permissions.append(ExigeFonctionPro())
        return permissions

    def get(self, request):
        tenant = Tenant.objects.get(pk=request.tenant_id)
        demandes = DomainClaim.objects.order_by("-created_at")
        return Response([_en_donnees(demande, tenant) for demande in demandes])

    def post(self, request):
        entree = DemandeSerializer(data=request.data)
        entree.is_valid(raise_exception=True)
        tenant = Tenant.objects.get(pk=request.tenant_id)
        try:
            demande = personnalises.demander(
                request.tenant_id, entree.validated_data["hostname"], request.user
            )
        except personnalises.DomaineRefuse as refus:
            code_http = (
                status.HTTP_409_CONFLICT
                if refus.code == "deja_pris"
                else status.HTTP_400_BAD_REQUEST
            )
            return Response({"detail": str(refus), "code": refus.code}, status=code_http)
        return Response(_en_donnees(demande, tenant), status=status.HTTP_201_CREATED)


class DomaineVerifierView(_ProprietairePro, APIView):
    """Lit le DNS et relie le domaine si la preuve y est."""

    throttle_scope = "domain_check"

    def post(self, request, pk):
        demande = get_object_or_404(DomainClaim.objects.all(), pk=pk)
        tenant = Tenant.objects.get(pk=request.tenant_id)
        try:
            demande = personnalises.verifier(demande, request.user)
        except personnalises.DomaineRefuse as refus:
            demande.refresh_from_db()
            return Response(
                {"detail": str(refus), "code": refus.code, "domaine": _en_donnees(demande, tenant)},
                status=status.HTTP_409_CONFLICT
                if refus.code == "deja_pris"
                else status.HTTP_400_BAD_REQUEST,
            )
        return Response(_en_donnees(demande, tenant))


class DomaineView(_Proprietaire, APIView):
    """Retirer un domaine : toujours possible, meme sans Pro."""

    def delete(self, request, pk):
        demande = get_object_or_404(DomainClaim.objects.all(), pk=pk)
        personnalises.retirer(demande, request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)
