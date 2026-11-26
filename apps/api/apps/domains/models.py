"""Table de routage hostname -> salon.

Volontairement sans politique RLS : elle doit etre interrogeable *avant*
qu'un tenant soit resolu. C'est la seule table tenant lisible hors contexte,
et elle ne contient aucune donnee metier.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import TenantOwnedModel, TimeStampedModel, UUIDModel


class Domain(UUIDModel, TimeStampedModel):
    class Kind(models.TextChoices):
        PLATFORM_SUBDOMAIN = "platform_subdomain", _("Sous-domaine plateforme")
        CUSTOM_DOMAIN = "custom_domain", _("Domaine personnalisé")

    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="domains")
    hostname = models.CharField(max_length=253, unique=True, db_index=True)
    kind = models.CharField(max_length=32, choices=Kind.choices, default=Kind.PLATFORM_SUBDOMAIN)
    is_primary = models.BooleanField(default=False)
    # Reste nul tant que la propriete du domaine n'est pas prouvee. Les
    # domaines personnalises sont une option payante : la verification
    # arrivera avec eux.
    verified_at = models.DateTimeField(null=True, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        verbose_name = _("domaine")
        ordering = ("hostname",)
        constraints = [
            models.UniqueConstraint(
                fields=["tenant"],
                condition=models.Q(is_primary=True),
                name="one_primary_domain_per_tenant",
            )
        ]

    def __str__(self) -> str:
        return self.hostname

    def save(self, *args, **kwargs):
        self.hostname = self.hostname.strip().lower()
        return super().save(*args, **kwargs)


class DomainClaim(TenantOwnedModel):
    """La demande d'un salon pour relier un domaine qu'il possede.

    Separee de `Domain`, qui route le trafic : une demande n'est qu'une
    intention, et plusieurs salons peuvent en deposer une pour le meme nom
    sans que personne ne soit bloque. Seul le premier a prouver qu'il
    controle le domaine (un enregistrement TXT a son nom) obtient la ligne
    `Domain`, unique par nom — c'est elle qui fait arriver le trafic.

    Taper un nom de domaine ne suffit jamais a le pointer sur un salon.
    """

    class Status(models.TextChoices):
        PENDING = "pending", _("En attente de vérification")
        CONNECTED = "connected", _("Relié")

    hostname = models.CharField(_("domaine"), max_length=253)
    token = models.CharField(_("jeton de vérification"), max_length=64)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=255, blank=True)
    requested_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        verbose_name = _("demande de domaine")
        verbose_name_plural = _("demandes de domaine")
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("tenant", "hostname"), name="une_demande_par_domaine_et_salon"
            )
        ]

    def __str__(self) -> str:
        return self.hostname

    def save(self, *args, **kwargs):
        self.hostname = self.hostname.strip().lower().rstrip(".")
        return super().save(*args, **kwargs)
