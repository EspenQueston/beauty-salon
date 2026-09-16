"""Recettes et depenses du salon.

---------------------------------------------------------------------------
Un seul modele pour les deux sens
---------------------------------------------------------------------------

Une recette et une depense partagent tout : un montant, une date, un motif,
un moyen de paiement. Les separer en deux tables aurait double chaque
requete de synthese - et la question qu'on pose le plus souvent, « qu'est-ce
qu'il me reste ce mois-ci », a besoin des deux en meme temps.

Le sens est donc une colonne, et le montant reste **toujours positif**.
Stocker les depenses en negatif est tentant et se paie cher : un signe perdu
au passage d'un formulaire transforme une charge en recette, et plus rien ne
permet de le detecter.

---------------------------------------------------------------------------
Ce qui vient tout seul
---------------------------------------------------------------------------

Une prestation honoree produit sa recette automatiquement (voir
`services.py`). Sans cela, le salon devrait ressaisir a la main ce que le
logiciel sait deja - et un cahier de comptes qu'on doit remplir deux fois
n'est jamais rempli.

Ces lignes automatiques restent modifiables : le montant encaisse differe
parfois du tarif (remise, arrondi, pourboire), et c'est le salon qui a
raison, pas le catalogue.
"""

from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import TenantOwnedModel


class Transaction(TenantOwnedModel):
    class Kind(models.TextChoices):
        INCOME = "income", _("Recette")
        EXPENSE = "expense", _("Dépense")

    class IncomeCategory(models.TextChoices):
        SERVICE = "service", _("Prestation")
        PRODUCT = "product", _("Vente de produit")
        TIP = "tip", _("Pourboire")
        OTHER_INCOME = "other_income", _("Autre recette")

    class ExpenseCategory(models.TextChoices):
        SUPPLIES = "supplies", _("Fournitures et produits")
        RENT = "rent", _("Loyer")
        WAGES = "wages", _("Salaires")
        UTILITIES = "utilities", _("Eau, électricité, internet")
        TRANSPORT = "transport", _("Transport et déplacements")
        MARKETING = "marketing", _("Publicité")
        EQUIPMENT = "equipment", _("Matériel")
        TAXES = "taxes", _("Taxes et impôts")
        OTHER_EXPENSE = "other_expense", _("Autre dépense")

    class Method(models.TextChoices):
        CASH = "cash", _("Espèces")
        MOBILE_MONEY = "mobile_money", _("Mobile Money")
        TRANSFER = "transfer", _("Virement")
        CARD = "card", _("Carte")
        WECHAT = "wechat", _("WeChat Pay")
        OTHER = "other", _("Autre")

    kind = models.CharField(_("sens"), max_length=10, choices=Kind.choices)

    # Une seule colonne pour les deux familles de categories : le sens dit
    # laquelle lire. Deux colonnes dont une toujours vide se desynchronisent.
    category = models.CharField(_("poste"), max_length=30)

    label = models.CharField(
        _("libellé"),
        max_length=200,
        help_text=_("Ce que c'était, en clair. « Mèches kanekalon », « loyer mars »."),
    )
    amount = models.DecimalField(
        _("montant"),
        max_digits=12,
        decimal_places=2,
        # Toujours positif : c'est `kind` qui porte le sens.
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    occurred_on = models.DateField(_("date"))
    method = models.CharField(
        _("moyen"), max_length=20, choices=Method.choices, default=Method.CASH
    )

    # Pour une recette : d'ou vient l'argent. Pour une depense : a qui il va.
    counterparty = models.CharField(
        _("origine ou bénéficiaire"), max_length=150, blank=True
    )
    note = models.TextField(_("détail"), blank=True)

    class Source(models.TextChoices):
        MANUAL = "manual", _("Saisie manuelle")
        BOOKING_DEPOSIT = "booking_deposit", _("Acompte encaissé")
        BOOKING_BALANCE = "booking_balance", _("Solde de la prestation")
        BOOKING_ITEMS = "booking_items", _("Vente au comptoir")
        SUBSCRIPTION = "subscription", _("Abonnement à la plateforme")

    # D'ou vient la ligne.
    #
    # Sert a deux choses. La premiere est l'affichage : une ligne que le salon
    # n'a pas saisie doit se signaler, sinon il cherche qui l'a ecrite. La
    # seconde est l'idempotence : avec le rendez-vous ou la facture, ce champ
    # forme la cle qui empeche de compter deux fois le meme argent.
    source = models.CharField(
        _("origine"), max_length=20, choices=Source.choices, default=Source.MANUAL
    )

    # Un rendez-vous produit jusqu'a deux lignes : l'acompte le jour ou il est
    # encaisse, puis le solde le jour de la prestation. D'ou une cle etrangere
    # et non une relation un-a-un - et une contrainte d'unicite sur le couple
    # (rendez-vous, origine), qui interdit le doublon sans interdire la paire.
    booking = models.ForeignKey(
        "scheduling.Booking",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="transactions",
        verbose_name=_("rendez-vous d'origine"),
    )

    invoice = models.ForeignKey(
        "billing.Invoice",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="transactions",
        verbose_name=_("facture d'origine"),
    )

    class Meta:
        verbose_name = _("mouvement")
        verbose_name_plural = _("recettes et dépenses")
        ordering = ("-occurred_on", "-created_at")
        indexes = [
            models.Index(fields=["tenant", "occurred_on"]),
            models.Index(fields=["tenant", "kind", "occurred_on"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name="transaction_amount_is_positive",
            ),
            # Un acompte ne s'encaisse qu'une fois, un solde ne se solde
            # qu'une fois. La contrainte vit en base plutot que dans le code
            # appelant : c'est la seule facon de resister a deux requetes
            # simultanees.
            models.UniqueConstraint(
                fields=("booking", "source"),
                condition=models.Q(booking__isnull=False),
                name="one_transaction_per_booking_and_source",
            ),
            models.UniqueConstraint(
                fields=("invoice",),
                condition=models.Q(invoice__isnull=False),
                name="one_transaction_per_invoice",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} — {self.label} ({self.amount})"

    @property
    def signed_amount(self) -> Decimal:
        """Montant oriente, pour les additions. Jamais stocke tel quel."""
        return self.amount if self.kind == self.Kind.INCOME else -self.amount

    @property
    def category_label(self) -> str:
        choices = (
            self.IncomeCategory if self.kind == self.Kind.INCOME else self.ExpenseCategory
        )
        # `str()` : les libelles sont des traductions differees, et les
        # laisser tels quels casse tout consommateur qui attend une chaine
        # (export Excel, serialisation).
        return str(dict(choices.choices).get(self.category, self.category))
