"""Configuration du salon par son equipe."""

from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Membership
from apps.common.permissions import HasTenantRole, IsTenantMember
from apps.common.viewsets import TenantModelViewSet

from .models import SalonProfile, TravelZone

MANAGERS = (Membership.Role.OWNER, Membership.Role.MANAGER)
EVERYONE = (*MANAGERS, Membership.Role.RECEPTIONIST, Membership.Role.STAFF)

# Cles de theme acceptees. La liste est fermee : le salon choisit son
# apparence, il ne redefinit pas la structure du produit, et un JSON libre
# finirait injecte tel quel dans le CSS du mini-site.
THEME_KEYS = {"primary", "accent", "surface", "font", "radius"}


class ThemeConfigField(serializers.JSONField):
    def to_internal_value(self, data):
        data = super().to_internal_value(data)
        if not isinstance(data, dict):
            raise serializers.ValidationError("Le thème doit être un objet.")
        unknown = set(data) - THEME_KEYS
        if unknown:
            raise serializers.ValidationError(
                f"Clés de thème inconnues : {', '.join(sorted(unknown))}."
            )
        return data


class SalonProfileSerializer(serializers.ModelSerializer):
    theme_config = ThemeConfigField(required=False)

    class Meta:
        model = SalonProfile
        fields = (
            "description",
            "address",
            "city",
            "service_mode",
            "service_area",
            "latitude",
            "longitude",
            "phone",
            "whatsapp_number",
            "social_links",
            "theme_config",
            "logo",
            "banner",
            "about_title",
            "about_content",
            "about_image",
            "deposit_rate",
            "deposit_minimum",
            "deposit_covers_items",
            "cancellation_policy",
            "cancellation_deadline_hours",
            "late_policy",
            "late_tolerance_minutes",
            "slot_granularity_minutes",
            "buffer_minutes",
            "min_lead_time_minutes",
            "max_advance_days",
        )


    def validate(self, attrs):
        """Empeche les reglages qui ne proposeraient plus aucun creneau.

        Le piege est silencieux : un delai minimal de dix jours sur un agenda
        ouvert sur sept ne produit aucune erreur, il produit une liste vide.
        La cliente voit « aucune disponibilite », le salon voit un agenda
        vide, et personne ne relie les deux au reglage qui en est la cause.

        On compare donc les deux au moment de la saisie, ou l'on peut encore
        expliquer ce qui cloche.
        """
        lead = attrs.get(
            "min_lead_time_minutes",
            getattr(self.instance, "min_lead_time_minutes", 0),
        )
        horizon = attrs.get(
            "max_advance_days", getattr(self.instance, "max_advance_days", 30)
        )

        if lead >= horizon * 24 * 60:
            raise serializers.ValidationError(
                {
                    "min_lead_time_minutes": (
                        f"Ce délai ({lead // 60} h) dépasse la fenêtre de "
                        f"réservation ({horizon} jours) : plus aucun créneau "
                        "ne serait proposé."
                    )
                }
            )

        return attrs


class SalonProfileView(APIView):
    """Ressource unique : un salon a exactement un profil."""

    permission_classes = [IsTenantMember, HasTenantRole]
    required_roles = MANAGERS
    safe_roles = EVERYONE

    def get(self, request):
        profile = self._get_or_create(request)
        return Response(SalonProfileSerializer(profile).data)

    def patch(self, request):
        profile = self._get_or_create(request)
        serializer = SalonProfileSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    def _get_or_create(self, request) -> SalonProfile:
        profile = SalonProfile.objects.filter(tenant_id=request.tenant_id).first()
        if profile is None:
            # Premiere visite du dashboard : on cree la fiche vide plutot que
            # d'imposer une etape de creation explicite.
            profile = SalonProfile.objects.create(tenant_id=request.tenant_id)
        return profile


class TravelZoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = TravelZone
        fields = ("id", "name", "fee_amount", "position", "active")

    def validate_name(self, value):
        return value.strip()


class TravelZoneViewSet(TenantModelViewSet):
    """Grille des frais de deplacement du salon.

    Elle engage un tarif annonce publiquement : seuls le proprietaire et le
    gerant la modifient, mais la reception la consulte - c'est elle qui
    repond au telephone quand une cliente demande le prix chez elle.
    """

    serializer_class = TravelZoneSerializer
    model = TravelZone
    required_roles = MANAGERS
    safe_roles = EVERYONE
    pagination_class = None  # une grille de quartiers tient en une reponse
