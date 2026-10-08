"""Le parrainage dans l'administration plateforme.

Lecture libre pour l'equipe ; les corrections — valider, invalider, annuler
une remise — passent par une page qui exige un motif, et chacune laisse une
trace dans le journal d'audit. Aucune ligne ne s'edite a la main : un
pourcentage ou un statut change sans auteur ni motif ne prouverait plus rien.
"""

from __future__ import annotations

from django import forms
from django.contrib import admin, messages
from django.contrib.admin import helpers
from django.template.response import TemplateResponse
from django.utils.html import format_html

from apps.common.admin import ADMIN_DB, TenantScopedAdmin

from . import services
from .models import (
    CodeClientSalon,
    CodeParrainage,
    EvenementParrainage,
    Parrainage,
    PolitiquePlateforme,
    PolitiqueSalon,
    RecompenseClient,
    Remise,
)

PERM_CORRIGER = "parrainage.corriger_parrainage"

TONS = {
    Parrainage.Statut.EN_VERIFICATION: "warning",
    Parrainage.Statut.ADMISSIBLE: "ok",
    Parrainage.Statut.REFUSE: "danger",
    Parrainage.Statut.INVALIDE: "danger",
    Remise.Statut.DISPONIBLE: "ok",
    Remise.Statut.EN_ATTENTE: "warning",
    Remise.Statut.SUSPENDUE: "warning",
    Remise.Statut.RESERVEE: "warning",
    Remise.Statut.UTILISEE: "",
    Remise.Statut.EXPIREE: "",
    Remise.Statut.ANNULEE: "danger",
}


def _pastille(texte: str, ton: str = "") -> str:
    classe = f"pill pill--{ton}" if ton else "pill"
    return format_html('<span class="{}">{}</span>', classe, texte)


class MotifForm(forms.Form):
    motif = forms.CharField(
        label="Motif",
        min_length=10,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Obligatoire (10 caractères au moins). Enregistré dans le journal d'audit.",
    )


class _LectureSeule(admin.ModelAdmin):
    """Ni ajout, ni edition, ni suppression depuis ces listes.

    Les fiches s'ouvrent en lecture (permission de vue) ; les corrections
    passent par les actions, qui exigent un motif.
    """

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return self.readonly_fields or tuple(
            f.name for f in self.model._meta.fields if f.name not in (self.exclude or ())
        )

    def _geste(self, request, queryset, *, titre, aide, action, executer, libelle):
        if not request.user.has_perm(PERM_CORRIGER):
            self.message_user(
                request, "Vous n'avez pas le droit de corriger un parrainage.", messages.ERROR
            )
            return None
        form = MotifForm(request.POST if "confirmer" in request.POST else None)
        if "confirmer" in request.POST and form.is_valid():
            reussis, echecs = 0, []
            for objet in queryset:
                try:
                    executer(objet, form.cleaned_data["motif"])
                    reussis += 1
                except ValueError as refus:
                    echecs.append(f"{libelle(objet)} : {refus}")
            if reussis:
                self.message_user(request, f"{titre} : {reussis} élément(s).", messages.SUCCESS)
            for echec in echecs:
                self.message_user(request, echec, messages.WARNING)
            return None
        objets = [{"pk": o.pk, "libelle": libelle(o)} for o in queryset]
        return TemplateResponse(
            request,
            "admin/parrainage/geste.html",
            {
                **self.admin_site.each_context(request),
                "title": titre,
                "aide": aide,
                "form": form,
                "objets": objets,
                "action": action,
                "opts": self.model._meta,
                "action_checkbox_name": helpers.ACTION_CHECKBOX_NAME,
            },
        )


