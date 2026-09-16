"""Table de routage hostname -> salon.

Volontairement sans politique RLS : elle doit etre interrogeable *avant*
qu'un tenant soit resolu. C'est la seule table tenant lisible hors contexte,
et elle ne contient aucune donnee metier.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import TimeStampedModel, UUIDModel


class Domain(UUIDModel, TimeStampedModel):
    class Kind(models.TextChoices):
        PLATFORM_SUBDOMAIN = "platform_subdomain", _("Sous-domaine plateforme")
        CUSTOM_DOMAIN = "custom_domain", _("Domaine personnalisé")

    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="domains"
    )
    hostname = models.CharField(max_length=253, unique=True, db_index=True)
    kind = models.CharField(
        max_length=32, choices=Kind.choices, default=Kind.PLATFORM_SUBDOMAIN
    )
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
