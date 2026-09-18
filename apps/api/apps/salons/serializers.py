"""Serialisation du mini-site public.

Le mini-site se charge en *un* appel. Les marches vises tournent souvent sur
des reseaux mobiles lents et factures a la donnee : six requetes en cascade
pour afficher une page coutent bien plus cher que la charge utile elle-meme.
"""

from rest_framework import serializers

from apps.catalog.models import Service, ServiceCategory, ServiceOption
from apps.media.models import MediaAsset
from apps.scheduling.models import BusinessHours
from apps.staff.models import StaffMember

from .models import SalonProfile, TravelZone


class MediaAssetSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = MediaAsset
        # `content_type` sert au mini-site a distinguer une photo d'une
        # video : les deux vivent dans la meme galerie, mais l'une se rend
        # avec <img> et l'autre avec <video>.
        fields = (
            "id",
            "url",
            "content_type",
            "alt_text",
            "width",
            "height",
            "kind",
            "position",
            "featured",
        )

    def get_url(self, asset) -> str:
        request = self.context.get("request")
        url = asset.file.url
        return request.build_absolute_uri(url) if request else url


class PublicServiceOptionSerializer(serializers.ModelSerializer):
    """Options proposees a la cliente, avec ce qu'elles coutent en argent et
    en temps. Les deux comptent : le second decide du creneau."""

    class Meta:
        model = ServiceOption
        fields = (
            "id",
            "name",
            "description",
            "price_delta",
            "duration_delta_minutes",
        )


class PublicRequirementSerializer(serializers.Serializer):
    """Ce qu'il faut prevoir, et ce que le salon peut fournir.

    Les articles en rupture sont volontairement **conserves** dans la
    reponse, marques indisponibles : les faire disparaitre laisserait croire
    que le salon n'en vend pas, et la cliente irait chercher ailleurs ce
    qu'elle aurait pu reserver la semaine suivante.
    """

    id = serializers.CharField()
    label = serializers.CharField()
    detail = serializers.CharField()
    mandatory = serializers.BooleanField()
    products = serializers.ListField()


class PublicServiceSerializer(serializers.ModelSerializer):
    image = MediaAssetSerializer(read_only=True)
    staff_member_ids = serializers.SerializerMethodField()
    options = serializers.SerializerMethodField()
    requirements = serializers.SerializerMethodField()

    class Meta:
        model = Service
        fields = (
            "id",
            "name",
            "description",
            "duration_minutes",
            "price_kind",
            "price_amount",
            "requires_deposit",
            "location_mode",
            "image",
            "staff_member_ids",
            "options",
            "requirements",
        )

    def get_options(self, service) -> list:
        # Pre-groupees par la vue : evite une requete par prestation.
        grouped = self.context.get("options_by_service", {})
        return PublicServiceOptionSerializer(
            grouped.get(service.id, []), many=True
        ).data

    def get_requirements(self, service) -> list:
        grouped = self.context.get("requirements_by_service", {})
        return grouped.get(service.id, [])

    def get_staff_member_ids(self, service) -> list[str]:
        # Pre-calcule par la vue : evite une requete par prestation.
        mapping = self.context.get("staff_by_service", {})
        return [str(value) for value in mapping.get(service.id, [])]


class PublicCategorySerializer(serializers.ModelSerializer):
    services = serializers.SerializerMethodField()

    class Meta:
        model = ServiceCategory
        fields = ("id", "name", "position", "services")

    def get_services(self, category) -> list:
        grouped = self.context.get("services_by_category", {})
        return PublicServiceSerializer(
            grouped.get(category.id, []), many=True, context=self.context
        ).data


class PublicStaffSerializer(serializers.ModelSerializer):
    photo = MediaAssetSerializer(read_only=True)

    class Meta:
        model = StaffMember
        fields = ("id", "name", "specialty", "bio", "photo", "position")


class PublicBusinessHoursSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessHours
        fields = ("weekday", "starts_at", "ends_at")


class PublicTravelZoneSerializer(serializers.ModelSerializer):
    """Zones desservies et leur forfait, telles qu'annoncees a la cliente."""

    class Meta:
        model = TravelZone
        fields = ("id", "name", "fee_amount")


class PublicSalonSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="tenant.name", read_only=True)
    slug = serializers.CharField(source="tenant.slug", read_only=True)
    currency = serializers.CharField(source="tenant.currency", read_only=True)
    timezone = serializers.CharField(source="tenant.timezone", read_only=True)

    logo = MediaAssetSerializer(read_only=True)
    banner = MediaAssetSerializer(read_only=True)
    about_image = MediaAssetSerializer(read_only=True)
    wechat_qr = MediaAssetSerializer(read_only=True)

    categories = serializers.SerializerMethodField()
    staff_members = serializers.SerializerMethodField()
    business_hours = serializers.SerializerMethodField()
    travel_zones = serializers.SerializerMethodField()
    gallery = serializers.SerializerMethodField()
    rating = serializers.SerializerMethodField()

    class Meta:
        model = SalonProfile
        fields = (
            "name",
            "slug",
            "currency",
            "timezone",
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
            "wechat_id",
            "wechat_qr",
            "theme_config",
            "about_title",
            "about_content",
            "about_image",
            "cancellation_policy",
            "cancellation_deadline_hours",
            "late_policy",
            "late_tolerance_minutes",
            "deposit_rate",
            "deposit_minimum",
            "deposit_covers_items",
            "min_lead_time_minutes",
            "max_advance_days",
            "logo",
            "banner",
            "categories",
            "staff_members",
            "business_hours",
            "travel_zones",
            "gallery",
            "rating",
        )

    def get_categories(self, profile) -> list:
        return PublicCategorySerializer(
            self.context.get("categories", []), many=True, context=self.context
        ).data

    def get_staff_members(self, profile) -> list:
        return PublicStaffSerializer(
            self.context.get("staff_members", []), many=True, context=self.context
        ).data

    def get_business_hours(self, profile) -> list:
        return PublicBusinessHoursSerializer(
            self.context.get("business_hours", []), many=True
        ).data

    def get_travel_zones(self, profile) -> list:
        return PublicTravelZoneSerializer(
            self.context.get("travel_zones", []), many=True
        ).data

    def get_gallery(self, profile) -> list:
        return MediaAssetSerializer(
            self.context.get("gallery", []), many=True, context=self.context
        ).data

    def get_rating(self, profile) -> dict:
        """Moyenne et nombre d'avis publies, calcules par la vue.

        Ils voyagent avec le reste du mini-site plutot que dans un second
        appel : afficher « 4,8 sur 12 avis » sous le nom du salon ne vaut pas
        un aller-retour reseau supplementaire sur un forfait mobile.
        """
        return self.context.get("rating", {"average": None, "count": 0})
