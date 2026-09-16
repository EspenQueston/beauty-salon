"""Le salon, vu comme locataire de la plateforme."""

from django.core.validators import RegexValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import TimeStampedModel, UUIDModel

slug_validator = RegexValidator(
    regex=r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$",
    message=_("Uniquement des minuscules, chiffres et tirets."),
)


class Tenant(UUIDModel, TimeStampedModel):
    """Un salon. Aucune politique RLS ici : c'est la table de reference."""

    class Status(models.TextChoices):
        PENDING = "pending", _("En préparation")
        ACTIVE = "active", _("Actif")
        SUSPENDED = "suspended", _("Suspendu")

    class Plan(models.TextChoices):
        TRIAL = "trial", _("Essai")
        SOLO = "solo", _("Solo")
        SALON = "salon", _("Salon")
        PRO = "pro", _("Pro")

    class Country(models.TextChoices):
        CONGO = "CG", _("Congo-Brazzaville")
        DRC = "CD", _("République démocratique du Congo")
        CHINA = "CN", _("Chine")

    class Currency(models.TextChoices):
        XAF = "XAF", _("Franc CFA")
        CDF = "CDF", _("Franc congolais")
        CNY = "CNY", _("Yuan")
        USD = "USD", _("Dollar américain")
        EUR = "EUR", _("Euro")

    name = models.CharField(_("nom"), max_length=120)
    # Sert de sous-domaine par defaut : <slug>.PLATFORM_DOMAIN
    slug = models.SlugField(_("identifiant"), max_length=63, unique=True,
                            validators=[slug_validator])
    status = models.CharField(
        _("statut"), max_length=20, choices=Status.choices, default=Status.PENDING
    )
    plan = models.CharField(
        _("offre"), max_length=20, choices=Plan.choices, default=Plan.TRIAL
    )
    country = models.CharField(
        _("pays"), max_length=2, choices=Country.choices, default=Country.CONGO
    )
    # Toutes les dates sont stockees en UTC ; ce fuseau sert a calculer les
    # creneaux et a afficher les horaires du salon.
    timezone = models.CharField(
        _("fuseau horaire"), max_length=64, default="Africa/Brazzaville"
    )
    currency = models.CharField(
        _("devise"), max_length=3, choices=Currency.choices, default=Currency.XAF
    )

    class Meta:
        verbose_name = _("salon")
        verbose_name_plural = _("salons")
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name

    @property
    def is_active(self) -> bool:
        return self.status == self.Status.ACTIVE
