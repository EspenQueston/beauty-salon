"""Catalogue de prestations."""

from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import TenantOwnedModel
from apps.salons.models import ServiceMode


class ServiceCategory(TenantOwnedModel):
    name = models.CharField(_("nom"), max_length=120)
    position = models.PositiveSmallIntegerField(_("ordre d'affichage"), default=0)
    active = models.BooleanField(_("visible"), default=True)

    class Meta:
        verbose_name = _("catégorie de prestation")
        verbose_name_plural = _("catégories de prestation")
        ordering = ("position", "name")
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "name"], name="unique_category_name_per_tenant"
            )
        ]

    def __str__(self) -> str:
        return self.name


class Service(TenantOwnedModel):
    """Une prestation vendable.

    Le prix peut etre ferme, indicatif ("a partir de") ou sur devis : les
    tresses et perruques se chiffrent rarement au tarif unique, et forcer un
    montant exact ferait fuir les prestataires.
    """

    class PriceKind(models.TextChoices):
        FIXED = "fixed", _("Prix ferme")
        FROM = "from", _("À partir de")
        QUOTE = "quote", _("Sur devis")

    category = models.ForeignKey(
        ServiceCategory,
        on_delete=models.PROTECT,
        related_name="services",
        verbose_name=_("catégorie"),
    )
    name = models.CharField(_("nom"), max_length=150)
    description = models.TextField(_("description"), blank=True)

    duration_minutes = models.PositiveIntegerField(
        _("durée en minutes"), validators=[MinValueValidator(5)]
    )
    price_kind = models.CharField(
        _("type de tarif"),
        max_length=10,
        choices=PriceKind.choices,
        default=PriceKind.FIXED,
    )
    price_amount = models.DecimalField(
        _("tarif"),
        max_digits=12, decimal_places=2, default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    # ----- acompte ----------------------------------------------------------
    #
    # Un interrupteur, et rien de plus.
    #
    # Ce champ portait un **montant**, et c'etait la source d'une
    # contradiction visible par les clientes : la fiche annoncait « acompte de
    # 5 000 » pendant que la reservation reclamait 7 500, parce que la regle du
    # salon - un pourcentage - l'emportait. Le salon publiait un chiffre et en
    # facturait un autre.
    #
    # Le « combien » vit desormais a un seul endroit, la fiche du salon :
    # un taux, et un plancher. Ici on ne dit plus que « oui » ou « non » -
    # parce que c'est la seule chose qui varie vraiment d'une prestation a
    # l'autre : une coupe de vingt minutes ne demande pas d'engagement, une
    # pose de quatre heures si.
    requires_deposit = models.BooleanField(
        _("demande un acompte"),
        default=False,
        help_text=_(
            "Le montant vient de la règle de votre salon : un pourcentage de "
            "la prestation, avec un minimum."
        ),
    )

    location_mode = models.CharField(
        _("lieu de la prestation"),
        max_length=10,
        choices=ServiceMode.choices,
        default=ServiceMode.SALON,
    )
    image = models.ForeignKey(
        "media.MediaAsset", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+", verbose_name=_("photo"),
    )

    position = models.PositiveSmallIntegerField(_("ordre d'affichage"), default=0)
    active = models.BooleanField(_("proposée à la réservation"), default=True)

    class Meta:
        verbose_name = _("prestation")
        verbose_name_plural = _("prestations")
        ordering = ("position", "name")
        indexes = [models.Index(fields=["tenant", "active"])]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(duration_minutes__gte=5),
                name="service_duration_at_least_5_minutes",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class ServiceOption(TenantOwnedModel):
    """Variante d'une prestation : ce qui s'ajoute au prix **et au temps**.

    ---------------------------------------------------------------------
    Le piege : une option n'est pas qu'une ligne de facture
    ---------------------------------------------------------------------

    « Longueur XL », « meches fournies », « retrait de l'ancienne coiffure » :
    chacune coute quelque chose, et la plupart prennent aussi du temps. Ne
    retenir que le prix serait le raccourci evident et la faute : une pose XL
    qui demande quarante-cinq minutes de plus se verrait proposer un creneau
    qui ne la contient pas, et la cliente suivante attendrait sur le trottoir.

    `duration_delta_minutes` entre donc dans le calcul des creneaux, au meme
    titre que la duree de la prestation elle-meme.

    Les deux ecarts peuvent valoir zero : « couleur au choix » ne change ni
    le prix ni la duree, et reste une information utile a la cliente.
    """

    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        related_name="options",
        verbose_name=_("prestation"),
    )
    name = models.CharField(_("nom"), max_length=120)
    description = models.CharField(_("précision"), max_length=255, blank=True)

    price_delta = models.DecimalField(
        _("supplément"),
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
        help_text=_("0 pour une option sans supplément."),
    )
    duration_delta_minutes = models.PositiveSmallIntegerField(
        _("temps supplémentaire (minutes)"),
        default=0,
        help_text=_("Compté dans la recherche de créneau, pas seulement affiché."),
    )

    position = models.PositiveSmallIntegerField(_("ordre d'affichage"), default=0)
    active = models.BooleanField(_("proposée à la réservation"), default=True)

    class Meta:
        verbose_name = _("option de prestation")
        verbose_name_plural = _("options de prestation")
        ordering = ("position", "name")
        constraints = [
            # Deux options du meme nom sur la meme prestation rendraient le
            # choix de la cliente ambigu.
            models.UniqueConstraint(
                fields=("service", "name"), name="unique_option_per_service"
            )
        ]

    def __str__(self) -> str:
        return self.name


