"""Administration des salons.

C'est ici que se joue la seule décision réellement manuelle du produit :
publier — ou non — le mini-site d'un salon qui vient de s'inscrire. Tant
qu'un salon est `pending`, sa page publique répond 404 ; l'action de
validation est donc l'interrupteur qui le met en ligne.
"""

from django.contrib import admin, messages
from django.db.models import OuterRef, Subquery
from django.urls import reverse
from django.utils.html import format_html
from django.utils.text import slugify

from apps.audit.models import AuditLog
from apps.common.admin import ADMIN_DB
from apps.common.admin_suppression import ConfirmationSalonForm, SuppressionDefinitiveMixin
from apps.domains.services import ensure_platform_domain

from .models import Tenant


class OffreFilter(admin.SimpleListFilter):
    """L'offre réelle, lue dans l'abonnement : essai, Standard ou Pro."""

    title = "offre"
    parameter_name = "offre"

    def lookups(self, request, model_admin):
        return (
            ("essai", "Essai"),
            ("standard", "Standard"),
            ("pro", "Pro"),
            ("aucune", "Sans abonnement"),
        )

    def queryset(self, request, queryset):
        from apps.billing.models import Subscription

        essai = Subscription.Status.TRIALING
        if self.value() == "essai":
            return queryset.filter(offre_statut=essai)
        if self.value() in ("standard", "pro"):
            return queryset.filter(offre_groupe=self.value()).exclude(offre_statut=essai)
        if self.value() == "aucune":
            return queryset.filter(offre_groupe__isnull=True)
        return queryset


