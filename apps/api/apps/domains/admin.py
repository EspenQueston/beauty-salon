from django.contrib import admin

from .models import Domain


@admin.register(Domain)
class DomainAdmin(admin.ModelAdmin):
    list_display = ("hostname", "tenant", "kind", "is_primary", "active", "verified_at")
    list_filter = ("kind", "active", "is_primary")
    search_fields = ("hostname", "tenant__name", "tenant__slug")
    autocomplete_fields = ("tenant",)
