from django.contrib import admin

from apps.common.admin import TenantScopedAdmin

from .models import Customer


@admin.register(Customer)
class CustomerAdmin(TenantScopedAdmin):
    list_display = ("full_name", "tenant", "phone", "email", "marketing_consent")
    list_filter = ("marketing_consent", "contact_preference", "tenant")
    search_fields = ("full_name", "phone", "email", "tenant__name")
    ordering = ("tenant__name", "full_name")
    readonly_fields = ("marketing_consent_at",)

    fieldsets = (
        (None, {"fields": ("tenant", "full_name", "phone", "email")}),
        (
            "Communication",
            {"fields": ("contact_preference", "marketing_consent", "marketing_consent_at")},
        ),
        # Donnees sensibles : allergies, sensibilite du cuir chevelu. Isolees
        # dans leur propre section pour qu'on sache ce qu'on ouvre.
        ("Notes internes", {"fields": ("private_notes",), "classes": ("collapse",)}),
    )
