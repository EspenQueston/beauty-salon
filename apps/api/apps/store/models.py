"""La boutique du salon.

---------------------------------------------------------------------------
Le probleme qu'elle resout
---------------------------------------------------------------------------

Beaucoup de prestations demandent une fourniture que la cliente apporte
elle-meme : des meches pour des tresses, une perruque a poser, un kit de
coloration. Le salon le sait, la cliente pas toujours - et elle arrive les
mains vides pour un rendez-vous de quatre heures qu'il faut annuler.

Deux objets suffisent a regler cela :

  - **`Requirement`** dit ce qu'il faut prevoir pour une prestation. C'est
    d'abord une *information*, affichee avant la reservation. Meme sans rien
    a vendre, un salon gagne a ecrire « prevoir 3 paquets de meches ».
  - **`Product`** est ce que le salon peut fournir a la place. Rattache a une
    exigence, il transforme « apportez vos meches » en « apportez-les, ou
    achetez-les ici ».

L'ordre compte : l'exigence existe sans le produit, jamais l'inverse. Un
catalogue de vente detache des prestations serait une boutique en ligne, ce
que ce produit n'est pas.

---------------------------------------------------------------------------
Le stock
---------------------------------------------------------------------------

Il est decremente **a la reservation**, pas a la prestation. Sinon deux
clientes reservent la derniere perruque le meme matin et l'une des deux
l'apprend en arrivant. Une annulation le rend.
"""

from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import TenantOwnedModel


class Product(TenantOwnedModel):
    """Un article que le salon vend au comptoir."""

    class Unit(models.TextChoices):
        PIECE = "piece", _("À l'unité")
        PACK = "pack", _("Paquet")
        METER = "meter", _("Mètre")
        GRAM = "gram", _("Gramme")

    name = models.CharField(_("nom"), max_length=150)
    description = models.TextField(_("description"), blank=True)

    price = models.DecimalField(
        _("prix"),
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )
    unit = models.CharField(
        _("vendu"), max_length=10, choices=Unit.choices, default=Unit.PIECE
    )

    # `None` signifie « je n'en manque jamais » : un salon qui vend du
    # shampooing au litre n'a pas envie de tenir un inventaire. Zero, lui,
    # veut dire « rupture », ce qui n'est pas la meme chose.
    stock = models.IntegerField(
        _("quantité en stock"),
        null=True,
        blank=True,
        help_text=_("Laissez vide si vous n'en manquez jamais."),
    )
    low_stock_at = models.PositiveSmallIntegerField(
        _("seuil d'alerte"),
        default=3,
        help_text=_("En dessous, l'article est signalé dans votre boutique."),
    )

    image = models.ForeignKey(
        "media.MediaAsset",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name=_("photo"),
    )

    active = models.BooleanField(_("proposé à la vente"), default=True)
    position = models.PositiveSmallIntegerField(_("ordre d'affichage"), default=0)

    class Meta:
        verbose_name = _("article")
        verbose_name_plural = _("boutique")
        ordering = ("position", "name")
        constraints = [
            models.UniqueConstraint(
                fields=("tenant", "name"), name="unique_product_name_per_tenant"
            )
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def in_stock(self) -> bool:
        return self.stock is None or self.stock > 0

    @property
    def is_low(self) -> bool:
        return self.stock is not None and 0 < self.stock <= self.low_stock_at

    @property
    def available(self) -> bool:
        """Vendable maintenant : proposé et pas en rupture."""
        return self.active and self.in_stock


class Requirement(TenantOwnedModel):
    """Ce qu'il faut prévoir pour une prestation.

    D'abord une information, affichee avant la reservation. Les articles
    rattaches, s'il y en a, la transforment en choix : apporter, ou acheter.
    """

    service = models.ForeignKey(
        "catalog.Service",
        on_delete=models.CASCADE,
        related_name="requirements",
        verbose_name=_("prestation"),
    )

    label = models.CharField(
        _("ce qu'il faut"),
        max_length=150,
        help_text=_("« 3 paquets de mèches », « une perruque », « votre kit »."),
    )
    detail = models.CharField(
        _("précision"),
        max_length=255,
        blank=True,
        help_text=_("Longueur, couleur, quantité conseillée…"),
    )

    # Une exigence facultative se saute sans explication ; une exigence
    # obligatoire demande une reponse explicite - apporter ou acheter - avant
    # de pouvoir reserver.
    mandatory = models.BooleanField(_("indispensable"), default=True)

    products = models.ManyToManyField(
        Product,
        through="RequirementProduct",
        related_name="requirements",
        verbose_name=_("articles proposés"),
        blank=True,
    )

    position = models.PositiveSmallIntegerField(_("ordre d'affichage"), default=0)

    class Meta:
        verbose_name = _("fourniture à prévoir")
        verbose_name_plural = _("fournitures à prévoir")
        ordering = ("position", "id")

    def __str__(self) -> str:
        return self.label


class RequirementProduct(TenantOwnedModel):
    """Article proposé pour satisfaire une exigence.

    Table de liaison explicite plutot qu'un ManyToMany nu : elle porte le
    tenant, donc la politique RLS s'y applique comme partout ailleurs.
    """

    requirement = models.ForeignKey(
        Requirement, on_delete=models.CASCADE, related_name="offers"
    )
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="offers"
    )

    class Meta:
        verbose_name = _("article proposé")
        verbose_name_plural = _("articles proposés")
        constraints = [
            models.UniqueConstraint(
                fields=("requirement", "product"),
                name="unique_product_per_requirement",
            )
        ]

    def __str__(self) -> str:
        return f"{self.requirement} → {self.product}"