class Resource(TenantOwnedModel):
    """Ce dont le salon n'a qu'un nombre limite : fauteuils, bacs, cabines.

    ---------------------------------------------------------------------
    Le probleme que ca resout
    ---------------------------------------------------------------------

    Le moteur de creneaux verifie qu'un prestataire est libre. Il ne verifie
    pas qu'il reste un bac a shampooing. Un salon a trois coiffeuses et deux
    bacs : a 14 h, trois clientes peuvent se voir proposer le meme creneau de
    lavage, et la troisieme attendra debout.

    La ressource est comptee, pas reservee nominativement : on ne dit pas
    « le fauteuil numero 2 », on dit « il en reste un sur trois ». C'est ainsi
    qu'un salon raisonne, et cela evite d'avoir a gerer une affectation que
    personne ne respecte dans la vraie vie.
    """

    class Kind(models.TextChoices):
        CHAIR = "chair", _("Fauteuil")
        BASIN = "basin", _("Bac à shampooing")
        ROOM = "room", _("Cabine")
        EQUIPMENT = "equipment", _("Matériel")

    name = models.CharField(_("nom"), max_length=120)
    kind = models.CharField(
        _("type"), max_length=20, choices=Kind.choices, default=Kind.CHAIR
    )
    capacity = models.PositiveSmallIntegerField(
        _("quantité disponible"),
        default=1,
        # Un salon n'a pas quinze mille bacs. Le plafond ne protege pas la
        # base - le champ tient de toute facon - il protege du chiffre saisi
        # par erreur, qui rendrait la ressource sans effet sans que personne
        # ne comprenne pourquoi.
        validators=[MinValueValidator(1), MaxValueValidator(999)],
        help_text=_("Combien vous en avez. Deux bacs : 2."),
    )
    active = models.BooleanField(_("prise en compte"), default=True)

    class Meta:
        verbose_name = _("ressource")
        verbose_name_plural = _("ressources")
        ordering = ("kind", "name")
        constraints = [
            models.UniqueConstraint(
                fields=("tenant", "name"), name="unique_resource_name_per_tenant"
            )
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.capacity})"


class ServiceResource(TenantOwnedModel):
    """Ce qu'une prestation mobilise. Une unite par rendez-vous.

    Table de liaison explicite plutot qu'un ManyToMany nu : elle porte le
    tenant, donc la politique RLS s'y applique comme partout ailleurs. Un
    ManyToMany implicite creerait une table hors de ce controle.
    """

    service = models.ForeignKey(
        Service, on_delete=models.CASCADE, related_name="resource_links"
    )
    resource = models.ForeignKey(
        Resource, on_delete=models.CASCADE, related_name="service_links"
    )

    class Meta:
        verbose_name = _("ressource d'une prestation")
        verbose_name_plural = _("ressources des prestations")
        constraints = [
            models.UniqueConstraint(
                fields=("service", "resource"), name="unique_service_resource"
            )
        ]

    def __str__(self) -> str:
        return f"{self.service} → {self.resource}"
