from django.contrib import admin

from apps.common.admin import TenantScopedAdmin

from .models import Domain, DomainClaim


@admin.register(Domain)
class DomainAdmin(admin.ModelAdmin):
    list_display = ("hostname", "tenant", "kind", "is_primary", "active", "verified_at")
    list_filter = ("kind", "active", "is_primary")
    search_fields = ("hostname", "tenant__name", "tenant__slug")
    autocomplete_fields = ("tenant",)


@admin.register(DomainClaim)
class DomainClaimAdmin(TenantScopedAdmin):
    """Les demandes de domaine personnalise, et ou elles en sont.

    En lecture seule : la preuve (TXT) et la connexion se font par le salon
    depuis son tableau de bord. Un domaine relie se retire ici en supprimant
    sa ligne dans « Domaines ».
    """

    list_display = ("hostname", "tenant", "status", "last_checked_at", "last_error", "created_at")
    list_filter = ("status",)
    search_fields = ("hostname", "tenant__name", "tenant__slug")
    readonly_fields = (
        "tenant",
        "hostname",
        "token",
        "status",
        "last_checked_at",
        "last_error",
        "requested_by",
        "created_at",
    )
    exclude = ("updated_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
