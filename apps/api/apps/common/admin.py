"""Base d'administration plateforme.

L'admin Django est l'outil de l'equipe SaaS, pas des salons : il doit voir
tous les tenants. Il travaille donc sur l'alias `admin` (role BYPASSRLS) et
sur le manager `all_tenants`. C'est le seul endroit de l'application ou le
contournement de l'isolation est intentionnel et assume.
"""

from django.contrib import admin

ADMIN_DB = "admin"


class PlatformAdminSite(admin.AdminSite):
    site_header = "Beauty Salon - Administration plateforme"
    site_title = "Beauty Salon"
    index_title = "Supervision"


class AdminDatabaseMixin:
    """Force toutes les listes deroulantes sur l'alias `admin`.

    Deux reglages sont necessaires, et oublier le second donne un bug
    silencieux :

    - `queryset` : sans lui, le manager par defaut d'un modele tenant renvoie
      `.none()` hors contexte et le menu est vide ;
    - `using` : les widgets d'autocompletion rechargent l'option deja
      selectionnee avec `queryset.using(self.db)`, ou `self.db` vient du
      routeur - donc `default`, ou les politiques RLS masquent la ligne. Le
      champ s'affiche alors vide, et l'enregistrement efface la relation.
    """

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        kwargs.setdefault("using", ADMIN_DB)

        related = db_field.remote_field.model
        manager = getattr(related, "all_tenants", related._default_manager)
        kwargs.setdefault("queryset", manager.using(ADMIN_DB))

        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class TenantScopedAdmin(AdminDatabaseMixin, admin.ModelAdmin):
    """ModelAdmin pour les modeles heritant de TenantOwnedModel."""

    list_select_related = ("tenant",)

    def get_queryset(self, request):
        return self.model.all_tenants.using(ADMIN_DB).select_related("tenant")

    def save_model(self, request, obj, form, change):
        obj.save(using=ADMIN_DB)

    def delete_model(self, request, obj):
        obj.delete(using=ADMIN_DB)

    def delete_queryset(self, request, queryset):
        queryset.using(ADMIN_DB).delete()


class TenantScopedTabularInline(AdminDatabaseMixin, admin.TabularInline):
    """Inline pour les modeles tenant, sur l'alias privilegie."""

    def get_queryset(self, request):
        return self.model.all_tenants.using(ADMIN_DB)
