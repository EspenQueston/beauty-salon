from django.contrib import admin

from apps.common.admin import ADMIN_DB, TenantScopedAdmin

from .models import MediaAsset


@admin.register(MediaAsset)
class MediaAssetAdmin(TenantScopedAdmin):
    list_display = ("__str__", "tenant", "kind", "visibility", "width", "height")
    list_filter = ("kind", "visibility", "tenant")
    search_fields = ("alt_text", "tenant__name")
    ordering = ("tenant__name", "position")
    readonly_fields = ("content_type", "byte_size", "width", "height", "derivatives")

    def save_model(self, request, obj, form, change):
        uploaded = form.cleaned_data.get("file")
        if uploaded is not None and hasattr(uploaded, "content_type"):
            obj.content_type = (uploaded.content_type or "").lower()
            obj.byte_size = uploaded.size

        super().save_model(request, obj, form, change)

        # Dimensions et derives WebP : meme traitement que par l'API, pour que
        # la galerie reste homogene quelle que soit la porte d'entree.
        from .tasks import process_media_asset

        process_media_asset.delay(str(obj.id), str(obj.tenant_id))

    def get_queryset(self, request):
        return MediaAsset.all_tenants.using(ADMIN_DB).select_related("tenant")
