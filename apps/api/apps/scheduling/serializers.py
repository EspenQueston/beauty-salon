from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from apps.catalog.models import Service
from apps.common.serializers import TenantPrimaryKeyRelatedField
from apps.customers.models import Customer
from apps.staff.models import StaffMember

from .models import AvailabilityException, Booking, BusinessHours, WaitlistEntry

MAX_RANGE_DAYS = 31


class SlotSerializer(serializers.Serializer):
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()
    staff_member_id = serializers.CharField()


class AvailabilityQuerySerializer(serializers.Serializer):
    service = serializers.UUIDField()
    staff_member = serializers.UUIDField(required=False, allow_null=True)
    # Les options allongent la prestation : sans elles, les creneaux
    # proposes seraient calcules sur une duree qui n'est pas la bonne.
    options = serializers.ListField(
        child=serializers.UUIDField(), required=False, default=list, max_length=20
    )
    date_from = serializers.DateField()
    date_to = serializers.DateField()

    def validate(self, attrs):
        if attrs["date_to"] < attrs["date_from"]:
            raise serializers.ValidationError(
                {"date_to": "La date de fin précède la date de début."}
            )
        # Borne dure : sans elle, une requete sur trois ans ferait travailler
        # le moteur pour rien et servirait de levier de deni de service.
        if (attrs["date_to"] - attrs["date_from"]).days > MAX_RANGE_DAYS:
            raise serializers.ValidationError(
                {"date_to": f"Plage limitée à {MAX_RANGE_DAYS} jours."}
            )
        return attrs


class PublicBookingCreateSerializer(serializers.Serializer):
    service = serializers.UUIDField()
    staff_member = serializers.UUIDField(required=False, allow_null=True)
    starts_at = serializers.DateTimeField()

    full_name = serializers.CharField(max_length=150)
    phone = serializers.CharField(max_length=32)
    email = serializers.EmailField(required=False, allow_blank=True)
    contact_preference = serializers.ChoiceField(
        choices=Customer.ContactPreference.choices,
        default=Customer.ContactPreference.WHATSAPP,
    )
    customer_note = serializers.CharField(required=False, allow_blank=True, max_length=1000)

    # ----- prestation a domicile -------------------------------------------
    # La presence d'une zone est le signal « chez moi » : pour une prestation
    # proposee dans les deux lieux, c'est elle qui tranche. La vue verifie
    # ensuite que la zone appartient bien au salon et que la prestation se
    # deplace - un identifiant devine ne doit pas offrir un tarif d'une autre
    # zone, ni un deplacement pour une prestation qui n'en fait pas.
    options = serializers.ListField(
        child=serializers.UUIDField(), required=False, default=list, max_length=20
    )

    # Panier : seuls l'identifiant et la quantite circulent. Le prix est relu
    # en base, sinon il suffirait de modifier la requete pour s'offrir une
    # perruque a zero.
    items = serializers.ListField(
        child=serializers.DictField(), required=False, default=list, max_length=20
    )
    # Exigences pour lesquelles la cliente dit apporter le necessaire. On la
    # croit sur parole : lui refuser sa propre perruque serait absurde.
    owned_requirements = serializers.ListField(
        child=serializers.UUIDField(), required=False, default=list, max_length=20
    )

    travel_zone = serializers.UUIDField(required=False, allow_null=True)
    address = serializers.CharField(required=False, allow_blank=True, max_length=255)

    marketing_consent = serializers.BooleanField(default=False)
    # Case a cocher obligatoire : le salon doit pouvoir opposer sa politique
    # d'annulation en cas de litige.
    accepts_policy = serializers.BooleanField()

    # La langue de lecture du mini-site, transmise par le serveur Next.
    #
    # Un choix ferme et non un champ libre : cette valeur finit dans le nom
    # d un gabarit d e-mail, et une chaine arbitraire y chercherait un fichier
    # que personne n a ecrit.
    language = serializers.ChoiceField(
        choices=[("fr", "fr"), ("en", "en")], default="fr"
    )

    # Champ piege : invisible pour une humaine, rempli par les robots.
    website = serializers.CharField(required=False, allow_blank=True)

    def validate_accepts_policy(self, value):
        if not value:
            raise serializers.ValidationError(
                "La politique d'annulation doit être acceptée."
            )
        return value

    def validate_starts_at(self, value):
        if value < timezone.now() - timedelta(minutes=1):
            raise serializers.ValidationError("Ce créneau est déjà passé.")
        return value


