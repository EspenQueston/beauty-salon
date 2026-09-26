"""Abonnements dans l'administration plateforme.

Quatre ecrans, pour quatre gestes :

  - **Tarifs d'abonnement** : le prix de chaque offre dans chaque devise ;
  - **Moyens de reglement** : les QR codes WeChat Pay et Alipay, et les
    comptes Mobile Money, pays par pays ;
  - **Paiements d'abonnement** : la file des paiements declares, a verifier,
    approuver ou refuser ;
  - **Abonnements** : l'etat de chaque salon, son historique, et les gestes
    exceptionnels — prolonger, suspendre, reactiver.

Deux permissions distinctes, en plus de la lecture :
`billing.review_subscriptionpaymentrequest` pour decider d'un paiement,
`billing.manage_subscription_manually` pour les gestes exceptionnels. Chaque
decision passe par `services.py` — jamais par l'enregistrement brut d'un
formulaire — et laisse sa trace dans l'historique et dans l'audit.
"""

from __future__ import annotations

from django import forms
from django.contrib import admin, messages
from django.contrib.admin import helpers
from django.http import FileResponse, Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from django.views.decorators.http import require_POST

from apps.common.admin import ADMIN_DB, TenantScopedAdmin, TenantScopedTabularInline
from apps.common.db import bypass_tenant_context, tenant_context

from . import services
from .models import (
    Invoice,
    Plan,
    PlanPrice,
    PlatformPaymentMethod,
    ProCapability,
    Subscription,
    SubscriptionEvent,
    SubscriptionPaymentRequest,
    SubscriptionReminder,
    type_du_qr,
)
from .services import BillingError, PaiementRefuse, mark_invoice_paid

PERM_VERIFIER = "billing.review_subscriptionpaymentrequest"
PERM_GESTES = "billing.manage_subscription_manually"

# Poids maximal d'un QR code : une image de quelques centaines de pixels.
QR_MAX_OCTETS = 5 * 1024 * 1024
QR_TYPES = {"image/jpeg", "image/png", "image/webp"}


def _pastille(texte: str, ton: str = "") -> str:
    classe = f"pill pill--{ton}" if ton else "pill"
    return format_html('<span class="{}">{}</span>', classe, texte)


def _montant(montant, devise: str) -> str:
    valeur = f"{montant:,.2f}".replace(",", " ").replace(".00", "")
    return f"{valeur} {devise}"


def _journal_reglages(request, objet, geste: str, champs=None) -> None:
    from apps.audit.models import AuditLog

    AuditLog.objects.using(ADMIN_DB).create(
        actor_user=request.user,
        action=AuditLog.Action.BILLING_SETTINGS_CHANGED,
        resource_type=objet._meta.model_name,
        resource_id=str(objet.pk),
        metadata={"geste": geste, "objet": str(objet), "champs": list(champs or [])},
    )


# ---------------------------------------------------------------------------
# Offres et tarifs
# ---------------------------------------------------------------------------


class PlanPriceInline(admin.TabularInline):
    model = PlanPrice
    extra = 0
    fields = ("currency", "amount", "active")
    verbose_name = "tarif"
    verbose_name_plural = "tarifs par devise"
    # Comme sur l'ecran des tarifs : desactiver, pas supprimer. Sans cela, la
    # case « supprimer » de la ligne rouvrait ce que l'autre ecran ferme.
    can_delete = False

    def get_readonly_fields(self, request, obj=None):
        # La devise d'une ligne existante ne change pas : la changer
        # re-tarifierait en silence une autre devise.
        return ("currency",) if obj is not None else ()


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("name", "groupe", "code", "billing_months", "tarifs", "active")
    list_filter = ("group", "active")
    search_fields = ("name", "code")
    ordering = ("group", "position")

    @admin.display(description="Groupe", ordering="group")
    def groupe(self, plan):
        return _pastille(plan.get_group_display(), "info" if plan.group == Plan.Groupe.PRO else "")

    inlines = (PlanPriceInline,)

    def get_readonly_fields(self, request, obj=None):
        # Le code et la duree definissent ce qu'un paiement accorde : le code
        # `monthly` renomme, plus aucun tarif n'est trouve ; la duree changee,
        # chaque approbation accorde autre chose que ce que le salon a paye.
        # Le groupe aussi : il decide des fonctions ouvertes a tous les abonnes.
        if obj is not None:
            return ("code", "group", "billing_months")
        return ()

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        _journal_reglages(request, obj, "modification" if change else "creation", form.changed_data)

    def has_delete_permission(self, request, obj=None):
        # Des abonnements et des paiements la referencent : on la desactive.
        return False

    @admin.display(description="Tarifs")
    def tarifs(self, plan):
        prix = [
            _montant(p.amount, p.currency)
            for p in plan.prices.filter(active=True).order_by("currency")
        ]
        return " · ".join(prix) or "—"

    def save_formset(self, request, form, formset, change):
        anciens = _anciens_montants(formset.forms)
        super().save_formset(request, form, formset, change)
        if formset.has_changed():
            _journal_reglages(request, form.instance, "tarifs", ["prices"])
        _annoncer_tarifs(request, [f.instance for f in formset.forms], anciens)


