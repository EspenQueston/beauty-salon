from django.contrib import admin

from apps.common.admin import TenantScopedAdmin

from .models import Service, ServiceCategory


@admin.register(ServiceCategory)
class ServiceCategoryAdmin(TenantScopedAdmin):
    list_display = ("name", "tenant", "position", "active")
    list_filter = ("active", "tenant")
    search_fields = ("name", "tenant__name")
    ordering = ("tenant__name", "position", "name")


@admin.register(Service)
class ServiceAdmin(TenantScopedAdmin):
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

    fieldsets = (
        (None, {"fields": ("tenant", "category", "name", "description", "image")}),
        ("Tarif", {"fields": ("price_kind", "price_amount", "requires_deposit")}),
        ("Realisation", {"fields": ("duration_minutes", "location_mode")}),
        ("Affichage", {"fields": ("position", "active")}),
    )
