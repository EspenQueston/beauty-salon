from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import AdminPasswordChangeForm
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from apps.common.admin import TenantScopedAdmin
from apps.common.admin_suppression import SuppressionDefinitiveMixin

from .forms import UserChangeForm, UserCreationForm
from .models import Invitation, Membership, User


class MembershipInline(admin.TabularInline):
    model = Membership
    extra = 0
    autocomplete_fields = ("tenant",)


@admin.register(User)
class UserAdmin(SuppressionDefinitiveMixin, BaseUserAdmin):
    add_form = UserCreationForm
    form = UserChangeForm
    change_password_form = AdminPasswordChangeForm
    ordering = ("email",)
    list_display = (
        "email",
        "display_name",
        "adresse_verifiee",
        "is_platform_admin",
        "is_active",
        "is_staff",
    )
    list_filter = (
        ("email_verified_at", admin.EmptyFieldListFilter),
        "is_platform_admin",
        "is_active",
        "is_staff",
    )
    actions = ("action_renvoyer_verification",)
    search_fields = ("email", "display_name", "phone")
    inlines = (MembershipInline,)

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profil", {"fields": ("display_name", "phone", "locale")}),
        (
            "Droits",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_platform_admin",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Dates", {"fields": ("email_verified_at", "last_login", "created_at", "updated_at")}),
        ("Zone sensible", {"fields": ("lien_suppression",)}),
    )
    readonly_fields = (
        "email_verified_at",
        "last_login",
        "created_at",
        "updated_at",
        "lien_suppression",
    )

    @admin.display(description="E-mail confirmé", boolean=True, ordering="email_verified_at")
    def adresse_verifiee(self, user) -> bool:
        return user.email_verified_at is not None

    @admin.action(description="Renvoyer le lien de confirmation d'adresse")
    def action_renvoyer_verification(self, request, queryset):
        """La preuve vient toujours du clic de la personne : l'equipe renvoie le lien,
        elle ne coche pas la case a sa place."""
        from django.contrib import messages
        from django.db import transaction

        from . import tasks

        envoyes = 0
        for user in queryset.filter(email_verified_at__isnull=True, is_active=True):
            base = tasks.base_cliente(user) if hasattr(user, "client_profile") else ""
            user_id = str(user.pk)
            transaction.on_commit(lambda u=user_id, b=base: tasks.verification.delay(u, b))
            envoyes += 1
        self.message_user(
            request,
            f"Lien renvoyé à {envoyes} compte(s)." if envoyes else "Aucun compte à confirmer.",
            messages.SUCCESS if envoyes else messages.INFO,
        )

    # --- Suppression definitive (apps/common/suppression.py) ---------------

    def suppression_identifiant(self, user) -> str:
        return user.email

    def suppression_contexte(self, request, user) -> dict:
        from apps.common.suppression import obstacles_compte

        salons = ", ".join(str(m.tenant) for m in user.memberships.select_related("tenant"))
        return {
            "obstacles": obstacles_compte(user, request.user),
            "resume": (
                "Partent : le compte, ses accès aux salons"
                + (f" ({salons})" if salons else "")
                + ", ses appareils de connexion, ses notifications et son espace cliente."
            ),
            "conserve": [
                "Ce qu'il a fait dans les salons (rendez-vous, gestes d'abonnement), sans son nom.",
                "Le journal d'audit, qui garde une adresse masquée et le motif.",
            ],
        }

    def suppression_executer(self, request, user, donnees) -> str:
        from apps.common.suppression import masquer, supprimer_compte

        supprimer_compte(user, administrateur=request.user, motif=donnees["motif"])
        return f"Compte {masquer(user.email)} supprimé définitivement."

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "display_name", "password1", "password2"),
            },
        ),
    )


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "tenant", "role", "status")
    list_filter = ("role", "status")
    search_fields = ("user__email", "tenant__name", "tenant__slug")
    autocomplete_fields = ("tenant", "user")


@admin.register(Invitation)
class InvitationAdmin(TenantScopedAdmin):
    """Les invitations d'equipe envoyees par les salons.

    -----------------------------------------------------------------------
    Le ticket qu'elle resout
    -----------------------------------------------------------------------

    « J'ai invite ma collegue, elle n'a rien recu. » Trois causes possibles,
    et on ne pouvait en verifier aucune : l'invitation n'a jamais ete creee,
    elle a expire, ou elle a deja ete acceptee sous une autre adresse. La
    colonne « Etat » les distingue d'un coup d'oeil.

    -----------------------------------------------------------------------
    Le jeton n'apparait nulle part, et il ne le peut pas
    -----------------------------------------------------------------------

    Seule son empreinte SHA-256 est stockee — c'est ce qui fait qu'une fuite
    de la base ne donne acces a aucun compte. Il n'y a donc rien a afficher,
    et surtout rien a renvoyer depuis ici : le seul geste correct est de
    demander au salon de reinviter, ce qui emet un jeton neuf.
    """

    list_display = ("email", "tenant", "role", "etat", "invited_by", "created_at")
    list_filter = ("role", "tenant")
    search_fields = ("email", "tenant__name", "invited_by__email")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    list_select_related = ("tenant", "invited_by")
    exclude = ("token_hash",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields if f.name != "token_hash"]

    @admin.display(description="État")
    def etat(self, invitation):
        if invitation.revoked_at:
            return mark_safe('<span style="color:var(--bs-ink-muted)">révoquée</span>')
        if invitation.accepted_at:
            return format_html(
                '<span style="color:var(--bs-ok)">● acceptée le {}</span>',
                invitation.accepted_at.strftime("%d/%m/%Y"),
            )
        if invitation.expires_at <= timezone.now():
            return mark_safe(
                '<span style="color:var(--bs-bad)">expirée — le salon doit réinviter</span>'
            )
        return format_html(
            '<span style="color:var(--bs-warn)">en attente — expire le {}</span>',
            invitation.expires_at.strftime("%d/%m/%Y"),
        )
