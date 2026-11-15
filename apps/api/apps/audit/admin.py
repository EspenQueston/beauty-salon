from django.contrib import admin
from django.utils.html import format_html

from apps.common.admin import ADMIN_DB

from .models import AuditLog


class CategorieFilter(admin.SimpleListFilter):
    """Le journal de securite des comptes, d'un clic, parmi tous les evenements."""

    title = "catégorie"
    parameter_name = "categorie"

    CATEGORIES = {
        "securite": ("Sécurité des comptes", "auth."),
        "abonnements": ("Abonnements", "subscription."),
        "parrainage": ("Parrainage", "referral."),
        "reservations": ("Réservations", "booking."),
    }

    def lookups(self, request, model_admin):
        return [(cle, libelle) for cle, (libelle, _) in self.CATEGORIES.items()]

    def queryset(self, request, queryset):
        choix = self.CATEGORIES.get(self.value())
        if choix is None:
            return queryset
        return queryset.filter(action__startswith=choix[1])


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Journal en lecture seule.

    Un audit que l'on peut modifier depuis l'interface ne prouve plus rien :
    aucun ajout, aucune edition, aucune suppression.
    """

    list_display = ("created_at", "action", "qui", "origine", "tenant", "resource_type")
    list_filter = (CategorieFilter, "action", "tenant")
    search_fields = (
        "resource_id",
        "actor_user__email",
        "tenant__name",
        "metadata__email",
        "metadata__ip",
    )
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    list_select_related = ("tenant", "actor_user")

    def get_queryset(self, request):
        return AuditLog.objects.using(ADMIN_DB).select_related("tenant", "actor_user")

    @admin.display(description="Compte")
    def qui(self, entree):
        # L'adresse saisie compte aussi quand aucun compte ne lui correspond :
        # c'est ainsi qu'on repere un essai sur une adresse inexistante.
        return entree.actor_user or (entree.metadata or {}).get("email") or "—"

    @admin.display(description="Origine")
    def origine(self, entree):
        meta = entree.metadata or {}
        if not meta.get("ip"):
            return "—"
        return format_html('<span title="{}">{}</span>', meta.get("navigateur", ""), meta.get("ip"))

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