@admin.register(CodeParrainage)
class CodeParrainageAdmin(_LectureSeule):
    list_display = ("code", "titulaire", "type", "actif", "cree_le")
    list_filter = ("actif",)
    search_fields = ("code", "tenant__name", "tenant__slug", "user__email")
    ordering = ("-cree_le",)
    actions = ("action_desactiver", "action_reactiver")

    def get_queryset(self, request):
        return CodeParrainage.objects.using(ADMIN_DB).select_related("tenant", "user")

    @admin.display(description="Titulaire")
    def titulaire(self, code):
        return code.tenant or code.user

    @admin.display(description="Type")
    def type(self, code):
        return Parrainage.TypeParrain(code.type_parrain).label

    def _basculer(self, request, queryset, actif: bool, titre: str, action: str):
        def executer(code, motif):
            CodeParrainage.objects.filter(pk=code.pk).update(actif=actif)
            from apps.audit.models import AuditLog

            AuditLog.objects.create(
                tenant_id=code.tenant_id,
                actor_user=request.user,
                action=AuditLog.Action.REFERRAL_ADMIN,
                resource_type="code_parrainage",
                resource_id=str(code.pk),
                metadata={"geste": "activation" if actif else "desactivation", "motif": motif},
            )

        return self._geste(
            request,
            queryset,
            titre=titre,
            aide=(
                "Un code désactivé n'est plus accepté à l'inscription. Les parrainages "
                "déjà enregistrés ne changent pas."
            ),
            action=action,
            executer=executer,
            libelle=lambda c: f"{c.code} — {c.tenant or c.user}",
        )

    @admin.action(description="Désactiver le code…")
    def action_desactiver(self, request, queryset):
        return self._basculer(request, queryset, False, "Désactiver le code", "action_desactiver")

    @admin.action(description="Réactiver le code…")
    def action_reactiver(self, request, queryset):
        return self._basculer(request, queryset, True, "Réactiver le code", "action_reactiver")


class RemiseInline(admin.TabularInline):
    model = Remise
    extra = 0
    can_delete = False
    fields = ("declencheur", "pourcentage", "statut", "expire_le", "montant_deduit", "devise")
    readonly_fields = fields
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        return Remise.objects.using(ADMIN_DB)


@admin.register(Parrainage)
class ParrainageAdmin(_LectureSeule):
    list_display = (
        "filleul",
        "parrain",
        "type_parrain",
        "statut_",
        "revue_requise",
        "publie_le",
        "admissible_le",
        "cree_le",
    )
    list_filter = ("statut", "type_parrain", "revue_requise")
    search_fields = (
        "filleul__name",
        "filleul__slug",
        "parrain_tenant__name",
        "parrain_user__email",
        "code__code",
    )
    ordering = ("-cree_le",)
    date_hierarchy = "cree_le"
    inlines = (RemiseInline,)
    readonly_fields = (
        "filleul",
        "code",
        "type_parrain",
        "parrain_tenant",
        "parrain_user",
        "statut",
        "motif",
        "revue_requise",
        "publie_le",
        "admissible_le",
        "essai_debut",
        "essai_fin",
        "cree_le",
    )
    exclude = ("empreinte_ip",)
    actions = ("action_invalider",)

    def get_queryset(self, request):
        return Parrainage.objects.using(ADMIN_DB).select_related(
            "filleul", "parrain_tenant", "parrain_user", "code"
        )

    @admin.display(description="Parrain")
    def parrain(self, parrainage):
        return parrainage.parrain_tenant or parrainage.parrain_user or "— (supprimé)"

    @admin.display(description="Statut", ordering="statut")
    def statut_(self, parrainage):
        return _pastille(parrainage.get_statut_display(), TONS.get(parrainage.statut, ""))

    @admin.action(description="Invalider (fraude, erreur)…")
    def action_invalider(self, request, queryset):
        return self._geste(
            request,
            queryset,
            titre="Invalider le parrainage",
            aide=(
                "Le parrainage est invalidé et ses remises encore disponibles sont "
                "annulées. Une remise déjà utilisée reste acquise ; une remise réservée "
                "par un paiement en attente se tranche en refusant ce paiement."
            ),
            action="action_invalider",
            executer=lambda p, motif: services.invalider(p, request.user, motif),
            libelle=lambda p: f"{p.filleul} ← {self.parrain(p)}",
        )


