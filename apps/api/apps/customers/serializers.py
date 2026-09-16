from rest_framework import serializers

from apps.accounts.models import Membership
from apps.scheduling.models import Booking

from .models import Customer


class CustomerBookingSerializer(serializers.ModelSerializer):
    """Une ligne d'historique.

    `service_name` est l'instantane pris a la vente, pas une jointure : une
    prestation renommee ou supprimee ne doit pas effacer ce qui a ete fait.
    """

    staff_member_name = serializers.CharField(
        source="staff_member.name", read_only=True, default=""
    )

    class Meta:
        model = Booking
        fields = (
            "id",
            "starts_at",
            "ends_at",
            "status",
            "service_name",
            "staff_member_name",
            "total_amount",
            "options_snapshot",
            "internal_note",
        )


class CustomerSerializer(serializers.ModelSerializer):
    # Annotes par la vue. `default=0` couvre les cas ou le serializer est
    # utilise hors de la liste - creation, mise a jour - ou l'annotation
    # n'existe pas.
    booking_count = serializers.IntegerField(source="bookings_total", read_only=True, default=0)
    visit_count = serializers.IntegerField(source="visits", read_only=True, default=0)
    no_show_count = serializers.IntegerField(source="no_shows", read_only=True, default=0)
    cancelled_count = serializers.IntegerField(
        source="cancellations", read_only=True, default=0
    )
    last_booking_at = serializers.DateTimeField(
        source="last_booking", read_only=True, default=None
    )

    class Meta:
        model = Customer
        fields = (
            "id",
            "full_name",
            "phone",
            "email",
            "contact_preference",
            "marketing_consent",
            "marketing_consent_at",
            "private_notes",
            "booking_count",
            "visit_count",
            "no_show_count",
            "cancelled_count",
            "last_booking_at",
            "created_at",
        )
        read_only_fields = ("marketing_consent_at",)

    def to_representation(self, instance):
        data = super().to_representation(instance)

        # Les notes internes contiennent des informations sensibles :
        # allergies, sensibilite du cuir chevelu, historique medical evoque
        # en cabine. Seuls le proprietaire et le gerant y ont acces.
        membership = getattr(self.context.get("request"), "membership", None)
        if membership is None or membership.role not in (
            Membership.Role.OWNER,
            Membership.Role.MANAGER,
        ):
            data.pop("private_notes", None)

        return data
