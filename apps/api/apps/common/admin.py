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


class SuppressionTracee:
    """Rend la suppression possible, et jamais silencieuse.

    -----------------------------------------------------------------------
    Pourquoi c'etait ferme, et pourquoi ca s'ouvre
    -----------------------------------------------------------------------

    Ces ecrans ont ete ecrits en lecture seule, et c'etait la bonne
    prudence par defaut : ils voient **tous** les salons, et une
    manipulation y porte plus loin qu'ailleurs.

    Mais l'equipe qui exploite la plateforme a de vraies raisons
    d'effacer : une demande de suppression de compte, une donnee de test
    restee en production, une image qu'un salon a televersee par erreur et
    ne sait pas retirer. Sans cette permission, la seule reponse est
    « ouvrez un shell Django sur la production » - infiniment plus
    dangereux que le bouton qu'on refusait.

    -----------------------------------------------------------------------
    Ce qui rend l'ouverture acceptable
    -----------------------------------------------------------------------

    La trace. Chaque suppression ecrit une ligne d'audit : qui, quand, sur
    quel salon, et de quel objet il s'agissait - sa representation texte est
    conservee, puisque l'objet ne sera plus la pour repondre.

    La trace precede la suppression : si elle echoue, rien n'est efface. On
    prefere un refus a un effacement muet.
    """

    def has_delete_permission(self, request, obj=None) -> bool:
        return True

    def get_deleted_objects(self, objs, request):
        """Ce que la confirmation annonce, compte sur le bon alias.

        -------------------------------------------------------------------
        Pourquoi il a fallu la reecrire
        -------------------------------------------------------------------

        Django construit cette liste avec `router.db_for_write()`, c'est-a-
        dire l'alias `default` - celui qui est soumis aux politiques RLS.
        Hors contexte tenant, ces politiques ne laissent passer aucune ligne :
        le collecteur ne voyait donc **rien** de ce qui depend de l'objet.

        Verifie : la page de suppression d'une prestation deja reservee
        annoncait « 1 prestation » et aucun objet protege, alors que sept
        tables pointent vers elle - dont des rendez-vous, en PROTECT. On
        confirmait une suppression en croyant n'effacer qu'une ligne, et
        l'ecriture echouait ensuite sur l'alias privilegie.

        Le collecteur travaille donc ici sur `admin`, le meme alias que la
        lecture et l'ecriture de ces ecrans. La page dit alors la verite.
        """
        from django.contrib.admin.utils import NestedObjects
        from django.utils.text import capfirst

        collecteur = NestedObjects(using=ADMIN_DB)
        collecteur.collect(objs)

        def decrire(obj):
            return f"{capfirst(obj._meta.verbose_name)} : {obj}"

        # Les permissions manquantes sont calculees comme le fait Django :
        # un compte peut avoir le droit d'effacer un salon sans avoir celui
        # d'effacer ses ecritures comptables.
        permissions = set()
        for modele in collecteur.data:
            code = (
                f"{modele._meta.app_label}.delete_{modele._meta.model_name}"
            )
            if not request.user.has_perm(code):
                permissions.add(capfirst(modele._meta.verbose_name))

        comptes = {
            modele._meta.verbose_name_plural: len(objets)
            for modele, objets in collecteur.model_objs.items()
        }
        proteges = [decrire(obj) for obj in collecteur.protected]

        return collecteur.nested(decrire), comptes, permissions, proteges

    def tracer_suppression(self, request, obj) -> None:
        from apps.audit.models import AuditLog

        AuditLog.objects.using(ADMIN_DB).create(
            tenant_id=getattr(obj, "tenant_id", None),
            actor_user=request.user if request.user.is_authenticated else None,
            action=AuditLog.Action.PLATFORM_DELETED,
            resource_type=obj._meta.label_lower,
            resource_id=str(obj.pk),
            # La representation texte est tout ce qui restera : l'objet
            # supprime ne pourra plus dire de qui ni de quoi il s'agissait.
            metadata={"objet": str(obj)[:200]},
        )

    def delete_model(self, request, obj):
        self.tracer_suppression(request, obj)
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            self.tracer_suppression(request, obj)
        super().delete_queryset(request, queryset)


class TenantScopedTabularInline(AdminDatabaseMixin, admin.TabularInline):
    """Inline pour les modeles tenant, sur l'alias privilegie."""

    def get_queryset(self, request):
        return self.model.all_tenants.using(ADMIN_DB)