class BookingSerializer(serializers.ModelSerializer):
    deposit_proof = serializers.SerializerMethodField()

    customer_name = serializers.CharField(source="customer.full_name", read_only=True)
    customer_phone = serializers.CharField(source="customer.phone", read_only=True)
    # L'adresse, pour ecrire depuis l'agenda. Elle peut etre vide : une
    # cliente peut reserver par telephone sans en donner, et ce n'est pas
    # une anomalie - l'ecran doit simplement ne rien afficher.
    customer_email = serializers.CharField(source="customer.email", read_only=True)
    staff_member_name = serializers.CharField(source="staff_member.name", read_only=True)

    class Meta:
        model = Booking
        fields = (
            "id",
            "starts_at",
            "ends_at",
            "status",
            "source",
            "service",
            "service_name",
            "staff_member",
            "staff_member_name",
            "customer",
            "customer_name",
            "customer_phone",
            "customer_email",
            "total_amount",
            "deposit_amount",
            "deposit_paid",
            "deposit_paid_at",
            "deposit_method",
            "deposit_received",
            "deposit_proof",
            "location_mode",
            "address",
            "options_snapshot",
            "options_amount",
            "items_snapshot",
            "items_amount",
            "travel_zone_name",
            "travel_fee_amount",
            "customer_note",
            "internal_note",
            "created_at",
        )
        read_only_fields = (
            "service_name",
            "options_snapshot",
            "options_amount",
            "items_snapshot",
            "items_amount",
            "travel_zone_name",
            "travel_fee_amount",
            "created_at",
            "deposit_paid_at",
            "deposit_method",
            "deposit_received",
        )

    def get_deposit_proof(self, booking) -> dict | None:
        """Ce que la cliente a envoye pour dire qu'elle a paye.

        Le salon en a besoin pour retrouver le versement dans son
        application : c'est la seule facon de verifier, puisque nous ne
        voyons jamais le paiement.
        """
        proof = getattr(booking, "deposit_proof", None)
        if proof is None:
            return None

        # `media_url` et non `file.url` : la capture est rangee en prive, et
        # son adresse doit donc etre celle de la route authentifiee. La
        # recalculer ici rouvrirait le trou a cet endroit precis.
        from apps.media.serializers import media_url

        request = self.context.get("request")
        url = media_url(proof.image, request) if proof.image_id else ""

        return {
            "status": proof.status,
            "channel": proof.channel,
            "reference": proof.reference,
            "note": proof.note,
            "image_url": url,
            "submitted_at": proof.submitted_at,
            "rejection_reason": proof.rejection_reason,
        }


class PublicBookingConfirmationSerializer(serializers.ModelSerializer):
    """Reponse renvoyee a la cliente : rien de ce qui est interne au salon."""

    staff_member_name = serializers.CharField(source="staff_member.name", read_only=True)

    # Laissez-passer pour la page de paiement.
    #
    # La cliente n'a pas de compte : sans ce jeton, elle ne pourrait pas
    # revenir regler son acompte apres avoir ferme l'onglet, et un
    # identifiant de rendez-vous devine ouvrirait la page de n'importe qui.
    payment_token = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = (
            "id",
            "payment_token",
            "starts_at",
            "ends_at",
            "status",
            "service_name",
            "staff_member_name",
            "total_amount",
            "deposit_amount",
            "options_snapshot",
            "options_amount",
            "items_snapshot",
            "items_amount",
            "travel_zone_name",
            "travel_fee_amount",
        )

    def get_payment_token(self, booking) -> str:
        """Vide quand rien n'est a payer en ligne."""
        if booking.status != Booking.Status.PENDING_PAYMENT:
            return ""

        from apps.payments.tokens import payment_token

        return payment_token(booking)

    def to_representation(self, instance):
        from apps.translations.booking import public_booking_labels

        data = super().to_representation(instance)
        data.update(public_booking_labels(instance, instance.language))
        return data


class BusinessHoursSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessHours
        fields = ("id", "staff_member", "weekday", "starts_at", "ends_at")

    def validate(self, attrs):
        starts_at = attrs.get("starts_at") or getattr(self.instance, "starts_at", None)
        ends_at = attrs.get("ends_at") or getattr(self.instance, "ends_at", None)
        if starts_at and ends_at and ends_at <= starts_at:
            raise serializers.ValidationError({"ends_at": "La fermeture précède l'ouverture."})
        return attrs


class AvailabilityExceptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AvailabilityException
        fields = ("id", "staff_member", "kind", "starts_at", "ends_at", "reason")

    def validate(self, attrs):
        starts_at = attrs.get("starts_at") or getattr(self.instance, "starts_at", None)
        ends_at = attrs.get("ends_at") or getattr(self.instance, "ends_at", None)
        if starts_at and ends_at and ends_at <= starts_at:
            raise serializers.ValidationError({"ends_at": "La fin précède le début."})
        return attrs


class StaffBookingCreateSerializer(serializers.Serializer):
    """Saisie manuelle par la reception : moins de garde-fous que le public,
    parce que le salon a le droit de forcer un rendez-vous hors grille."""

    service = TenantPrimaryKeyRelatedField(Service)
    staff_member = TenantPrimaryKeyRelatedField(StaffMember)
    customer = TenantPrimaryKeyRelatedField(Customer, required=False, allow_null=True)
    full_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True)
    starts_at = serializers.DateTimeField()
    internal_note = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if not attrs.get("customer") and not (attrs.get("full_name") and attrs.get("phone")):
            raise serializers.ValidationError(
                "Indiquez une cliente existante, ou un nom et un téléphone."
            )
        return attrs


class WaitlistEntrySerializer(serializers.ModelSerializer):
    service_name = serializers.CharField(source="service.name", read_only=True)
    staff_member_name = serializers.CharField(
        source="staff_member.name", read_only=True, default=""
    )

    class Meta:
        model = WaitlistEntry
        fields = (
            "id",
            "service",
            "service_name",
            "staff_member",
            "staff_member_name",
            "full_name",
            "phone",
            "email",
            "preferred_from",
            "preferred_to",
            "note",
            "status",
            "contacted_at",
            "created_at",
        )
        read_only_fields = ("contacted_at", "created_at")

    def validate(self, attrs):
        start = attrs.get("preferred_from")
        end = attrs.get("preferred_to")
        if start and end and end < start:
            raise serializers.ValidationError(
                {"preferred_to": "La fin de la période précède son début."}
            )
        return attrs


class PublicWaitlistSerializer(WaitlistEntrySerializer):
    """Inscription depuis le mini-site.

    Le statut n'est pas dans les champs modifiables : une inscription arrive
    toujours « en attente », et seul le salon la fait avancer.
    """

    class Meta(WaitlistEntrySerializer.Meta):
        fields = (
            "service",
            "staff_member",
            "full_name",
            "phone",
            "email",
            "preferred_from",
            "preferred_to",
            "note",
        )
