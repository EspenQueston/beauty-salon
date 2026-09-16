from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from apps.tenants.models import Tenant

from .models import Invitation, Membership, User


class TenantSummarySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    slug = serializers.CharField()
    status = serializers.CharField()
    timezone = serializers.CharField()
    currency = serializers.CharField()


class MembershipSerializer(serializers.ModelSerializer):
    tenant = TenantSummarySerializer(read_only=True)
    user_email = serializers.EmailField(source="user.email", read_only=True)
    user_name = serializers.CharField(source="user.display_name", read_only=True)

    class Meta:
        model = Membership
        fields = ("id", "role", "status", "tenant", "user_email", "user_name")
        read_only_fields = ("status",)


class UserSerializer(serializers.ModelSerializer):
    memberships = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "phone",
            "display_name",
            "locale",
            "is_platform_admin",
            "memberships",
        )

    def get_memberships(self, user):
        queryset = user.memberships.filter(status=Membership.Status.ACTIVE).select_related(
            "tenant"
        )
        return MembershipSerializer(queryset, many=True).data


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})


class SignupSerializer(serializers.Serializer):
    """Inscription d'un salon et de son proprietaire, en un formulaire."""

    salon_name = serializers.CharField(max_length=120)
    slug = serializers.SlugField(max_length=63)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=10)
    display_name = serializers.CharField(max_length=120, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True)

    country = serializers.ChoiceField(
        choices=Tenant.Country.choices, default=Tenant.Country.CONGO
    )
    timezone_name = serializers.CharField(max_length=64, default="Africa/Brazzaville")
    currency = serializers.ChoiceField(
        choices=Tenant.Currency.choices, default=Tenant.Currency.XAF
    )
    accepts_terms = serializers.BooleanField()

    # Couleurs composees sur la page d'accueil avant l'inscription. Elles
    # arrivent de l'exterieur : seules trois cles sont acceptees, et chacune
    # doit etre un code hexadecimal — sans quoi une valeur libre finirait
    # injectee telle quelle dans le CSS du mini-site.
    theme_config = serializers.DictField(
        child=serializers.RegexField(r"^#[0-9a-fA-F]{6}$"),
        required=False,
    )

    def validate_theme_config(self, value):
        allowed = {"primary", "accent", "surface"}
        unknown = set(value) - allowed
        if unknown:
            raise serializers.ValidationError(
                f"Clés de thème inconnues : {', '.join(sorted(unknown))}."
            )
        return value

    def validate_slug(self, value):
        value = value.strip().lower()
        if value in settings.RESERVED_SUBDOMAINS:
            raise serializers.ValidationError("Cette adresse est réservée.")
        if Tenant.objects.filter(slug=value).exists():
            raise serializers.ValidationError("Cette adresse est déjà prise.")
        return value

    def validate_timezone_name(self, value):
        try:
            ZoneInfo(value)
        except Exception:
            raise serializers.ValidationError("Fuseau horaire inconnu.") from None
        return value

    def validate_accepts_terms(self, value):
        if not value:
            raise serializers.ValidationError("Vous devez accepter les conditions.")
        return value

    def validate_password(self, value):
        # Les regles de robustesse sont celles de Django, pour rester
        # coherent avec la reinitialisation et l'admin.
        validate_password(value)
        return value


class SlugAvailabilitySerializer(serializers.Serializer):
    slug = serializers.SlugField(max_length=63)


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    password = serializers.CharField(write_only=True, min_length=10)

    def validate_password(self, value):
        validate_password(value)
        return value


class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=10)

    def validate_new_password(self, value):
        validate_password(value, user=self.context.get("user"))
        return value


class InvitationSerializer(serializers.ModelSerializer):
    status = serializers.CharField(read_only=True)
    invited_by_name = serializers.CharField(source="invited_by.email", read_only=True)

    class Meta:
        model = Invitation
        fields = (
            "id",
            "email",
            "role",
            "status",
            "expires_at",
            "accepted_at",
            "revoked_at",
            "invited_by_name",
            "created_at",
        )
        read_only_fields = ("expires_at", "accepted_at", "revoked_at", "created_at")


class InvitationCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=Membership.Role.choices)


class AcceptInvitationSerializer(serializers.Serializer):
    token = serializers.CharField()
    # Requis uniquement si aucun compte n'existe encore pour cette adresse.
    password = serializers.CharField(
        write_only=True, min_length=10, required=False, allow_blank=True
    )
    display_name = serializers.CharField(max_length=120, required=False, allow_blank=True)

    def validate(self, attrs):
        if attrs.get("password"):
            validate_password(attrs["password"])
        return attrs
