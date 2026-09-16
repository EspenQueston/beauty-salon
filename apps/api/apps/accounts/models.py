"""Identite, appartenance a un salon, et invitations d'equipe.

`User` et `Membership` sont des tables plateforme : un utilisateur peut
appartenir a plusieurs salons, et le middleware doit pouvoir lire ses
memberships *avant* qu'un contexte tenant existe. Elles ne portent donc pas
de politique RLS ; leur controle d'acces est applicatif.

`Invitation`, en revanche, est une donnee du salon et porte sa politique RLS
comme le reste.
"""

import hashlib
import secrets
from datetime import timedelta

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.common.models import TenantOwnedModel, TimeStampedModel, UUIDModel


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra):
        if not email:
            raise ValueError("Une adresse e-mail est obligatoire.")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        extra.setdefault("is_platform_admin", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("is_platform_admin", True)
        if not extra["is_staff"] or not extra["is_superuser"]:
            raise ValueError("Un superutilisateur doit avoir is_staff et is_superuser.")
        return self._create_user(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin, UUIDModel, TimeStampedModel):
    email = models.EmailField(_("e-mail"), unique=True)
    phone = models.CharField(_("téléphone"), max_length=32, blank=True)
    display_name = models.CharField(_("nom affiché"), max_length=120, blank=True)
    locale = models.CharField(max_length=10, default="fr")

    # Equipe SaaS. Ce drapeau n'accorde aucun acces aux donnees d'un salon
    # via l'API : l'admin plateforme passe par son propre alias de base.
    is_platform_admin = models.BooleanField(default=False)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = _("utilisateur")
        ordering = ("email",)

    def __str__(self) -> str:
        return self.display_name or self.email


class Membership(UUIDModel, TimeStampedModel):
    """Lien utilisateur <-> salon, porteur du role."""

    class Role(models.TextChoices):
        OWNER = "owner", _("Propriétaire")
        MANAGER = "manager", _("Gérant")
        RECEPTIONIST = "receptionist", _("Réceptionniste")
        STAFF = "staff", _("Prestataire")

    class Status(models.TextChoices):
        INVITED = "invited", _("Invité")
        ACTIVE = "active", _("Actif")
        DISABLED = "disabled", _("Désactivé")

    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="memberships"
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.STAFF)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        verbose_name = _("membre")
        ordering = ("tenant__name", "user__email")
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "user"], name="unique_membership_per_tenant_user"
            )
        ]
        indexes = [models.Index(fields=["user", "status"])]

    def __str__(self) -> str:
        return f"{self.user} @ {self.tenant} ({self.role})"

    @property
    def can_manage_salon(self) -> bool:
        return self.role in (self.Role.OWNER, self.Role.MANAGER)


class Invitation(TenantOwnedModel):
    """Invitation d'une personne a rejoindre l'equipe d'un salon.

    Contrairement a User et Membership, une invitation est une donnee du
    salon : elle porte donc une politique RLS comme le reste. La recherche
    par jeton, elle, a lieu avant qu'un contexte tenant existe - elle passe
    explicitement par l'alias `admin`, le chemin inter-tenants documente.

    Le jeton n'est jamais stocke en clair. Seule son empreinte SHA-256 est
    conservee : une fuite de la base ne donne acces a aucun compte.
    """

    VALIDITY = timedelta(days=7)

    email = models.EmailField(_("e-mail"))
    role = models.CharField(
        max_length=20, choices=Membership.Role.choices, default=Membership.Role.STAFF
    )
    token_hash = models.CharField(max_length=64, unique=True, db_index=True)
    expires_at = models.DateTimeField()

    invited_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sent_invitations",
    )
    accepted_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("invitation")
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["tenant", "email"])]
        constraints = [
            # Une seule invitation vivante par adresse et par salon : sinon
            # deux liens valides circuleraient pour la meme personne.
            models.UniqueConstraint(
                fields=["tenant", "email"],
                condition=models.Q(accepted_at__isnull=True, revoked_at__isnull=True),
                name="one_pending_invitation_per_email",
            )
        ]

    def __str__(self) -> str:
        return f"{self.email} ({self.get_role_display()})"

    @property
    def is_pending(self) -> bool:
        return (
            self.accepted_at is None
            and self.revoked_at is None
            and self.expires_at > timezone.now()
        )

    @property
    def status(self) -> str:
        if self.accepted_at:
            return "accepted"
        if self.revoked_at:
            return "revoked"
        if self.expires_at <= timezone.now():
            return "expired"
        return "pending"

    @staticmethod
    def hash_token(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    @classmethod
    def issue(cls, *, tenant, email, role, invited_by=None):
        """Cree l'invitation et renvoie le jeton en clair, une seule fois."""
        token = secrets.token_urlsafe(32)
        invitation = cls.objects.create(
            tenant=tenant,
            email=email.strip().lower(),
            role=role,
            token_hash=cls.hash_token(token),
            expires_at=timezone.now() + cls.VALIDITY,
            invited_by=invited_by,
        )
        return invitation, token