@admin.register(Remise)
class RemiseAdmin(_LectureSeule):
    list_display = (
        "beneficiaire",
        "filleul_nom",
        "declencheur",
        "pourcentage",
        "statut_",
        "expire_le",
        "montant_deduit",
        "devise",
        "cree_le",
    )
    list_filter = ("statut", "declencheur")
    search_fields = (
        "beneficiaire_tenant__name",
        "beneficiaire_user__email",
        "filleul_nom",
        "reference",
    )
    ordering = ("-cree_le",)
    readonly_fields = (
        "parrainage",
        "filleul_nom",
        "beneficiaire_tenant",
        "beneficiaire_user",
        "declencheur",
        "reference",
        "pourcentage",
        "statut",
        "expire_le",
        "paiement_declencheur",
        "paiement_confirme_le",
        "disponible_le",
        "conditions",
        "demande",
        "montant_deduit",
        "devise",
        "utilisee_le",
        "annulee_le",
        "motif",
        "cree_le",
    )
    actions = ("action_annuler",)

    def get_queryset(self, request):
        return Remise.objects.using(ADMIN_DB).select_related(
            "beneficiaire_tenant", "beneficiaire_user", "parrainage"
        )

    @admin.display(description="Bénéficiaire")
    def beneficiaire(self, remise):
        return remise.beneficiaire_tenant or remise.beneficiaire_user

    @admin.display(description="Statut", ordering="statut")
    def statut_(self, remise):
        return _pastille(remise.get_statut_display(), TONS.get(remise.statut, ""))

    @admin.action(description="Annuler la remise…")
    def action_annuler(self, request, queryset):
        return self._geste(
            request,
            queryset,
            titre="Annuler la remise",
            aide=(
                "Seules les remises disponibles s'annulent. "
                "Le bénéficiaire ne pourra plus l'utiliser."
            ),
            action="action_annuler",
            executer=lambda r, motif: services.annuler_remise(r, request.user, motif),
            libelle=lambda r: f"{r.pourcentage} % — {self.beneficiaire(r)} ({r.filleul_nom})",
        )


@admin.register(PolitiquePlateforme)
class PolitiquePlateformeAdmin(admin.ModelAdmin):
    list_display = ("active", "cooling_mode", "validite_jours", "reservation_heures")
    fieldsets = (
        (
            "Programme salon → nouveau salon (Cas B)",
            {
                "fields": ("active",),
                "description": (
                    "Essai de 30 jours pour le filleul. Une remise de 10 % pour le salon parrain, "
                    "après le premier abonnement payé et le délai de sécurité. "
                    "Les conditions déjà accordées restent figées."
                ),
            },
        ),
        (
            "Disponibilité et validité",
            {
                "fields": (
                    "cooling_mode",
                    "cooling_jours",
                    "validite_jours",
                    "validite_depuis_disponibilite",
                )
            },
        ),
        (
            "Utilisation et annulation",
            {
                "fields": (
                    "recompenses_max_par_parrain",
                    "remises_max_par_echeance",
                    "reservation_heures",
                    "apres_remboursement",
                ),
                "description": (
                    "Un remboursement pendant le délai de sécurité annule la récompense. "
                    "Après disponibilité, elle est conservée. Une seule remise par échéance."
                ),
            },
        ),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).using(ADMIN_DB)

    def has_add_permission(self, request):
        return not PolitiquePlateforme.objects.using(
            ADMIN_DB
        ).exists() and super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        obj.full_clean()
        obj.save(using=ADMIN_DB)
        EvenementParrainage.objects.using(ADMIN_DB).create(
            cas="B",
            tenant=None,
            ressource="00000000-0000-0000-0000-000000000001",
            action="configuration",
            details={"acteur": str(request.user.pk), "champs": form.changed_data},
        )


class _LectureSeuleTenant(TenantScopedAdmin):
    def get_readonly_fields(self, request, obj=None):
        return tuple(f.name for f in self.model._meta.fields if f.name != "identite_filleul")


@admin.register(PolitiqueSalon)
class PolitiqueSalonAdmin(_LectureSeuleTenant):
    list_display = ("tenant", "active", "taux", "validite_jours", "plafond_montant", "devise")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(RecompenseClient)
class RecompenseClientAdmin(_LectureSeuleTenant):
    list_display = ("tenant", "parrain", "statut", "taux", "plafond_montant", "expire_le")
    list_filter = ("tenant", "statut")
    search_fields = ("parrain__email", "tenant__name")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CodeClientSalon)
class CodeClientSalonAdmin(_LectureSeuleTenant):
    list_display = ("tenant", "user", "code", "actif")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(EvenementParrainage)
class EvenementParrainageAdmin(_LectureSeule):
    list_display = ("cas", "tenant", "ressource", "action", "cree_le")
    list_filter = ("cas", "action", "tenant")
    search_fields = ("ressource", "details", "tenant__name")

    def get_queryset(self, request):
        return super().get_queryset(request).using(ADMIN_DB)
