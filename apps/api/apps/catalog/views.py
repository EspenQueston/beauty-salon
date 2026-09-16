from apps.accounts.models import Membership
from apps.common.viewsets import TenantModelViewSet

from .models import Resource, Service, ServiceCategory, ServiceOption, ServiceResource
from .serializers import (
    ResourceSerializer,
    ServiceCategorySerializer,
    ServiceOptionSerializer,
    ServiceResourceSerializer,
    ServiceSerializer,
)

# Le catalogue engage les prix du salon : la reception peut le consulter,
# pas le modifier.
MANAGERS = (Membership.Role.OWNER, Membership.Role.MANAGER)
EVERYONE = (*MANAGERS, Membership.Role.RECEPTIONIST, Membership.Role.STAFF)


class ServiceCategoryViewSet(TenantModelViewSet):
    serializer_class = ServiceCategorySerializer
    model = ServiceCategory
    required_roles = MANAGERS
    safe_roles = EVERYONE


class ServiceViewSet(TenantModelViewSet):
    serializer_class = ServiceSerializer
    model = Service
    select_related = ("category",)
    prefetch_related = ("staff_services", "options")
    required_roles = MANAGERS
    safe_roles = EVERYONE

    def get_queryset(self):
        queryset = super().get_queryset()
        active = self.request.query_params.get("active")
        if active in ("true", "false"):
            queryset = queryset.filter(active=active == "true")
        category = self.request.query_params.get("category")
        if category:
            queryset = queryset.filter(category_id=category)
        return queryset


class ServiceOptionViewSet(TenantModelViewSet):
    """Options d'une prestation : « longueur XL », « meches fournies ».

    Elles engagent un tarif *et* une duree annonces publiquement : seuls le
    proprietaire et le gerant les modifient, mais la reception les consulte -
    c'est elle qui repond au telephone quand une cliente demande combien
    coute la longueur supplementaire.
    """

    serializer_class = ServiceOptionSerializer
    model = ServiceOption
    select_related = ("service",)
    required_roles = MANAGERS
    safe_roles = EVERYONE
    pagination_class = None  # la grille d'options d'un salon tient en une reponse

    def get_queryset(self):
        queryset = super().get_queryset()
        if service := self.request.query_params.get("service"):
            queryset = queryset.filter(service_id=service)
        return queryset


class ResourceViewSet(TenantModelViewSet):
    """Fauteuils, bacs, cabines : ce dont le salon n'a qu'un nombre limite."""

    serializer_class = ResourceSerializer
    model = Resource
    required_roles = MANAGERS
    safe_roles = EVERYONE
    pagination_class = None


class ServiceResourceViewSet(TenantModelViewSet):
    """Ce qu'une prestation mobilise."""

    serializer_class = ServiceResourceSerializer
    model = ServiceResource
    select_related = ("service", "resource")
    required_roles = MANAGERS
    safe_roles = EVERYONE
    pagination_class = None

    def get_queryset(self):
        queryset = super().get_queryset()
        if service := self.request.query_params.get("service"):
            queryset = queryset.filter(service_id=service)
        return queryset
