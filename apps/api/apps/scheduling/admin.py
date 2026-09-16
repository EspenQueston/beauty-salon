from django.contrib import admin

from apps.common.admin import TenantScopedAdmin

from .models import AvailabilityException, Booking, BusinessHours


@admin.register(BusinessHours)
class BusinessHoursAdmin(TenantScopedAdmin):
    list_display = ("tenant", "staff_member", "weekday", "starts_at", "ends_at")
    list_filter = ("weekday", "tenant")
    search_fields = ("tenant__name", "staff_member__name")
    autocomplete_fields = ("staff_member",)
    ordering = ("tenant__name", "weekday", "starts_at")
    list_select_related = ("tenant", "staff_member")


@admin.register(AvailabilityException)
class AvailabilityExceptionAdmin(TenantScopedAdmin):
    list_display = ("tenant", "staff_member", "kind", "starts_at", "ends_at", "reason")
    list_filter = ("kind", "tenant")
    search_fields = ("tenant__name", "staff_member__name", "reason")
    autocomplete_fields = ("staff_member",)
    date_hierarchy = "starts_at"
    ordering = ("-starts_at",)
    list_select_related = ("tenant", "staff_member")


@admin.register(Booking)
class BookingAdmin(TenantScopedAdmin):
    """Toutes les commandes des salons, en lecture seule.

    -----------------------------------------------------------------------
    Pourquoi la plateforme regarde sans toucher
    -----------------------------------------------------------------------

    Elle en a besoin pour le support : « ma cliente dit avoir reserve et je
    ne vois rien », « pourquoi ce montant ». Repondre demande de voir.

    Modifier, non. Un rendez-vous appartient au salon : il porte son chiffre
    d'affaires, ses acomptes, ses engagements envers une cliente. Une
    correction faite ici passerait sous ses yeux sans trace dans son agenda,
    et ses comptes ne tomberaient plus juste. Le geste correct est toujours
    de lui dire quoi faire, jamais de le faire a sa place.

    La suppression est fermee pour la meme raison, en plus fort : les lignes
    de recette pointent vers ces rendez-vous.
    """

    list_display = (
        "starts_at",
        "tenant",
        "service_name",
        "customer",
        "staff_member",
        "status",
        "total_amount",
        "money_detail",
        "source",
    )
    list_filter = ("status", "source", "tenant")
    search_fields = (
        "service_name",
        "customer__full_name",
        "customer__phone",
        "staff_member__name",
        "tenant__name",
    )
    autocomplete_fields = ("customer", "staff_member", "service")
    date_hierarchy = "starts_at"
    ordering = ("-starts_at",)
    list_select_related = ("tenant", "customer", "staff_member")

    fieldsets = (
        (None, {"fields": ("tenant", "customer", "staff_member", "service")}),
        ("Creneau", {"fields": ("starts_at", "ends_at")}),
        ("Etat", {"fields": ("status", "source", "cancelled_at", "cancellation_reason")}),
        (
            "Montants",
            {
                "fields": (
                    "service_name",
                    "total_amount",
                    "options_amount",
                    "items_amount",
                    "travel_fee_amount",
                    "deposit_amount",
                    "deposit_received",
                    "deposit_paid",
                    "deposit_method",
                )
            },
        ),
        ("Detail vendu", {"fields": ("options_snapshot", "items_snapshot")}),
        ("Lieu", {"fields": ("location_mode", "address", "travel_zone_name")}),
        ("Notes", {"fields": ("customer_note", "internal_note")}),
        ("Dates", {"fields": ("created_at", "updated_at", "reminder_sent_at")}),
    )

    @admin.display(description="detail")
    def money_detail(self, booking) -> str:
        """Ce qui s'ajoute a la prestation, resume en une colonne.

        Sans elle, un total de 690 pour une prestation a 450 obligeait a
        ouvrir la fiche pour comprendre - c'est la question la plus frequente
        du support.
        """
        parts = []
        if booking.options_amount:
            parts.append(f"options {booking.options_amount}")
        if booking.items_amount:
            parts.append(f"boutique {booking.items_amount}")
        if booking.travel_fee_amount:
            parts.append(f"déplacement {booking.travel_fee_amount}")
        return " · ".join(parts) or "—"

    def get_readonly_fields(self, request, obj=None):
        """Tout, sans exception.

        Calcule depuis les fieldsets plutot qu'ecrit a la main : un champ
        ajoute au modele demain apparaitra ici en lecture seule sans que
        personne n'ait a y penser. Une liste figee finirait par laisser
        passer un champ modifiable.
        """
        fields = []
        for _, options in self.fieldsets:
            fields.extend(options["fields"])
        return tuple(fields)

    def has_add_permission(self, request) -> bool:
        # Une reservation naît du parcours public ou de l'agenda du salon.
        # En creer une ici sauterait la verification de creneau, et poserait
        # un rendez-vous sur un autre.
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        # Les lignes de recette pointent vers ces rendez-vous.
        return False
