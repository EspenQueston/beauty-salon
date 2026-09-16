from django.contrib import admin

from apps.common.admin import ADMIN_DB

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Journal en lecture seule.

    Un audit que l'on peut modifier depuis l'interface ne prouve plus rien :
    aucun ajout, aucune edition, aucune suppression.
    """

    list_display = ("created_at", "action", "tenant", "actor_user", "resource_type")
    list_filter = ("action", "tenant")
    search_fields = ("resource_id", "actor_user__email", "tenant__name")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    list_select_related = ("tenant", "actor_user")

    def get_queryset(self, request):
        return AuditLog.objects.using(ADMIN_DB).select_related("tenant", "actor_user")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
