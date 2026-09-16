"""Serialisation de l'espace cliente."""

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.accounts.models import User

from .models import ClientProfile


class ClientSignupSerializer(serializers.Serializer):
    """Creation d'un compte cliente.

    Le telephone est obligatoire, l'e-mail aussi : le premier sert au salon
    pour confirmer, le second a la cliente pour recuperer son mot de passe.
    WhatsApp et WeChat restent facultatifs - ce sont des preferences de
    contact, pas des identifiants.
    """

    full_name = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=32)
    password = serializers.CharField(write_only=True, min_length=8, max_length=128)

    whatsapp = serializers.CharField(max_length=32, required=False, allow_blank=True)
    wechat = serializers.CharField(max_length=64, required=False, allow_blank=True)

    def validate_email(self, value):
        email = value.strip().lower()
        if User.objects.filter(email=email).exists():
            # Message neutre : il ne dit pas si ce compte est celui d'une
            # cliente ou d'un salon.
            raise serializers.ValidationError(
                "Un compte existe déjà avec cette adresse. Connectez-vous."
            )
        return email

    def validate_password(self, value):
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        return value

    def validate_phone(self, value):
        phone = value.strip()
        if len(phone) < 6:
            raise serializers.ValidationError("Numéro de téléphone trop court.")
        return phone


class ClientProfileSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="user.display_name")
    email = serializers.EmailField(source="user.email", read_only=True)
    phone = serializers.CharField(source="user.phone")
    preferred_salon_name = serializers.CharField(
        source="preferred_salon.name", read_only=True, default=""
    )
    preferred_salon_slug = serializers.CharField(
        source="preferred_salon.slug", read_only=True, default=""
    )

    class Meta:
        model = ClientProfile
        fields = (
            "full_name",
            "email",
            "phone",
            "whatsapp",
            "wechat",
            "preferred_salon",
            "preferred_salon_name",
            "preferred_salon_slug",
        )

    def update(self, instance, validated_data):
        # `source="user.x"` produit un dictionnaire imbrique : DRF ne sait pas
        # l'ecrire tout seul sur une relation.
        user_data = validated_data.pop("user", {})
        if user_data:
            for field, value in user_data.items():
                setattr(instance.user, field, value)
            instance.user.save(update_fields=[*user_data.keys()])

        return super().update(instance, validated_data)


class ClientBookingSerializer(serializers.Serializer):
    """Une ligne d'historique, deja aplatie par le service.

    Serializer explicite plutot que ModelSerializer : les lignes viennent de
    contextes de base differents et ne sont plus des instances Django au
    moment ou elles arrivent ici.
    """

    id = serializers.CharField()
    salon_name = serializers.CharField()
    salon_slug = serializers.CharField()
    currency = serializers.CharField()
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()
    status = serializers.CharField()
    service_name = serializers.CharField()
    staff_member_name = serializers.CharField()
    total_amount = serializers.CharField()
    deposit_amount = serializers.CharField()
    options_snapshot = serializers.ListField()
    travel_zone_name = serializers.CharField()
    payment_token = serializers.CharField(allow_blank=True)
    checkin_token = serializers.CharField(allow_blank=True)
    # Le code court : ce que la cliente lit à voix haute quand la caméra du
    # salon ne coopère pas.
    checkin_code = serializers.CharField(allow_blank=True)
    # Où en est l'avis : le serveur tranche, l'écran affiche.
    reviewed = serializers.BooleanField()
    can_review = serializers.BooleanField()
    review_token = serializers.CharField(allow_blank=True)
    review_until = serializers.CharField(allow_blank=True)
    # Ouvre la page de suivi du rendez-vous. Toujours present : c'est le
    # chemin de retour quand la page de reglement a ete fermee, et celui
    # qu'on rouvre plus tard pour retrouver ce qu'on a paye.
    status_token = serializers.CharField()
    can_forget = serializers.BooleanField()
    address = serializers.CharField()
