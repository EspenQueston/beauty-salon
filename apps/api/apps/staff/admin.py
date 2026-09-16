from django.contrib import admin

from apps.common.admin import ADMIN_DB, TenantScopedAdmin, TenantScopedTabularInline

from .models import StaffMember, StaffService


class StaffServiceInline(TenantScopedTabularInline):
    """Competences du prestataire, gerees depuis sa fiche.

    C'est la que le salon raisonne (« Fatou fait les tresses »), et cela
    evite d'exposer une table de liaison nue dans le menu.
    """

    model = StaffService
    extra = 1
    autocomplete_fields = ("service",)
    exclude = ("tenant",)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("service", "staff_member")


@admin.register(StaffMember)
class StaffMemberAdmin(TenantScopedAdmin):
    list_display = ("name", "tenant", "specialty", "active")
    list_filter = ("active", "tenant")
    search_fields = ("name", "specialty", "tenant__name")
    autocomplete_fields = ("photo",)
    ordering = ("tenant__name", "position", "name")
    inlines = (StaffServiceInline,)

    def save_formset(self, request, form, formset, change):
        # Le tenant vient du prestataire, jamais du formulaire : une
        # competence ne peut pas atterrir dans un autre salon.
        instances = formset.save(commit=False)
        for instance in instances:
            if isinstance(instance, StaffService):
                instance.tenant_id = form.instance.tenant_id
            instance.save(using=ADMIN_DB)
        for obj in formset.deleted_objects:
            obj.delete(using=ADMIN_DB)
        formset.save_m2m()