@admin.register(PlanPrice)
class PlanPriceAdmin(admin.ModelAdmin):
    """Le prix de chaque offre dans chaque devise.

    Aucun prix n'est deduit d'un autre : une devise sans ligne ici n'est pas
    proposee aux salons. Une demande deja envoyee garde le montant de son
    envoi, quel que soit le changement fait ici.
    """

    list_display = ("plan", "currency", "amount", "active", "updated_at")
    list_editable = ("amount", "active")
    list_filter = ("plan", "currency", "active")
    ordering = ("plan__position", "currency")

    def get_readonly_fields(self, request, obj=None):
        # Une ligne existante reste la meme offre dans la meme devise : seuls
        # le montant et l'etat changent, et ce changement-la est annonce.
        return ("plan", "currency") if obj is not None else ()

    def save_model(self, request, obj, form, change):
        anciens = _anciens_montants([form])
        super().save_model(request, obj, form, change)
        _journal_reglages(request, obj, "modification" if change else "creation", form.changed_data)
        _annoncer_tarifs(request, [obj], anciens)

    def has_delete_permission(self, request, obj=None):
        # Desactiver, pas supprimer : l'historique des demandes s'y rapporte.
        return False


def _anciens_montants(formulaires) -> dict:
    """Le montant d'avant, pour chaque tarif existant dont le montant change."""
    return {
        f.instance.pk: f.initial.get("amount")
        for f in formulaires
        if f.instance.pk and "amount" in getattr(f, "changed_data", ()) and f.initial.get("amount")
    }


def _annoncer_tarifs(request, prix, anciens: dict) -> None:
    """Un montant modifie est annonce par e-mail aux salons de cette devise."""
    annonces = 0
    for tarif in prix:
        ancien = anciens.get(tarif.pk)
        if ancien is not None and tarif.active and tarif.amount != ancien:
            services.annoncer_tarif(tarif, ancien)
            annonces += 1
    if annonces:
        messages.info(
            request,
            "Les salons qui règlent dans cette devise sont prévenus par e-mail du "
            "nouveau tarif. Les paiements déjà déclarés gardent l'ancien montant.",
        )


# ---------------------------------------------------------------------------
# Moyens de reglement de la plateforme
# ---------------------------------------------------------------------------


