"""Moderation des avis, cote plateforme.

C'est le seul endroit ou un avis peut etre masque ou supprime. Le salon, lui,
les consulte sans pouvoir y toucher : un commerce qui retire les avis qui le
derangent ne publie plus que des cinq etoiles, et la note cesse d'informer
qui que ce soit.
"""

from django.contrib import admin
from django.utils.translation import ngettext

from apps.common.admin import TenantScopedAdmin

from .models import Review


@admin.register(Review)
class ReviewAdmin(TenantScopedAdmin):
    list_display = (
        "author_name",
        "rating",
        "tenant",
        "service_label",
        "status",
        "created_at",
    )
    list_filter = ("status", "rating", "tenant")
    search_fields = ("author_name", "comment")
    date_hierarchy = "created_at"
    autocomplete_fields = ("tenant", "booking", "customer")
    readonly_fields = ("created_at", "updated_at")
    actions = ("hide_reviews", "publish_reviews")

    @admin.display(description="Prestation")
    def service_label(self, review):
        return review.booking.service_name

    @admin.action(description="Masquer les avis sélectionnés")
    def hide_reviews(self, request, queryset):
        count = queryset.update(status=Review.Status.HIDDEN)
        self.message_user(
            request,
            ngettext("%d avis masqué.", "%d avis masqués.", count) % count,
        )

    @admin.action(description="Publier les avis sélectionnés")
    def publish_reviews(self, request, queryset):
        count = queryset.update(status=Review.Status.PUBLISHED)
        self.message_user(
            request,
            ngettext("%d avis publié.", "%d avis publiés.", count) % count,
        )
