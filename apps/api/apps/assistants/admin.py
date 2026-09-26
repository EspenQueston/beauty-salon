from django.contrib import admin

from apps.common.admin import TenantScopedAdmin

from .models import AssistantReglages


@admin.register(AssistantReglages)
class AssistantReglagesAdmin(TenantScopedAdmin):
    """L'etat des assistants de chaque salon. Lecture seule, sans secret.

    L'empreinte du jeton WhatsApp n'est pas affichee : elle ne sert qu'a
    verifier les appels d'Evolution.
    """

    list_display = (
        "tenant",
        "clientes_actif",
        "whatsapp_statut",
        "whatsapp_actif",
        "whatsapp_numero",
        "whatsapp_derniere_activite",
    )
    list_filter = ("whatsapp_statut", "clientes_actif", "whatsapp_actif")
    search_fields = ("tenant__name", "tenant__slug", "whatsapp_instance")
    fields = (
        "tenant",
        "clientes_actif",
        "whatsapp_actif",
        "whatsapp_statut",
        "whatsapp_instance",
        "whatsapp_numero",
        "whatsapp_derniere_activite",
    )
    readonly_fields = fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