class MoyenForm(forms.ModelForm):
    class Meta:
        model = PlatformPaymentMethod
        fields = (
            "kind",
            "provider_name",
            "country",
            "currency",
            "qr_image",
            "account_number",
            "account_holder",
            "instructions",
            "active",
            "position",
        )
        widgets = {"instructions": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.tenants.models import Tenant

        self.fields["country"] = forms.ChoiceField(label="Pays", choices=Tenant.Country.choices)

    def clean_qr_image(self):
        fichier = self.cleaned_data.get("qr_image")
        # Une image deja enregistree n'a pas de `content_type` : seul un
        # nouveau televersement se verifie.
        if fichier and hasattr(fichier, "content_type"):
            if fichier.size > QR_MAX_OCTETS:
                raise forms.ValidationError("Le QR code dépasse 5 Mo.")
            if fichier.content_type not in QR_TYPES:
                raise forms.ValidationError("Envoyez une image JPEG, PNG ou WebP.")
        return fichier


@admin.register(PlatformPaymentMethod)
class PlatformPaymentMethodAdmin(admin.ModelAdmin):
    form = MoyenForm
    list_display = (
        "libelle_affiche",
        "kind",
        "pays",
        "currency",
        "account_number",
        "account_holder",
        "etat",
        "apercu_liste",
    )
    list_filter = ("kind", "country", "currency", "active")
    search_fields = ("provider_name", "account_number", "account_holder")
    readonly_fields = ("apercu",)
    actions = ("action_activer", "action_desactiver")
    fieldsets = (
        (
            None,
            {"fields": ("kind", "provider_name", ("country", "currency"), "active", "position")},
        ),
        (
            "WeChat Pay / Alipay",
            {
                "fields": ("qr_image", "apercu"),
                "description": "Le QR code que les salons scannent pour payer.",
            },
        ),
        (
            "Mobile Money",
            {
                "fields": ("account_number", "account_holder"),
                "description": "Le numéro qui reçoit les paiements, et le nom affiché au salon.",
            },
        ),
        ("Instructions", {"fields": ("instructions",)}),
    )

    @admin.display(description="Moyen", ordering="provider_name")
    def libelle_affiche(self, moyen):
        return moyen.libelle

    @admin.display(description="Pays", ordering="country")
    def pays(self, moyen):
        return moyen.get_country_display()

    @admin.display(description="État")
    def etat(self, moyen):
        if not moyen.active:
            return _pastille("Inactif")
        manques = moyen.problemes()
        if manques:
            return _pastille("Incomplet : " + ", ".join(manques), "danger")
        return _pastille("Proposé aux salons", "ok")

    def _url_qr(self, moyen) -> str:
        return reverse("admin:billing_platformpaymentmethod_qr", args=[moyen.pk])

    @admin.display(description="QR")
    def apercu_liste(self, moyen):
        if not moyen.qr_image:
            return "—"
        return format_html('<img src="{}" alt="QR code" class="qr-vignette">', self._url_qr(moyen))

    @admin.display(description="Aperçu")
    def apercu(self, moyen):
        if not moyen or not moyen.pk or not moyen.qr_image:
            return "Aucun QR code pour l'instant."
        return format_html('<img src="{}" alt="QR code" class="qr-apercu">', self._url_qr(moyen))

    def get_urls(self):
        return [
            path(
                "<uuid:pk>/qr/",
                self.admin_site.admin_view(self.vue_qr),
                name="billing_platformpaymentmethod_qr",
            ),
            *super().get_urls(),
        ]

    def vue_qr(self, request, pk):
        if not self.has_view_permission(request):
            raise Http404
        moyen = get_object_or_404(PlatformPaymentMethod, pk=pk)
        if not moyen.qr_image:
            raise Http404
        try:
            reponse = FileResponse(
                moyen.qr_image.open("rb"), content_type=type_du_qr(moyen.qr_image.name)
            )
        except FileNotFoundError as erreur:
            raise Http404 from erreur
        reponse["X-Content-Type-Options"] = "nosniff"
        reponse["Cache-Control"] = "private, max-age=300"
        return reponse

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        _journal_reglages(request, obj, "modification" if change else "creation", form.changed_data)

    @admin.action(description="Activer (proposer aux salons)")
    def action_activer(self, request, queryset):
        actives, refuses = [], []
        for moyen in queryset:
            if moyen.problemes():
                refuses.append(f"{moyen.libelle} ({', '.join(moyen.problemes())})")
                continue
            moyen.active = True
            moyen.save(update_fields=["active", "updated_at"])
            _journal_reglages(request, moyen, "activation")
            actives.append(moyen.libelle)
        if actives:
            self.message_user(request, "Activés : " + ", ".join(actives), messages.SUCCESS)
        if refuses:
            self.message_user(
                request, "Incomplets, non activés : " + "; ".join(refuses), messages.ERROR
            )

    @admin.action(description="Désactiver (retirer des salons)")
    def action_desactiver(self, request, queryset):
        for moyen in queryset:
            moyen.active = False
            moyen.save(update_fields=["active", "updated_at"])
            _journal_reglages(request, moyen, "desactivation")
        self.message_user(request, f"{queryset.count()} moyen(s) désactivé(s).", messages.SUCCESS)

    def has_delete_permission(self, request, obj=None):
        # Les demandes passees gardent leur copie du compte, mais la ligne
        # reste : on desactive, on ne supprime pas.
        return False


# ---------------------------------------------------------------------------
# Paiements d'abonnement : la file de verification
# ---------------------------------------------------------------------------

TONS_DEMANDE = {
    SubscriptionPaymentRequest.Status.PENDING: "warning",
    SubscriptionPaymentRequest.Status.APPROVED: "ok",
    SubscriptionPaymentRequest.Status.REJECTED: "danger",
}


@admin.register(SubscriptionPaymentRequest)
class SubscriptionPaymentRequestAdmin(TenantScopedAdmin):
    change_form_template = "admin/billing/subscriptionpaymentrequest/change_form.html"
    list_display = (
        "created_at",
        "tenant",
        "plan",
        "montant",
        "pays",
        "moyen",
        "reference",
        "statut",
        "reviewed_by",
    )
    list_filter = (
        "status",
        ("plan__group", admin.ChoicesFieldListFilter),
        "plan",
        "country",
        "currency",
        "method_kind",
        ("created_at", admin.DateFieldListFilter),
    )
    search_fields = ("tenant__name", "tenant__slug", "reference", "method_label")
    date_hierarchy = "created_at"
    list_select_related = ("tenant", "plan", "reviewed_by")
    ordering = ("-created_at",)
    readonly_fields = (
        "tenant",
        "plan",
        "billing_months",
        "country",
        "currency",
        "amount",
        "method_kind",
        "method_label",
        "method_account_number",
        "method_account_holder",
        "reference",
        "apercu_preuve",
        "submitted_by",
        "created_at",
        "status",
        "reviewed_by",
        "reviewed_at",
        "rejection_reason",
        "review_note",
        "period_start",
        "period_end",
        "invoice",
    )
    fieldsets = (
        (
            "Salon et offre",
            {"fields": ("tenant", "plan", "billing_months", "created_at", "submitted_by")},
        ),
        (
            "Paiement déclaré",
            {
                "fields": (
                    "amount",
                    "currency",
                    "country",
                    "method_kind",
                    "method_label",
                    "method_account_number",
                    "method_account_holder",
                    "reference",
                    "apercu_preuve",
                )
            },
        ),
        (
            "Vérification",
            {
                "fields": (
                    "status",
                    "reviewed_by",
                    "reviewed_at",
                    "rejection_reason",
                    "review_note",
                    "period_start",
                    "period_end",
                    "invoice",
                )
            },
        ),
    )

    def get_queryset(self, request):
        return SubscriptionPaymentRequest.all_tenants.using(ADMIN_DB).select_related(
            "tenant", "plan", "reviewed_by", "submitted_by", "proof", "invoice"
        )

    @admin.display(description="Montant", ordering="amount")
    def montant(self, demande):
        return _montant(demande.amount, demande.currency)

    @admin.display(description="Pays", ordering="country")
    def pays(self, demande):
        from apps.tenants.models import Tenant

        return dict(Tenant.Country.choices).get(demande.country, demande.country)

    @admin.display(description="Moyen", ordering="method_kind")
    def moyen(self, demande):
        return demande.method_label

    @admin.display(description="Statut", ordering="status")
    def statut(self, demande):
        return _pastille(demande.get_status_display(), TONS_DEMANDE.get(demande.status, ""))

    @admin.display(description="Preuve de paiement")
    def apercu_preuve(self, demande):
        if not demande.proof_id:
            return "Aucune capture jointe — vérifiez avec la référence."
        url = reverse("admin:billing_subscriptionpaymentrequest_preuve", args=[demande.pk])
        return format_html(
            '<a href="{0}" target="_blank" rel="noopener">'
            '<img src="{0}" alt="Preuve de paiement" class="paiement-preuve"></a>',
            url,
        )

    def get_urls(self):
        return [
            path(
                "<uuid:pk>/preuve/",
                self.admin_site.admin_view(self.vue_preuve),
                name="billing_subscriptionpaymentrequest_preuve",
            ),
            path(
                "<uuid:pk>/approuver/",
                self.admin_site.admin_view(require_POST(self.vue_approuver)),
                name="billing_subscriptionpaymentrequest_approuver",
            ),
            path(
                "<uuid:pk>/refuser/",
                self.admin_site.admin_view(require_POST(self.vue_refuser)),
                name="billing_subscriptionpaymentrequest_refuser",
            ),
            *super().get_urls(),
        ]

    def vue_preuve(self, request, pk):
        """La capture, servie a qui peut lire les paiements, et a lui seul."""
        if not self.has_view_permission(request):
            raise Http404
        demande = get_object_or_404(self.get_queryset(request), pk=pk)
        preuve = demande.proof
        if preuve is None or not preuve.file:
            raise Http404
        try:
            reponse = FileResponse(preuve.file.open("rb"), content_type=preuve.content_type or None)
        except FileNotFoundError as erreur:
            raise Http404 from erreur
        reponse["X-Content-Type-Options"] = "nosniff"
        reponse["Cache-Control"] = "private, no-store"
        return reponse

    def _retour(self, pk):
        return HttpResponseRedirect(
            reverse("admin:billing_subscriptionpaymentrequest_change", args=[pk])
        )

    def vue_approuver(self, request, pk):
        if not request.user.has_perm(PERM_VERIFIER):
            self.message_user(
                request, "Vous n'avez pas le droit de valider les paiements.", messages.ERROR
            )
            return self._retour(pk)
        try:
            demande = services.approuver_paiement(
                pk, administrateur=request.user, note=request.POST.get("note", "")
            )
        except PaiementRefuse as refus:
            self.message_user(request, str(refus), messages.WARNING)
            return self._retour(pk)
        fin = timezone.localtime(demande.period_end)
        self.message_user(
            request,
            f"Paiement approuvé : abonnement {demande.plan.name} de {demande.tenant} "
            f"jusqu'au {fin:%d/%m/%Y}. Facture {demande.invoice.number}.",
            messages.SUCCESS,
        )
        return self._retour(pk)

    def vue_refuser(self, request, pk):
        if not request.user.has_perm(PERM_VERIFIER):
            self.message_user(
                request, "Vous n'avez pas le droit de refuser les paiements.", messages.ERROR
            )
            return self._retour(pk)
        try:
            services.refuser_paiement(
                pk,
                administrateur=request.user,
                motif=request.POST.get("motif", ""),
                note=request.POST.get("note", ""),
            )
        except PaiementRefuse as refus:
            self.message_user(request, str(refus), messages.WARNING)
            return self._retour(pk)
        self.message_user(request, "Paiement refusé. Le salon voit le motif.", messages.SUCCESS)
        return self._retour(pk)

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        extra_context = extra_context or {}
        extra_context["peut_verifier"] = request.user.has_perm(PERM_VERIFIER)
        # Tout est en lecture seule : les boutons d'enregistrement ne
        # feraient rien, et laisseraient croire le contraire.
        extra_context.update(
            show_save=False, show_save_and_continue=False, show_save_and_add_another=False
        )
        if object_id:
            demande = self.get_queryset(request).filter(pk=object_id).first()
            if demande and demande.status == SubscriptionPaymentRequest.Status.PENDING:
                extra_context["apercu_periode"] = self._apercu_periode(demande)
        return super().changeform_view(request, object_id, form_url, extra_context)

    @staticmethod
    def _apercu_periode(demande) -> dict | None:
        """Ce que l'approbation accorderait, calcule sans rien ecrire.

        L'administrateur voit avant de cliquer jusqu'a quand le salon sera
        couvert : un paiement mensuel verse pendant l'essai ne commence pas
        aujourd'hui, et mieux vaut le lire que le decouvrir.
        """
        abonnement = (
            Subscription.all_tenants.using(ADMIN_DB)
            .select_related("tenant")
            .filter(pk=demande.subscription_id)
            .first()
        )
        if abonnement is None:
            return None
        debut, fin, _ancre, _mois = services._periode_accordee(
            abonnement, demande.billing_months, timezone.now()
        )
        return {"debut": debut, "fin": fin}

    def has_add_permission(self, request):
        # Un paiement se declare depuis le salon, jamais d'ici.
        return False

    def has_delete_permission(self, request, obj=None):
        # L'historique des paiements ne s'efface pas.
        return False


# ---------------------------------------------------------------------------
# Abonnements : etat, historique, gestes exceptionnels
# ---------------------------------------------------------------------------


class SubscriptionEventInline(TenantScopedTabularInline):
    model = SubscriptionEvent
    fk_name = "subscription"
    extra = 0
    can_delete = False
    fields = (
        "created_at",
        "kind",
        "status_before",
        "status_after",
        "period_end_after",
        "actor",
        "note",
    )
    readonly_fields = fields
    ordering = ("-created_at",)
    verbose_name_plural = "Historique"

    def has_add_permission(self, request, obj=None):
        return False


class GesteForm(forms.Form):
    """Le formulaire commun aux gestes exceptionnels : une justification."""

    note = forms.CharField(
        label="Justification",
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Obligatoire. Enregistrée dans l'historique et dans l'audit.",
    )


class ProlongationForm(GesteForm):
    mois = forms.TypedChoiceField(
        label="Durée accordée",
        choices=[(1, "1 mois"), (12, "12 mois")],
        coerce=int,
    )


class ChangementOffreForm(GesteForm):
    """Placer un salon sur une offre : c'est ici qu'on le passe à Pro."""

    offre = forms.ChoiceField(
        label="Nouvelle offre",
        choices=[
            ("monthly", "Standard — mensuel"),
            ("yearly", "Standard — annuel"),
            ("pro_monthly", "Pro — mensuel"),
            ("pro_yearly", "Pro — annuel"),
        ],
        help_text="S'applique tout de suite, avec ses droits.",
    )
    mois = forms.TypedChoiceField(
        label="Mois offerts en plus",
        choices=[(0, "Aucun — garder la date de fin actuelle"), (1, "1 mois"), (12, "12 mois")],
        coerce=int,
        initial=0,
        help_text="Un essai en cours devient une période de l'offre choisie, jusqu'à la même date.",
    )


TONS_ABONNEMENT = {
    Subscription.Status.TRIALING: "info",
    Subscription.Status.ACTIVE: "ok",
    Subscription.Status.PENDING_PAYMENT: "warning",
    Subscription.Status.EXPIRED: "danger",
    Subscription.Status.PAST_DUE: "danger",
    Subscription.Status.SUSPENDED: "danger",
}


@admin.register(Subscription)
class SubscriptionAdmin(TenantScopedAdmin):
    list_display = (
        "tenant",
        "plan",
        "groupe",
        "statut",
        "current_period_end",
        "acces",
        "programme",
        "price_amount",
        "currency",
    )
    list_filter = ("status", ("plan__group", admin.ChoicesFieldListFilter), "plan", "currency")
    search_fields = ("tenant__name", "tenant__slug")
    inlines = (SubscriptionEventInline,)
    actions = ("action_changer_offre", "action_prolonger", "action_suspendre", "action_reactiver")
    # Les dates et le statut ne se modifient qu'a travers les gestes traces :
    # un champ de date edite a la main n'aurait ni auteur ni motif.
    readonly_fields = (
        "tenant",
        "plan",
        "price_amount",
        "currency",
        "status",
        "trial_ends_at",
        "current_period_start",
        "current_period_end",
        "period_anchor",
        "anchor_months",
        "cancelled_at",
        "scheduled_plan",
        "scheduled_period_end",
        "scheduled_price_amount",
        "scheduled_currency",
        "groupe_effectif",
        "fonctions_ouvertes",
    )

    @admin.display(description="Groupe", ordering="plan__group")
    def groupe(self, abonnement):
        return _pastille(
            abonnement.plan.get_group_display(),
            "info" if abonnement.plan.group == Plan.Groupe.PRO else "",
        )

    @admin.display(description="Changement programmé")
    def programme(self, abonnement):
        if not abonnement.scheduled_plan_id:
            return "—"
        return format_html(
            "{} dès le {}",
            abonnement.scheduled_plan.name,
            timezone.localtime(abonnement.current_period_end).strftime("%d/%m/%Y"),
        )

    @admin.display(description="Groupe effectif")
    def groupe_effectif(self, abonnement):
        from .droits import groupe_effectif

        groupe = groupe_effectif(abonnement)
        return {"pro": "Pro", "standard": "Standard"}.get(groupe, "Accès fermé")

    @admin.display(description="Fonctions Pro ouvertes")
    def fonctions_ouvertes(self, abonnement):
        from .droits import fonctions_du_salon

        with bypass_tenant_context(), tenant_context(abonnement.tenant_id):
            fonctions = fonctions_du_salon(abonnement.tenant_id)
        ouvertes = [str(ProCapability.Code(code).label) for code, ok in fonctions.items() if ok]
        return ", ".join(ouvertes) or "—"

    @admin.display(description="Statut", ordering="status")
    def statut(self, abonnement):
        return _pastille(
            abonnement.get_status_display(), TONS_ABONNEMENT.get(abonnement.status, "")
        )

    @admin.display(description="Accès")
    def acces(self, abonnement):
        etat = services.acces_de(abonnement)
        if not etat.ouvert:
            return _pastille("Fermé", "danger")
        if etat.en_grace:
            return _pastille(f"Grâce jusqu'au {timezone.localtime(etat.jusqu_au):%d/%m}", "warning")
        return _pastille("Ouvert", "ok")

    def _geste(self, request, queryset, *, titre, formulaire, executer, action):
        if not request.user.has_perm(PERM_GESTES):
            self.message_user(
                request,
                "Vous n'avez pas le droit de modifier un abonnement à la main.",
                messages.ERROR,
            )
            return None
        form = formulaire(request.POST if "confirmer" in request.POST else None)
        if "confirmer" in request.POST and form.is_valid():
            reussis, echecs = 0, []
            for abonnement in queryset:
                try:
                    executer(abonnement, form.cleaned_data)
                    reussis += 1
                except (PaiementRefuse, BillingError) as refus:
                    echecs.append(f"{abonnement.tenant} : {refus}")
            if reussis:
                self.message_user(request, f"{titre} : {reussis} abonnement(s).", messages.SUCCESS)
            for echec in echecs:
                self.message_user(request, echec, messages.WARNING)
            return None
        return TemplateResponse(
            request,
            "admin/billing/subscription/geste.html",
            {
                **self.admin_site.each_context(request),
                "title": titre,
                "form": form,
                "abonnements": queryset,
                "action": action,
                "opts": self.model._meta,
                "action_checkbox_name": helpers.ACTION_CHECKBOX_NAME,
            },
        )

    @admin.action(description="Changer l'offre (Standard / Pro)…")
    def action_changer_offre(self, request, queryset):
        return self._geste(
            request,
            queryset,
            titre="Changer l'offre",
            formulaire=ChangementOffreForm,
            action="action_changer_offre",
            executer=lambda ab, d: services.changer_d_offre(
                ab.tenant_id,
                administrateur=request.user,
                code=d["offre"],
                mois=d["mois"],
                note=d["note"],
            ),
        )

    @admin.action(description="Prolonger à la main (exceptionnel)…")
    def action_prolonger(self, request, queryset):
        return self._geste(
            request,
            queryset,
            titre="Prolonger à la main",
            formulaire=ProlongationForm,
            action="action_prolonger",
            executer=lambda ab, d: services.prolonger_manuellement(
                ab.tenant_id, administrateur=request.user, mois=d["mois"], note=d["note"]
            ),
        )

    @admin.action(description="Suspendre l'accès…")
    def action_suspendre(self, request, queryset):
        return self._geste(
            request,
            queryset,
            titre="Suspendre l'accès",
            formulaire=GesteForm,
            action="action_suspendre",
            executer=lambda ab, d: services.suspendre(
                ab.tenant_id, administrateur=request.user, motif=d["note"]
            ),
        )

    @admin.action(description="Réactiver (lever une suspension)…")
    def action_reactiver(self, request, queryset):
        return self._geste(
            request,
            queryset,
            titre="Réactiver",
            formulaire=GesteForm,
            action="action_reactiver",
            executer=lambda ab, d: services.reactiver(
                ab.tenant_id, administrateur=request.user, note=d["note"]
            ),
        )

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SubscriptionEvent)
class SubscriptionEventAdmin(TenantScopedAdmin):
    list_display = (
        "created_at",
        "tenant",
        "kind",
        "status_before",
        "status_after",
        "period_end_after",
        "actor",
    )
    list_filter = ("kind", ("created_at", admin.DateFieldListFilter))
    search_fields = ("tenant__name", "tenant__slug", "note")
    date_hierarchy = "created_at"
    list_select_related = ("tenant", "actor")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SubscriptionReminder)
