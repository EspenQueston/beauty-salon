from django.contrib import admin

from apps.common.admin import TenantScopedAdmin

from .models import SalonProfile, TravelZone


@admin.register(SalonProfile)
class SalonProfileAdmin(TenantScopedAdmin):
    list_display = ("tenant", "city", "service_mode", "phone", "whatsapp_number")
    list_filter = ("service_mode", "tenant")
    search_fields = ("tenant__name", "city", "address")
    autocomplete_fields = ("logo", "banner")

    fieldsets = (
        (None, {"fields": ("tenant", "description", "logo", "banner")}),
        ("Coordonnees", {"fields": ("address", "city", "phone", "whatsapp_number",
                                    "social_links")}),
        ("Apparence", {"fields": ("theme_config",)}),
        (
            "Reservation",
            {
                "fields": (
                    "service_mode",
                    "slot_granularity_minutes",
                    "buffer_minutes",
                    "min_lead_time_minutes",
                    "max_advance_days",
                )
            },
        ),
        (
            "Annulation",
            {"fields": ("cancellation_policy", "cancellation_deadline_hours")},
        ),
        (
            "Retard",
            {"fields": ("late_tolerance_minutes", "late_policy")},
        ),
        (
            "Déplacement",
            {"fields": ("service_area", "latitude", "longitude")},
        ),
    )


@admin.register(TravelZone)
class TravelZoneAdmin(TenantScopedAdmin):
    list_display = ("name", "fee_amount", "active", "position", "tenant")
    list_filter = ("active", "tenant")
    search_fields = ("name", "tenant__name")
    ordering = ("tenant", "position", "name")
