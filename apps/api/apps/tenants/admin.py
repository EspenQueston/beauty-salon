"""Administration des salons.

C'est ici que se joue la seule décision réellement manuelle du produit :
publier — ou non — le mini-site d'un salon qui vient de s'inscrire. Tant
qu'un salon est `pending`, sa page publique répond 404 ; l'action de
validation est donc l'interrupteur qui le met en ligne.
"""

from django.contrib import admin, messages
from django.utils.html import format_html
from django.utils.text import slugify

from apps.audit.models import AuditLog
from apps.common.admin import ADMIN_DB
from apps.domains.services import ensure_platform_domain

from .models import Tenant


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "slug",
        "status_badge",
        "plan",
        "country",
        "currency",
        "mini_site",
        "inscrit_le",
    )
    list_filter = ("status", "plan", "country")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    actions = ("action_publish", "action_suspend", "action_create_platform_domain")

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
