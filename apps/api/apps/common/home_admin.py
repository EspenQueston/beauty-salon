from django.contrib import admin

from .models import HomeMetric, HomeReference, HomeSettings


@admin.register(HomeReference)
class HomeReferenceAdmin(admin.ModelAdmin):
    list_display = ("tenant", "author", "active", "consent", "verified", "showcase")
    list_filter = ("active", "consent", "verified")
    search_fields = ("tenant__name", "author")
    autocomplete_fields = ("tenant",)


@admin.register(HomeSettings)
class HomeSettingsAdmin(admin.ModelAdmin):
    list_display = ("support_email", "support_whatsapp")

    def has_add_permission(self, request):
        return super().has_add_permission(request) and not HomeSettings.objects.exists()


@admin.register(HomeMetric)
class HomeMetricAdmin(admin.ModelAdmin):
    list_display = ("day", "stage", "language", "count")
    list_filter = ("event", "language", "day")
    readonly_fields = ("day", "event", "language", "count")
    date_hierarchy = "day"

    @admin.display(description="étape")
    def stage(self, obj):
        return {
            "home_view": "Visite de la page d’accueil",
            "create_click": "Clic vers la création",
            "preview_used": "Personnalisation de l’aperçu",
            "demo_completed": "Démonstration terminée",
            "pricing_view": "Tarifs consultés",
            "signup_started": "Formulaire d’inscription ouvert",
            "signup_completed": "Salon créé (serveur)",
            "email_verified": "E-mail du propriétaire confirmé (serveur)",
            "salon_published": "Salon publié (serveur)",
            "first_booking": "Premier rendez-vous (serveur)",
        }.get(obj.event, obj.event)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