@admin.register(Tenant)
class TenantAdmin(SuppressionDefinitiveMixin, admin.ModelAdmin):
    list_display = (
        "name",
        "slug",
        "status_badge",
        "offre",
        "country",
        "currency",
        "mini_site",
        "inscrit_le",
    )
    list_filter = ("status", OffreFilter, "country")
    readonly_fields = ("offre_actuelle", "lien_suppression")
    suppression_formulaire = ConfirmationSalonForm
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    actions = ("action_publish", "action_suspend", "action_create_platform_domain")

    def get_queryset(self, request):
        """L'offre de chaque salon, lue dans son abonnement.

        Sur l'alias `admin` : la table des abonnements est sous RLS, et hors
        contexte salon la sous-requête ne verrait rien sur `default`.
        """
        from apps.billing.models import Subscription

        abonnement = Subscription.all_tenants.filter(tenant=OuterRef("pk"))
        return (
            super()
            .get_queryset(request)
            .using(ADMIN_DB)
            .annotate(
                offre_groupe=Subquery(abonnement.values("plan__group")[:1]),
                offre_nom=Subquery(abonnement.values("plan__name")[:1]),
                offre_statut=Subquery(abonnement.values("status")[:1]),
                abonnement_id=Subquery(abonnement.values("pk")[:1]),
            )
        )

    @admin.display(description="Offre", ordering="offre_groupe")
    def offre(self, tenant):
        from apps.billing.models import Subscription

        groupe = getattr(tenant, "offre_groupe", None)
        if groupe is None:
            return "—"
        if getattr(tenant, "offre_statut", "") == Subscription.Status.TRIALING:
            return format_html('<span class="pill">Essai</span>')
        if groupe == "pro":
            return format_html('<span class="pill pill--ok">Pro · {}</span>', tenant.offre_nom)
        return format_html('<span class="pill">Standard · {}</span>', tenant.offre_nom)

    @admin.display(description="Offre")
    def offre_actuelle(self, tenant):
        """Ce que le salon a vraiment, et où le changer."""
        if tenant.pk is None or getattr(tenant, "abonnement_id", None) is None:
            return "Aucun abonnement : il est créé avec l'essai, à l'enregistrement."
        liste = reverse("admin:billing_subscription_changelist")
        return format_html(
            '{} &nbsp; <a href="{}?q={}">Changer l’offre →</a><br>'
            '<span class="help">Cochez l’abonnement, puis l’action « Changer l’offre '
            "(Standard / Pro) ». Les droits suivent l'abonnement, jamais cette fiche.</span>",
            self.offre(tenant),
            liste,
            tenant.slug,
        )

    # --- Suppression definitive (apps/common/suppression.py) ---------------

    def suppression_identifiant(self, tenant) -> str:
        return tenant.slug

    def suppression_contexte(self, request, tenant) -> dict:
        from apps.common.suppression import inventaire_salon

        obstacles = []
        if tenant.status == Tenant.Status.ACTIVE:
            obstacles.append(
                "Ce salon est en ligne. Suspendez-le d'abord (action « Suspendre ») : "
                "sa page disparaît, et vous gardez le temps de revenir en arrière."
            )
        inv = inventaire_salon(tenant)
        return {
            "obstacles": obstacles,
            "donnees": inv.comptes,
            "fichiers": inv.fichiers,
            "domaines": inv.domaines,
            "comptes_equipe": inv.comptes_equipe,
            "comptes_clientes": inv.comptes_clientes,
            "conserve": [
                "Le journal d'audit, dont une ligne décrit cette suppression.",
                "Le grand livre de la plateforme : les montants encaissés restent, "
                "sans lien vers le salon.",
            ],
        }

    def suppression_executer(self, request, tenant, donnees) -> str:
        from apps.common.suppression import supprimer_salon

        bilan = supprimer_salon(
            tenant,
            administrateur=request.user,
            motif=donnees["motif"],
            avec_comptes=donnees.get("avec_comptes", False),
        )
        return (
            f"Salon « {tenant.name} » supprimé définitivement "
            f"({sum(bilan['donnees'].values())} lignes, {bilan['fichiers']} fichiers, "
            f"{bilan['comptes']} compte(s))."
        )

    @admin.display(description="Statut", ordering="status")
    def status_badge(self, tenant):
        tone = {
            Tenant.Status.ACTIVE: "",
            Tenant.Status.PENDING: " pill--warning",
            Tenant.Status.SUSPENDED: " pill--danger",
        }[tenant.status]
        return format_html(
            '<span class="pill{}">{}</span>', tone, tenant.get_status_display()
        )

    @admin.display(description="Inscrit le", ordering="created_at")
    def inscrit_le(self, tenant):
        return tenant.created_at

    @admin.display(description="Mini-site")
    def mini_site(self, tenant):
        domain = tenant.domains.filter(is_primary=True).first()
        if domain is None:
            return "—"
        if tenant.status != Tenant.Status.ACTIVE:
            return format_html("<span class=\"pill\">{}</span>", domain.hostname)
        return format_html(
            '<a href="http://{}" target="_blank" rel="noreferrer">{}</a>',
            domain.hostname,
            domain.hostname,
        )

    def save_model(self, request, obj, form, change):
        if not obj.slug:
            obj.slug = slugify(obj.name)
        super().save_model(request, obj, form, change)
        # Un salon sans sous-domaine n'est joignable par personne : on le
        # crée dès la première sauvegarde.
        if not change:
            ensure_platform_domain(obj)
            # Et son essai, comme a l'inscription : un salon cree ici sans
            # abonnement echapperait aux regles d'acces.
            from apps.billing.services import BillingError, start_trial

            try:
                start_trial(obj)
            except BillingError:
                self.message_user(
                    request,
                    "Aucune offre d'essai n'est configurée : lancez bootstrap_platform.",
                    messages.WARNING,
                )

    @admin.action(description="Valider et publier le mini-site")
    def action_publish(self, request, queryset):
        """Fait passer un salon de « en préparation » à « actif ».

        C'est l'étape que le parcours d'inscription laisse volontairement en
        attente : sans elle, n'importe qui publierait une page sous le
        domaine de la plateforme en s'inscrivant.
        """
        published = []
        skipped = []

        for tenant in queryset:
            if tenant.status == Tenant.Status.ACTIVE:
                skipped.append(tenant.name)
                continue

            tenant.status = Tenant.Status.ACTIVE
            tenant.save(using=ADMIN_DB, update_fields=["status", "updated_at"])
            # Le sous-domaine peut manquer sur un salon créé à la main.
            ensure_platform_domain(tenant)
            published.append(tenant.name)

            AuditLog.objects.using(ADMIN_DB).create(
                tenant=tenant,
                actor_user=request.user,
                action=AuditLog.Action.TENANT_STATUS_CHANGED,
                resource_type="tenant",
                resource_id=str(tenant.id),
                metadata={"status": Tenant.Status.ACTIVE, "via": "admin"},
            )

        if published:
            self.message_user(
                request,
                f"Mini-site en ligne pour : {', '.join(published)}.",
                messages.SUCCESS,
            )
        if skipped:
            self.message_user(
                request, f"Déjà actifs : {', '.join(skipped)}.", messages.INFO
            )

    @admin.action(description="Suspendre (met le mini-site hors ligne)")
    def action_suspend(self, request, queryset):
        suspended = []
        for tenant in queryset:
            if tenant.status == Tenant.Status.SUSPENDED:
                continue
            tenant.status = Tenant.Status.SUSPENDED
            tenant.save(using=ADMIN_DB, update_fields=["status", "updated_at"])
            suspended.append(tenant.name)

            AuditLog.objects.using(ADMIN_DB).create(
                tenant=tenant,
                actor_user=request.user,
                action=AuditLog.Action.TENANT_STATUS_CHANGED,
                resource_type="tenant",
                resource_id=str(tenant.id),
                metadata={"status": Tenant.Status.SUSPENDED, "via": "admin"},
            )

        if suspended:
            self.message_user(
                request,
                f"Suspendus : {', '.join(suspended)}. Leurs rendez-vous sont conservés.",
                messages.WARNING,
            )
        else:
            self.message_user(
                request, "Aucun salon à suspendre dans la sélection.", messages.INFO
            )

    @admin.action(description="Créer le sous-domaine plateforme manquant")
    def action_create_platform_domain(self, request, queryset):
        hostnames = [ensure_platform_domain(tenant).hostname for tenant in queryset]
        self.message_user(
            request, "Sous-domaines en place : " + ", ".join(hostnames), messages.INFO
        )
