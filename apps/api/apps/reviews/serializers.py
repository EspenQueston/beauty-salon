from decimal import Decimal

from rest_framework import serializers

from .models import Review


class PublicReviewSerializer(serializers.ModelSerializer):
    """Avis tel qu'il apparait sur le mini-site.

    Ni identifiant de cliente, ni identifiant de rendez-vous : la page est
    publique, et le nom de la prestation suffit a situer l'avis.
    """

    service_name = serializers.CharField(source="booking.service_name", read_only=True)
    detail = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = (
            "id",
            "author_name",
            "rating",
            "detail",
            "comment",
            "service_name",
            "created_at",
        )

    def get_detail(self, review) -> list:
        return review.detail()


class ReviewInvitationSerializer(serializers.Serializer):
    """Contexte affiche au-dessus du formulaire de notation."""

    salon_name = serializers.CharField()
    service_name = serializers.CharField()
    staff_member_name = serializers.CharField(allow_blank=True)
    starts_at = serializers.DateTimeField()
    customer_name = serializers.CharField()


def _critere():
    """Un critere : de 1 a 5, ou rien du tout.

    `allow_null` et non `required=False` seulement : le formulaire envoie
    tous les champs, et une etoile non cliquee part a `null`. Refuser le null
    obligerait la page a filtrer ses propres champs avant l'envoi, ce qui est
    exactement le genre de logique qui finit par diverger entre les deux
    cotes.
    """
    return serializers.IntegerField(
        min_value=1, max_value=5, required=False, allow_null=True
    )


class ReviewCreateSerializer(serializers.Serializer):
    """Ce que la cliente envoie : cinq critères et, si elle veut, un texte.

    La note d'ensemble n'est pas demandee - elle se calcule a partir des
    criteres. L'accepter du client permettrait a un avis de porter « 5 sur
    5 » au-dessus de cinq criteres a 1, et ce serait cette note-la qui
    compterait dans la moyenne publique.
    """

    token = serializers.CharField()

    rating_result = _critere()
    rating_welcome = _critere()
    rating_punctuality = _critere()
    rating_cleanliness = _critere()
    rating_value = _critere()

    comment = serializers.CharField(required=False, allow_blank=True, max_length=2000)

    # Champ piege : invisible pour une humaine, rempli par les robots.
    website = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if not any(attrs.get(field) for field, _ in Review.CRITERIA):
            # Un avis sans aucune etoile ne dit rien et fausserait la moyenne
            # avec une note d'ensemble inventee.
            raise serializers.ValidationError(
                {"rating_result": "Notez au moins un critère."}
            )
        return attrs

    def overall(self) -> int:
        """La note d'ensemble : moyenne des criteres donnes, arrondie."""
        notes = [
            self.validated_data[field]
            for field, _ in Review.CRITERIA
            if self.validated_data.get(field)
        ]
        # Arrondi au plus proche, a mi-chemin vers le haut : une moyenne de
        # 3,5 donne 4. Le contraire ferait perdre une etoile a un salon pour
        # une demi-note, ce qui se voit sur une fiche a cinq crans.
        return int(Decimal(sum(notes)) / Decimal(len(notes)) + Decimal("0.5"))


class DashboardReviewSerializer(serializers.ModelSerializer):
    """Vue du salon : lecture seule, mais complete.

    Le salon voit tout, y compris les avis masques par l'equipe plateforme —
    lui cacher un avis retire ne ferait que lui faire croire a un bug.
    """

    service_name = serializers.CharField(source="booking.service_name", read_only=True)
    staff_member_name = serializers.CharField(
        source="booking.staff_member.name", read_only=True
    )
    booking_starts_at = serializers.DateTimeField(
        source="booking.starts_at", read_only=True
    )
    detail = serializers.SerializerMethodField()

    def get_detail(self, review) -> list:
        return review.detail()

    class Meta:
        model = Review
        fields = (
            "id",
            "author_name",
            "rating",
            "detail",
            "comment",
            "status",
            "service_name",
            "staff_member_name",
            "booking_starts_at",
            "created_at",
        )
