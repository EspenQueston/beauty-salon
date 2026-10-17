"""Le catalogue d'un salon, vu depuis le support plateforme.

---------------------------------------------------------------------------
Ce qui vit dans un menu, et ce qui vit dans une fiche
---------------------------------------------------------------------------

Une option (« + shampooing, 2 000 ») et un besoin de ressource (« cette
prestation occupe un bac ») n'existent pas seuls : ils qualifient une
prestation. En entree de menu, ils donnaient deux listes de lignes nues ou
il fallait lire un identifiant pour savoir de quoi on parle.

Ils sont donc poses en `inline` sur la fiche de la prestation, la ou le
salon les a saisis et la ou ils se lisent. Une ressource, elle, garde son
menu : un bac ou un fauteuil existe independamment des prestations qui
l'utilisent.
"""

from django.contrib import admin
from django.utils.safestring import mark_safe

from apps.common.admin import (
    SuppressionTracee,
    TenantScopedAdmin,
    TenantScopedTabularInline,
)

from .models import Resource, Service, ServiceCategory, ServiceOption, ServiceResource


class ServiceOptionInline(TenantScopedTabularInline):
    """Les options d'une prestation, sur sa propre fiche."""

    model = ServiceOption
    extra = 0
    fields = ("name", "description", "price_delta", "duration_delta_minutes", "position")
    ordering = ("position", "name")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class ServiceResourceInline(TenantScopedTabularInline):
    """Ce que la prestation occupe pendant sa duree.

    C'est la cause la plus opaque d'un « il n'y a plus de creneaux » : deux
    prestations qui partagent un bac ne peuvent pas tourner en parallele,
    et rien d'autre ne le dit.
    """

    model = ServiceResource
    extra = 0
    autocomplete_fields = ("resource",)
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("resource")


@admin.register(ServiceCategory)
class ServiceCategoryAdmin(TenantScopedAdmin):
    list_display = ("name", "tenant", "position", "active")
    list_filter = ("active", "tenant")
    search_fields = ("name", "tenant__name")
    ordering = ("tenant__name", "position", "name")


@admin.register(Service)
class ServiceAdmin(SuppressionTracee, TenantScopedAdmin):
    list_display = (
        "name",
        "tenant",
        "category",
        "duration_minutes",
        "price_amount",
        "requires_deposit",
        "active",
    )
    list_filter = ("active", "price_kind", "location_mode", "tenant")
    search_fields = ("name", "description", "tenant__name")
    autocomplete_fields = ("category", "image")
    ordering = ("tenant__name", "position", "name")
    list_select_related = ("tenant", "category")
    inlines = (ServiceOptionInline, ServiceResourceInline)

    fieldsets = (
        (None, {"fields": ("tenant", "category", "name", "description", "image")}),
        ("Tarif", {"fields": ("price_kind", "price_amount", "requires_deposit")}),
        ("Realisation", {"fields": ("duration_minutes", "location_mode")}),
        ("Affichage", {"fields": ("position", "active")}),
    )


@admin.register(Resource)
class ResourceAdmin(SuppressionTracee, TenantScopedAdmin):
    """Bacs, fauteuils, postes : ce qui se partage entre prestations.

    Lecture seule, comme tout ce qui appartient au salon. La capacite est
    le chiffre qu'on vient verifier : elle borne le nombre de rendez-vous
    simultanes, et une capacite a 1 posee par megarde explique a elle seule
    un agenda qui parait complet.
    """

    list_display = ("name", "tenant", "kind", "capacite", "active")
    list_filter = ("kind", "active", "tenant")
    search_fields = ("name", "tenant__name")
    ordering = ("tenant__name", "name")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    # La suppression, elle, est ouverte : seul le lien
    # prestation<->ressource pointe vers une ressource, et il part avec.
    # Aucune ecriture comptable, aucun rendez-vous n'y fait reference.

    @admin.display(description="Capacité", ordering="capacity")
    def capacite(self, resource):
        if resource.capacity <= 1:
            return mark_safe(
                '<span style="color:var(--bs-warn)">1 — une seule cliente à la fois</span>'
            )
        return f"{resource.capacity} en parallèle"
