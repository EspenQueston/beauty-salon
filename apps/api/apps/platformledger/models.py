"""Les comptes de la plateforme elle-meme.

---------------------------------------------------------------------------
Pourquoi une table separee des comptes des salons
---------------------------------------------------------------------------

Ce ne sont pas les memes comptes, et ils n'appartiennent pas aux memes gens.

`finance.Transaction` porte l'argent **d'un salon** : il est soumis a la
politique RLS, invisible d'un salon a l'autre, et la plateforme n'y touche
jamais en ecriture. Cette table-ci porte l'argent **de la plateforme** :
elle n'a pas de tenant, elle n'est lisible que depuis l'administration, et
aucun salon n'y a acces.

Les melanger aurait produit exactement la confusion qu'on veut eviter : un
abonnement regle est une *depense* pour le salon et une *recette* pour la
plateforme. C'est le meme versement vu des deux cotes du registre, et chaque
cote doit pouvoir etre lu sans l'autre.

Le lien vers le salon reste, en simple reference : la plateforme a besoin de
savoir de qui vient son chiffre d'affaires, sans que cela ouvre quoi que ce
soit dans l'autre sens.
"""

from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _


class PlatformEntry(models.Model):
    class Kind(models.TextChoices):
        INCOME = "income", _("Recette")
        EXPENSE = "expense", _("Dépense")

    class IncomeCategory(models.TextChoices):
        SUBSCRIPTION = "subscription", _("Abonnement salon")
        SETUP = "setup", _("Mise en service")
        OTHER_INCOME = "other_income", _("Autre recette")

    class ExpenseCategory(models.TextChoices):
        HOSTING = "hosting", _("Hébergement et infrastructure")
        DOMAINS = "domains", _("Domaines et certificats")
        TOOLING = "tooling", _("Outils et licences")
        SALARIES = "salaries", _("Salaires et prestataires")
        MARKETING = "marketing", _("Acquisition")
        FEES = "fees", _("Frais bancaires")
        TAXES = "taxes", _("Taxes et impôts")
        OTHER_EXPENSE = "other_expense", _("Autre dépense")

    class Source(models.TextChoices):
        MANUAL = "manual", _("Saisie manuelle")
        SUBSCRIPTION = "subscription", _("Facture d'abonnement réglée")

    kind = models.CharField(_("sens"), max_length=10, choices=Kind.choices)
    category = models.CharField(_("poste"), max_length=30)
    source = models.CharField(
        _("origine"), max_length=20, choices=Source.choices, default=Source.MANUAL
    )

    label = models.CharField(_("libellé"), max_length=200)
    amount = models.DecimalField(
        _("montant"),
        max_digits=14,
        decimal_places=2,
        # Toujours positif : c'est `kind` qui porte le sens, jamais le signe.
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    currency = models.CharField(max_length=3, default="XAF")
    occurred_on = models.DateField(_("date"))

    # Simple reference, sans cascade : un salon supprime ne doit pas effacer
    # le chiffre d'affaires qu'il a genere.
    tenant = models.ForeignKey(
        "tenants.Tenant",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name=_("salon concerné"),
    )
    invoice = models.ForeignKey(
        "billing.Invoice",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="platform_entries",
        verbose_name=_("facture d'origine"),
    )

    note = models.TextField(_("détail"), blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("mouvement plateforme")
        verbose_name_plural = _("comptes de la plateforme")
        ordering = ("-occurred_on", "-created_at")
        indexes = [models.Index(fields=["kind", "occurred_on"])]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name="platform_entry_amount_is_positive",
            ),
            # Une facture ne produit qu'une recette, meme si le marquage
            # « payee » repasse.
            models.UniqueConstraint(
                fields=("invoice",),
                condition=models.Q(invoice__isnull=False),
                name="one_platform_entry_per_invoice",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} — {self.label} ({self.amount})"

    @property
    def category_label(self) -> str:
        choices = (
            self.IncomeCategory if self.kind == self.Kind.INCOME else self.ExpenseCategory
        )
        return str(dict(choices.choices).get(self.category, self.category))