class SubscriptionReminderAdmin(TenantScopedAdmin):
    """Les rappels partis : pour repondre a « je n'ai jamais ete prevenue »."""

    list_display = ("created_at", "tenant", "kind", "period_end", "recipients")
    list_filter = ("kind", ("created_at", admin.DateFieldListFilter))
    search_fields = ("tenant__name", "tenant__slug")
    date_hierarchy = "created_at"
    list_select_related = ("tenant",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ProCapability)
class ProCapabilityAdmin(admin.ModelAdmin):
    """Couper ou rouvrir une fonction Pro pour tous les salons Pro.

    Les reglages des salons ne sont pas touches : une fonction coupee se met
    en pause, et revient telle quelle quand on la rouvre.
    """

    list_display = ("fonction", "etat", "active", "description")
    list_editable = ("active",)
    ordering = ("position",)
    fields = ("code", "active", "description", "position")
    readonly_fields = ("code",)

    @admin.display(description="Fonction", ordering="code")
    def fonction(self, capacite):
        return capacite.get_code_display()

    @admin.display(description="État")
    def etat(self, capacite):
        return (
            _pastille("Ouverte aux salons Pro", "ok")
            if capacite.active
            else _pastille("Coupée", "danger")
        )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        _journal_reglages(request, obj, "fonction_pro", form.changed_data)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Invoice)
