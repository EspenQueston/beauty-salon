"""Horaires, indisponibilites et reservations.

La regle centrale du produit est ici : **deux clientes ne peuvent pas
reserver le meme prestataire au meme moment**. Elle n'est pas confiee au
code applicatif seul mais a une contrainte d'exclusion PostgreSQL, qui tient
meme sous requetes concurrentes et meme si une reservation est creee par un
chemin qu'on n'avait pas prevu.
"""

from decimal import Decimal

from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateTimeRangeField, RangeBoundary, RangeOperators
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Func, Q
from django.utils.translation import gettext_lazy as _

from apps.common.models import TenantOwnedModel
from apps.salons.models import ServiceMode


class Weekday(models.IntegerChoices):
    MONDAY = 0, _("Lundi")
    TUESDAY = 1, _("Mardi")
    WEDNESDAY = 2, _("Mercredi")
    THURSDAY = 3, _("Jeudi")
    FRIDAY = 4, _("Vendredi")
    SATURDAY = 5, _("Samedi")
    SUNDAY = 6, _("Dimanche")


class TsTzRange(Func):
    """tstzrange(starts_at, ends_at, '[)') pour la contrainte d'exclusion."""

    function = "TSTZRANGE"
    output_field = DateTimeRangeField()


class BusinessHours(TenantOwnedModel):
    """Horaires recurrents, en heure locale du salon.

    `staff_member` nul signifie « horaires du salon », appliques a tous les
    prestataires qui n'ont pas leurs propres horaires. Cela evite de ressaisir
    la meme grille pour chaque personne d'une equipe.
    """

    staff_member = models.ForeignKey(
        "staff.StaffMember",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="business_hours",
    )
    weekday = models.PositiveSmallIntegerField(choices=Weekday.choices)
    starts_at = models.TimeField(_("ouverture"))
    ends_at = models.TimeField(_("fermeture"))

    class Meta:
        verbose_name = _("horaire")
        verbose_name_plural = _("horaires")
        ordering = ("weekday", "starts_at")
        indexes = [models.Index(fields=["tenant", "staff_member", "weekday"])]
        constraints = [
            models.CheckConstraint(
                condition=Q(ends_at__gt=models.F("starts_at")),
                name="business_hours_end_after_start",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_weekday_display()} {self.starts_at}-{self.ends_at}"


class AvailabilityException(TenantOwnedModel):
    """Conge, blocage ponctuel ou ouverture exceptionnelle.

    Stocke en UTC, contrairement a BusinessHours : une exception vise un
    moment precis, pas une case de grille hebdomadaire.
    """

    class Kind(models.TextChoices):
        BLOCKED = "blocked", _("Créneau bloqué")
        LEAVE = "leave", _("Congé")
        EXTRA_OPENING = "extra_opening", _("Ouverture exceptionnelle")

    staff_member = models.ForeignKey(
        "staff.StaffMember",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="availability_exceptions",
    )
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.BLOCKED)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    reason = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = _("indisponibilité")
        verbose_name_plural = _("indisponibilités")
        ordering = ("starts_at",)
        indexes = [models.Index(fields=["tenant", "staff_member", "starts_at", "ends_at"])]
        constraints = [
            models.CheckConstraint(
                condition=Q(ends_at__gt=models.F("starts_at")),
                name="availability_exception_end_after_start",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} {self.starts_at:%d/%m/%Y %H:%M}"


class BookingStatus(models.TextChoices):
    PENDING_PAYMENT = "pending_payment", _("En attente de paiement")
    REQUESTED = "requested", _("Demandée")
    CONFIRMED = "confirmed", _("Confirmée")
    CHECKED_IN = "checked_in", _("Cliente arrivée")
    COMPLETED = "completed", _("Terminée")
    CANCELLED = "cancelled", _("Annulée")
    NO_SHOW = "no_show", _("Absente")


class BookingSource(models.TextChoices):
    WEB = "web", _("Mini-site")
    STAFF = "staff", _("Saisie salon")
    WHATSAPP = "whatsapp", _("WhatsApp")
    MARKETPLACE = "marketplace", _("Marketplace")


# Statuts qui occupent reellement le creneau. Le moteur de disponibilites et
# la contrainte d'exclusion doivent rester d'accord : ils lisent tous les deux
# cette constante. Declaree au niveau du module car le corps d'une classe
# Meta ne voit pas les attributs de la classe englobante.
BLOCKING_BOOKING_STATUSES = (
    BookingStatus.PENDING_PAYMENT,
    BookingStatus.REQUESTED,
    BookingStatus.CONFIRMED,
    BookingStatus.CHECKED_IN,
)


class Booking(TenantOwnedModel):
    Status = BookingStatus
    Source = BookingSource
    BLOCKING_STATUSES = BLOCKING_BOOKING_STATUSES

    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.PROTECT, related_name="bookings"
    )
    # Non nullable : sans prestataire identifie, la contrainte d'exclusion ne
    # pourrait pas empecher les chevauchements.
    staff_member = models.ForeignKey(
        "staff.StaffMember", on_delete=models.PROTECT, related_name="bookings"
    )
    service = models.ForeignKey(
        "catalog.Service", on_delete=models.PROTECT, related_name="bookings"
    )

    starts_at = models.DateTimeField(db_index=True)
    ends_at = models.DateTimeField()

    status = models.CharField(
        max_length=20,
        choices=BookingStatus.choices,
        default=BookingStatus.REQUESTED,
        db_index=True,
    )
    source = models.CharField(
        max_length=20, choices=BookingSource.choices, default=BookingSource.WEB
    )

    # Instantanes : le catalogue evolue, une reservation passee doit rester
    # lisible telle qu'elle a ete vendue.
    service_name = models.CharField(max_length=150)

    # La devise dans laquelle ce rendez-vous a ete vendu.
    #
    # Figee ici, et pas lue sur le salon, pour la meme raison que le nom de
    # la prestation juste au-dessus : un salon peut changer de devise - il
    # demenage, ou il s'est trompe a l'inscription. Sans cette colonne, les
    # 25 000 francs d'une pose de l'an dernier s'afficheraient du jour au
    # lendemain comme 25 000 yuans, soit quatre-vingt-cinq fois leur valeur.
    # Le montant, lui, ne serait pas converti : c'est l'etiquette qui
    # mentirait, ce qui est la pire des deux erreurs.
    currency = models.CharField(_("devise"), max_length=3, blank=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    deposit_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    deposit_paid = models.BooleanField(_("acompte encaissé"), default=False)
    deposit_paid_at = models.DateTimeField(null=True, blank=True)

    # Montant reellement recu, qui n'est pas toujours celui attendu : une
    # cliente laisse ce qu'elle a sur elle, arrondit, ou complete plus tard.
    # Enregistrer le montant demande a la place du montant recu fausserait
    # la caisse du salon des le premier arrondi.
    deposit_received = models.DecimalField(
        _("montant reçu"),
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    deposit_method = models.CharField(
        max_length=20,
        blank=True,
        choices=[
            ("cash", _("Espèces")),
            ("mobile_money", _("Mobile Money")),
            ("transfer", _("Virement")),
            ("other", _("Autre")),
        ],
    )

    location_mode = models.CharField(
        max_length=10, choices=ServiceMode.choices, default=ServiceMode.SALON
    )
    address = models.CharField(max_length=255, blank=True)

    # Zone de deplacement, figee comme le reste de la vente.
    #
    # Le nom est copie plutot que reference : une zone renommee ou supprimee
    # ne doit pas reecrire ce qui a ete convenu, et un rendez-vous d'il y a
    # six mois doit rester lisible tel qu'il a ete vendu. Meme discipline que
    # `service_name` et `total_amount` juste au-dessus.
    #
    # `total_amount` contient deja les frais : c'est le montant annonce a la
    # cliente. Le detail est garde a part pour que le salon sache ce qui
    # relevait de la prestation et ce qui relevait du trajet.
    # Options retenues, figees au moment de la vente.
    #
    # Une liste JSON plutot qu'une table de liaison : ce sont des lignes
    # mortes, jamais requetees, jamais jointes. Une table imposerait de
    # garder l'option d'origine vivante pour lire une reservation d'il y a
    # six mois - exactement ce que l'instantane existe pour eviter.
    #
    # Forme : [{"name": "Longueur XL", "price": "5000.00", "minutes": 45}]
    options_snapshot = models.JSONField(
        _("options retenues"), default=list, blank=True
    )
    options_amount = models.DecimalField(
        _("supplément options"),
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )

    # Articles achetes au salon pendant la reservation.
    #
    # Meme discipline que les options : une liste figee, jamais une jointure.
    # Retarifer une perruque demain ne doit pas reecrire ce qui a ete vendu
    # aujourd'hui.
    items_snapshot = models.JSONField(
        _("articles achetés"), default=list, blank=True
    )
    items_amount = models.DecimalField(
        _("total boutique"),
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )

    travel_zone_name = models.CharField(
        _("zone de déplacement"), max_length=120, blank=True
    )
    travel_fee_amount = models.DecimalField(
        _("frais de déplacement"),
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )

    customer_note = models.TextField(blank=True)
    internal_note = models.TextField(blank=True)

    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.CharField(max_length=255, blank=True)
    # Pose par la tache de rappel : garantit qu'un rappel part une seule fois,
    # meme si la tache periodique repasse sur la meme reservation.
    reminder_sent_at = models.DateTimeField(null=True, blank=True)

    # Meme role pour la demande d'avis, envoyee apres la prestation. Un
    # compteur separe : rappel et demande d'avis partent a des moments
    # differents, et rater l'un ne doit pas empecher l'autre.
    review_invited_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("réservation")
        verbose_name_plural = _("réservations")
        ordering = ("-starts_at",)
        indexes = [
            models.Index(fields=["tenant", "starts_at"]),
            models.Index(fields=["tenant", "staff_member", "starts_at"]),
            models.Index(fields=["tenant", "status", "starts_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(ends_at__gt=models.F("starts_at")),
                name="booking_end_after_start",
            ),
            # Le garde-fou anti double-reservation. Il s'applique dans la
            # base : ni un bug de service, ni une requete concurrente, ni un
            # import en masse ne peuvent le contourner.
            ExclusionConstraint(
                name="no_overlapping_bookings_per_staff",
                expressions=[
                    ("tenant", RangeOperators.EQUAL),
                    ("staff_member", RangeOperators.EQUAL),
                    (
                        TsTzRange("starts_at", "ends_at", RangeBoundary()),
                        RangeOperators.OVERLAPS,
                    ),
                ],
                condition=Q(status__in=list(BLOCKING_BOOKING_STATUSES)),
            ),
        ]

    def save(self, *args, **kwargs):
        """Fige la devise a la creation, si personne ne l'a posee.

        Au niveau du modele plutot que dans `create_booking` : une
        reservation s'ecrit aussi depuis l'agenda du salon, depuis une
        commande de peuplement et, un jour, depuis un import. Chacun de ces
        chemins aurait pu l'oublier, et l'oubli ne se voit qu'apres coup,
        quand un salon change de devise et que les lignes sans etiquette
        basculent avec lui.
        """
        if not self.currency:
            from apps.common.devise import devise_du_salon

            # `tenant_id` peut encore etre vide ici : la classe de base le
            # remplit depuis le contexte, juste apres. On resout donc la
            # meme source qu'elle.
            self.currency = devise_du_salon(self.tenant_id)
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.service_name} - {self.starts_at:%d/%m/%Y %H:%M}"

    @property
    def is_active(self) -> bool:
        return self.status in self.BLOCKING_STATUSES


# La liste d'attente vit dans son propre module : elle ne partage rien avec
# le reste de l'agenda, et melanger les deux rendait ce fichier illisible.
from .waitlist import WaitlistEntry  # noqa: E402,F401
