"""Journal des evenements sensibles.

Table plateforme : `tenant` y est nullable (une action d'administration
n'appartient a aucun salon) et elle ne porte pas de politique RLS. Un salon
ne la lit jamais ; seule l'equipe SaaS y accede, via l'admin.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import TimeStampedModel, UUIDModel


class AuditLog(UUIDModel, TimeStampedModel):
    class Action(models.TextChoices):
        BOOKING_CREATED = "booking.created", _("Réservation créée")
        BOOKING_CANCELLED = "booking.cancelled", _("Réservation annulée")
        BOOKING_RESCHEDULED = "booking.rescheduled", _("Réservation déplacée")
        BOOKING_STATUS_CHANGED = "booking.status_changed", _("Statut modifié")
        CUSTOMER_NOTES_VIEWED = "customer.notes_viewed", _("Notes clientes consultées")
        TENANT_CREATED = "tenant.created", _("Salon créé")
        TENANT_STATUS_CHANGED = "tenant.status_changed", _("Statut du salon modifié")
        MEMBERSHIP_CHANGED = "membership.changed", _("Membership modifié")
        TENANT_ACCESS_DENIED = "tenant.access_denied", _("Accès croisé refusé")
        # Suppression depuis l'administration plateforme. C'est la trace
        # qui rend cette permission acceptable : l'equipe SaaS peut effacer
        # la donnee d'un salon, mais jamais sans laisser dire qui, quand et
        # quoi.
        PLATFORM_DELETED = "platform.deleted", _("Supprimé depuis l'administration")
        # Abonnements : chaque decision qui touche a l'acces d'un salon ou a
        # un montant laisse une trace nominative.
        SUBSCRIPTION_PAYMENT_SUBMITTED = (
            "subscription.payment_submitted",
            _("Paiement d'abonnement déclaré"),
        )
        SUBSCRIPTION_PAYMENT_APPROVED = (
            "subscription.payment_approved",
            _("Paiement d'abonnement approuvé"),
        )
        SUBSCRIPTION_PAYMENT_REJECTED = (
            "subscription.payment_rejected",
            _("Paiement d'abonnement refusé"),
        )
        SUBSCRIPTION_MANUAL_CHANGE = (
            "subscription.manual_change",
            _("Abonnement modifié à la main"),
        )
        BILLING_SETTINGS_CHANGED = (
            "billing.settings_changed",
            _("Tarifs ou moyens de règlement modifiés"),
        )
        DOMAIN_CLAIMED = "domain.claimed", _("Domaine personnalisé demandé")
        DOMAIN_CONNECTED = "domain.connected", _("Domaine personnalisé relié")
        DOMAIN_REMOVED = "domain.removed", _("Domaine personnalisé retiré")
        SITE_CUSTOMIZED = "site.customized", _("Personnalisation du site modifiée")
        ASSISTANT_SETTINGS_CHANGED = (
            "assistant.settings_changed",
            _("Réglages des assistants IA modifiés"),
        )
        # Suppressions definitives, par la procedure dediee : la trace
        # survit a ce qu'elle decrit (salon et compte sont partis).
        TENANT_DELETED = "tenant.deleted", _("Salon supprimé définitivement")
        USER_DELETED = "user.deleted", _("Compte supprimé définitivement")
        # Parrainage : chaque etape qui peut valoir une remise laisse une trace.
        REFERRAL_DETECTED = "referral.detected", _("Parrainage détecté")
        REFERRAL_ELIGIBLE = "referral.eligible", _("Parrainage admissible")
        REFERRAL_REVIEW_REQUIRED = "referral.review_required", _("Parrainage à revoir")
        REFERRAL_REWARD_CREATED = "referral.reward_created", _("Remise de parrainage créée")
        REFERRAL_ADMIN = "referral.admin", _("Parrainage corrigé par l'administration")
        # Securite des comptes (voir apps/accounts/journal.py).
        AUTH_LOGIN_SUCCEEDED = "auth.login_succeeded", _("Connexion réussie")
        AUTH_LOGIN_FAILED = "auth.login_failed", _("Connexion échouée")
        AUTH_ACCOUNT_LOCKED = "auth.account_locked", _("Connexions suspendues (trop d'échecs)")
        AUTH_MFA_FAILED = "auth.mfa_failed", _("Code de double authentification refusé")
        AUTH_MFA_ENABLED = "auth.mfa_enabled", _("Double authentification activée")
        AUTH_MFA_DISABLED = "auth.mfa_disabled", _("Double authentification désactivée")
        AUTH_RECOVERY_CODES_REGENERATED = (
            "auth.recovery_codes_regenerated",
            _("Codes de secours régénérés"),
        )
        AUTH_PASSWORD_RESET = "auth.password_reset", _("Mot de passe réinitialisé")
        AUTH_PASSWORD_CHANGED = "auth.password_changed", _("Mot de passe changé")
        AUTH_EMAIL_CHANGED = "auth.email_changed", _("Adresse e-mail changée")
        AUTH_EMAIL_VERIFIED = "auth.email_verified", _("Adresse e-mail vérifiée")
        AUTH_PASSWORD_BREACHED = (
            "auth.password_breached",
            _("Mot de passe refusé (présent dans des fuites)"),
        )

    tenant = models.ForeignKey(
        "tenants.Tenant",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
    )
    actor_user = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=64, choices=Action.choices)
    resource_type = models.CharField(max_length=64, blank=True)
    resource_id = models.CharField(max_length=64, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = _("événement d'audit")
        verbose_name_plural = _("événements d'audit")
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["tenant", "-created_at"]),
            models.Index(fields=["action", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.action} @ {self.created_at:%d/%m/%Y %H:%M}"