class InvoiceAdmin(TenantScopedAdmin):
    list_display = (
        "number",
        "tenant",
        "amount",
        "currency",
        "status",
        "issued_at",
        "due_at",
        "paid_at",
    )
    list_filter = ("status", "currency", "payment_method")
    search_fields = ("number", "tenant__name", "payment_reference")
    date_hierarchy = "issued_at"
    actions = ("action_mark_paid",)

    # Une facture est une piece comptable : elle naît de l'approbation d'un
    # paiement, deja reglee, et sa recette est deja inscrite dans les deux
    # registres (celui du salon et celui de la plateforme). La modifier ou la
    # supprimer ici ferait diverger ces registres sans trace. Elle se lit,
    # c'est tout.
    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return [champ.name for champ in Invoice._meta.fields]

    @admin.action(description="Marquer comme réglée (espèces) — factures anciennes…")
    def action_mark_paid(self, request, queryset):
        """Solde une facture emise par l'ancien cycle, jamais une facture payee.

        Reserve au meme droit que les gestes exceptionnels, et trace : une
        recette inscrite a la main doit avoir un auteur.
        """
        if not request.user.has_perm(PERM_GESTES):
            self.message_user(
                request, "Vous n'avez pas le droit de solder une facture.", messages.ERROR
            )
            return
        reglees = 0
        for invoice in queryset.filter(status=Invoice.Status.ISSUED):
            try:
                mark_invoice_paid(invoice, method=Invoice.Method.CASH)
            except BillingError:
                continue
            reglees += 1
            _journal_reglages(request, invoice, "facture_soldee_a_la_main", ["status"])
        self.message_user(request, f"{reglees} facture(s) réglée(s).", messages.SUCCESS)

    def get_queryset(self, request):
        return Invoice.all_tenants.using(ADMIN_DB).select_related("tenant", "subscription")
