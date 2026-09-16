"""Boutique : articles, fournitures a prevoir, et ce qu'on en propose."""

from rest_framework import serializers

from apps.accounts.models import Membership
from apps.common.viewsets import TenantModelViewSet

from .models import Product, Requirement, RequirementProduct

MANAGERS = (Membership.Role.OWNER, Membership.Role.MANAGER)
# La reception vend au comptoir : elle doit voir le stock et les prix.
EVERYONE = (*MANAGERS, Membership.Role.RECEPTIONIST, Membership.Role.STAFF)


class ProductSerializer(serializers.ModelSerializer):
    unit_label = serializers.CharField(source="get_unit_display", read_only=True)
    image_url = serializers.SerializerMethodField()
    # Photo ou video : le navigateur ne peut pas le deviner depuis l'URL,
    # et rendre un MP4 dans une balise <img> ne donne rien du tout.
    image_type = serializers.SerializerMethodField()
    in_stock = serializers.BooleanField(read_only=True)
    is_low = serializers.BooleanField(read_only=True)

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "description",
            "price",
            "unit",
            "unit_label",
            "stock",
            "low_stock_at",
            "image",
            "image_url",
            "image_type",
            "active",
            "position",
            "in_stock",
            "is_low",
        )

    def get_image_url(self, product) -> str:
        if not product.image_id or not product.image:
            return ""
        request = self.context.get("request")
        url = product.image.file.url
        return request.build_absolute_uri(url) if request else url

    def get_image_type(self, product) -> str:
        return product.image.content_type if product.image_id and product.image else ""

    def validate_name(self, value):
        """Un nom deja pris se refuse ici, pas dans PostgreSQL.

        La contrainte `unique_product_name_per_tenant` porte sur (tenant,
        name). DRF ne sait pas en deduire de validateur : `tenant` n'est pas
        un champ du serializer, il vient du contexte de la requete. Sans ce
        controle, renommer un article en un nom deja utilise remontait une
        IntegrityError - une erreur 500 la ou l'utilisatrice attend « ce nom
        est deja pris ».

        `Product.objects` est filtre sur le salon courant : la comparaison ne
        peut pas voir l'article d'un voisin, et un salon reste libre de
        vendre des « Meches kanekalon » meme si celui d'a cote en vend aussi.
        """
        name = value.strip()
        taken = Product.objects.filter(name=name)
        if self.instance is not None:
            taken = taken.exclude(pk=self.instance.pk)
        if taken.exists():
            raise serializers.ValidationError(
                "Un article de votre boutique porte déjà ce nom."
            )
        return name


class RequirementSerializer(serializers.ModelSerializer):
    service_name = serializers.CharField(source="service.name", read_only=True)
    product_ids = serializers.SerializerMethodField()

    class Meta:
        model = Requirement
        fields = (
            "id",
            "service",
            "service_name",
            "label",
            "detail",
            "mandatory",
            "position",
            "product_ids",
        )

    def get_product_ids(self, requirement) -> list[str]:
        return [str(offer.product_id) for offer in requirement.offers.all()]

    def validate_label(self, value):
        return value.strip()


class RequirementProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = RequirementProduct
        fields = ("id", "requirement", "product")


class ProductViewSet(TenantModelViewSet):
    """Le catalogue de vente du salon."""

    serializer_class = ProductSerializer
    model = Product
    select_related = ("image",)
    required_roles = MANAGERS
    safe_roles = EVERYONE
    pagination_class = None  # la boutique d'un salon tient en une reponse

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.request.query_params.get("available") == "true":
            queryset = queryset.filter(active=True)
        return queryset


class RequirementViewSet(TenantModelViewSet):
    """Ce qu'il faut prevoir, prestation par prestation."""

    serializer_class = RequirementSerializer
    model = Requirement
    select_related = ("service",)
    prefetch_related = ("offers",)
    required_roles = MANAGERS
    safe_roles = EVERYONE
    pagination_class = None

    def get_queryset(self):
        queryset = super().get_queryset()
        if service := self.request.query_params.get("service"):
            queryset = queryset.filter(service_id=service)
        return queryset


class RequirementProductViewSet(TenantModelViewSet):
    """Rattachement d'un article a une fourniture a prevoir."""

    serializer_class = RequirementProductSerializer
    model = RequirementProduct
    select_related = ("requirement", "product")
    required_roles = MANAGERS
    safe_roles = EVERYONE
    pagination_class = None

    def get_queryset(self):
        queryset = super().get_queryset()
        if requirement := self.request.query_params.get("requirement"):
            queryset = queryset.filter(requirement_id=requirement)
        return queryset
