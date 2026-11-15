from django.contrib import admin

from apps.common.admin import TenantScopedAdmin

from .models import AssistantReglages, ConversationAssistant


@admin.register(AssistantReglages)
class AssistantReglagesAdmin(TenantScopedAdmin):
    """L'etat des assistants de chaque salon. Lecture seule, sans secret.

    Les empreintes des jetons (WhatsApp, n8n) ne sont pas affichees : elles
    ne servent qu'a verifier les appels entrants.
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
        "n8n_numero",
        "n8n_derniere_reception",
    )
    readonly_fields = fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ConversationAssistant)
class ConversationAssistantAdmin(TenantScopedAdmin):
    """Les fils de l'assistant : qui, quand, combien — jamais ce qui s'est dit.

    Le contenu des messages appartient au salon et a sa cliente. La
    plateforme supervise l'activite (un fil qui s'emballe, un salon dont
    l'assistant ne repond plus) sans lire les conversations : ni apercu ni
    messages ici.
    """

    list_display = ("tenant", "canal", "contact", "nom", "nombre_messages", "dernier_message_le")
    list_filter = ("canal",)
    search_fields = ("tenant__name", "tenant__slug", "contact")
    fields = ("tenant", "canal", "contact", "nom", "nombre_messages", "dernier_message_le")
    readonly_fields = fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
