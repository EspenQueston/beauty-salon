"""Cas A : configuration propriétaire et historique privé du client par salon."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Membership
from apps.clients.views import IsClient
from apps.common.permissions import HasTenantRole, IsTenantMember

from . import clients
from .models import EvenementParrainage, PolitiqueSalon, RecompenseClient


class PolitiqueSerializer(serializers.ModelSerializer):
    class Meta:
        model = PolitiqueSalon
        exclude = ("id", "tenant", "created_at", "updated_at")

    def validate(self, attrs):
        obj = PolitiqueSalon(
            **{
                f.name: getattr(self.instance, f.name)
                for f in self.Meta.model._meta.fields
                if f.name not in {"id", "tenant"}
            }
        )
        for k, v in attrs.items():
            setattr(obj, k, v)
        try:
            obj.clean()
        except ValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        if self.instance and obj.active:
            from apps.tenants.models import Tenant

            if obj.devise != Tenant.objects.get(pk=self.instance.tenant_id).currency:
                raise serializers.ValidationError("Le plafond doit être dans la devise du salon.")
        return attrs


class ParrainageClientsSalonView(APIView):
    permission_classes = [IsTenantMember, HasTenantRole]
    required_roles = safe_roles = (Membership.Role.OWNER,)
    throttle_scope = "referral_check"

    def _configuration(self):
        return PolitiqueSalon.objects.get_or_create(
            tenant_id=self.request.tenant_id,
            defaults={
                "reservations_annulees_excluent": True,
                "attribution": "premier_code",
                "formule": "apres_promotions_prestation",
                "recompenses_par_reservation": 1,
                "annulation_declencheur": "maintenir",
                "annulation_utilisation": "restituer",
            },
        )[0]

    def get(self, request):
        p = self._configuration()
        ids = RecompenseClient.objects.values_list("pk", flat=True)
        evenements = EvenementParrainage.objects.filter(
            cas="A", tenant_id=request.tenant_id, ressource__in=ids
        ).values("id", "ressource", "action", "details", "cree_le")[:100]
        return Response(
            {"configuration": PolitiqueSerializer(p).data, "historique": list(evenements)}
        )

    @transaction.atomic
    def patch(self, request):
        from apps.tenants.models import Tenant

        Tenant.objects.select_for_update().get(pk=request.tenant_id)
        p = self._configuration()
        entree = PolitiqueSerializer(p, data=request.data, partial=True)
        entree.is_valid(raise_exception=True)
        entree.save()
        EvenementParrainage.objects.create(
            cas="A",
            tenant_id=request.tenant_id,
            ressource=p.pk,
            action="configuration",
            details={"acteur": str(request.user.pk), "champs": list(entree.validated_data)},
        )
        return Response(entree.data)


class ParrainageClientSalonView(APIView):
    permission_classes = [IsClient]
    throttle_scope = "referral_check"

    def get(self, request):
        if not request.user.email_verified_at:
            return Response({"actif": False, "verification_requise": True})
        return Response(clients.etat(request.user, request.tenant_id))


class DevisParrainageView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "referral_check"

    def get(self, request):
        from apps.catalog.models import Service
        from apps.clients.services import est_cliente
        from apps.scheduling.views_public import _resolve_options

        try:
            import uuid

            sid = uuid.UUID(request.query_params.get("service", ""))
            options = [uuid.UUID(v) for v in request.query_params.getlist("options")]
        except ValueError:
            return Response({"detail": "Prestation ou options invalides."}, status=400)
        if len(options) > 20:
            return Response(status=400)
        service = Service.objects.filter(pk=sid, active=True).first()
        if not service:
            return Response(status=404)
        selection = _resolve_options(service, options)
        if selection is None:
            return Response(status=400)
        initial = service.price_amount + sum((o.price_delta for o in selection), Decimal(0))
        reduction = Decimal(0)
        if est_cliente(request.user) and request.user.email_verified_at:
            r = (
                RecompenseClient.objects.filter(
                    parrain=request.user,
                    statut="disponible",
                    expire_le__gt=timezone.now(),
                    devise=service.tenant.currency,
                )
                .order_by("expire_le", "created_at")
                .first()
            )
            if r:
                reduction, _ = clients.prix(
                    initial, Decimal(0), r.taux, r.plafond_montant, r.devise
                )
        # Aucun moteur promotionnel n'existe ici ; son montant courant est réellement zéro.
        return Response(
            {
                "prix_initial": str(initial),
                "promotions": "0",
                "reduction_parrainage": str(reduction),
                "montant_final": str(initial - reduction),
                "code_actif": bool(clients.politique()),
            }
        )
