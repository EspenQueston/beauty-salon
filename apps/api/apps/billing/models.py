"""Abonnements, factures et acomptes.

Deux flux d'argent bien distincts, et volontairement separes :

- **l'abonnement** que le salon paie a la plateforme ;
- **l'acompte** que la cliente verse au salon.

Aucune passerelle de paiement n'est branchee. Le document de cadrage
conditionne cette integration a la validation d'un partenaire par pays, et
prevoit explicitement une premiere etape ou l'encaissement a lieu hors ligne
et se constate dans l'outil. C'est ce qui est implemente ici : les montants,
les echeances et les statuts sont suivis, le reglement est saisi a la main.
"""

from decimal import Decimal

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.common.models import TenantOwnedModel, TimeStampedModel, UUIDModel


class Plan(UUIDModel, TimeStampedModel):
    """Offre commerciale.

    Table plateforme : les offres sont communes a tous les salons. Le prix,
    lui, vit sur l'abonnement - les tarifs du document doivent encore etre
    valides marche par marche, et un salon pilote n'a pas le tarif public.
    """

    class Code(models.TextChoices):
        TRIAL = "trial", _("Essai")
        SOLO = "solo", _("Solo")
        SALON = "salon", _("Salon")
        PRO = "pro", _("Pro")

    code = models.CharField(max_length=20, choices=Code.choices, unique=True)
    name = models.CharField(max_length=80)
    description = models.TextField(blank=True)

    # Bornes fonctionnelles de l'offre. `None` vaut « sans limite ».
    max_staff = models.PositiveSmallIntegerField(null=True, blank=True)
    allows_custom_domain = models.BooleanField(default=False)

    # Tarif indicatif, en francs CFA, a titre de reference interne.
    reference_price = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0")
    )
    position = models.PositiveSmallIntegerField(default=0)
    active = models.BooleanField(default=True)

    class Meta:
        verbose_name = _("offre")
        verbose_name_plural = _("offres")
        ordering = ("position", "reference_price")

    def __str__(self) -> str:
        return self.name


class Subscription(TenantOwnedModel):
    """Abonnement d'un salon a la plateforme.

    Un seul par salon. Le prix et la devise y sont figes : c'est ce qui
    permet d'accompagner un salon pilote a un tarif negocie sans toucher aux
    offres publiques, et de facturer en CDF a Kinshasa comme en XAF a
    Brazzaville.
    """

    class Status(models.TextChoices):
        TRIALING = "trialing", _("Période d'essai")
        ACTIVE = "active", _("Actif")
        PAST_DUE = "past_due", _("Impayé")
        CANCELLED = "cancelled", _("Résilié")

    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions")
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.TRIALING
    )

    price_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0")
    )
    currency = models.CharField(max_length=3, default="XAF")

    trial_ends_at = models.DateTimeField(null=True, blank=True)
    current_period_start = models.DateTimeField(default=timezone.now)
    current_period_end = models.DateTimeField()
    cancelled_at = models.DateTimeField(null=True, blank=True)

    # Frais de mise en route du document : ponctuels, distincts du mensuel.
    setup_fee_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0")
    )
    setup_fee_paid = models.BooleanField(default=False)

    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = _("abonnement")
        verbose_name_plural = _("abonnements")
        constraints = [
            models.UniqueConstraint(
                fields=["tenant"], name="one_subscription_per_tenant"
            )
        ]

    def __str__(self) -> str:
        return f"{self.plan.name} ({self.get_status_display()})"

    @property
    def is_running(self) -> bool:
        return self.status in (self.Status.TRIALING, self.Status.ACTIVE)

    @property
    def days_left_in_trial(self) -> int | None:
        if self.status != self.Status.TRIALING or self.trial_ends_at is None:
            return None
        remaining = (self.trial_ends_at - timezone.now()).days
        return max(remaining, 0)


class Invoice(TenantOwnedModel):
    """Facture d'abonnement.

    Emise par la plateforme, reglee hors ligne pour l'instant. Le numero est
    attribue a l'emission et jamais reutilise : une facture annulee se
    remplace par une nouvelle, elle ne se recycle pas.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", _("Brouillon")
        ISSUED = "issued", _("Émise")
        PAID = "paid", _("Payée")
        VOID = "void", _("Annulée")

    class Method(models.TextChoices):
        CASH = "cash", _("Espèces")
        MOBILE_MONEY = "mobile_money", _("Mobile Money")
        TRANSFER = "transfer", _("Virement")
        OTHER = "other", _("Autre")

    subscription = models.ForeignKey(
        Subscription, on_delete=models.PROTECT, related_name="invoices"
    )
    number = models.CharField(max_length=32, unique=True)

    period_start = models.DateTimeField()
    period_end = models.DateTimeField()

    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="XAF")
    label = models.CharField(max_length=150, blank=True)

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ISSUED
    )
    issued_at = models.DateTimeField(default=timezone.now)
    due_at = models.DateTimeField()
    paid_at = models.DateTimeField(null=True, blank=True)
    payment_method = models.CharField(
        max_length=20, choices=Method.choices, blank=True
    )
    payment_reference = models.CharField(max_length=100, blank=True)

    class Meta:
        verbose_name = _("facture")
        verbose_name_plural = _("factures")
        ordering = ("-issued_at",)
        indexes = [models.Index(fields=["tenant", "-issued_at"])]

    def __str__(self) -> str:
        return self.number

    @property
    def is_overdue(self) -> bool:
        return self.status == self.Status.ISSUED and self.due_at < timezone.now()
