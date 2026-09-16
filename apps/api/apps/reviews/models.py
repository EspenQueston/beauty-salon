"""Avis laisses par les clientes apres un rendez-vous.

Un avis n'est pas un commentaire libre : il est **rattache a un rendez-vous
reellement honore**. C'est ce qui le distingue d'un formulaire de contact, et
c'est ce qui le rend credible — personne ne peut noter un salon ou il n'est
jamais alle, ni noter deux fois le meme passage.

Le lien passe par un jeton signe envoye par e-mail apres la prestation ; voir
`services.py`.
"""

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import TenantOwnedModel


class Review(TenantOwnedModel):
    class Status(models.TextChoices):
        PUBLISHED = "published", _("Publié")
        HIDDEN = "hidden", _("Masqué")

    # Un rendez-vous, un avis. La contrainte est portee par la base, pas
    # seulement par la vue : un double envoi ne cree pas deux notes.
    booking = models.OneToOneField(
        "scheduling.Booking",
        on_delete=models.CASCADE,
        related_name="review",
        verbose_name=_("rendez-vous"),
    )
    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.CASCADE,
        related_name="reviews",
        verbose_name=_("cliente"),
    )

    # Nom recopie a l'ecriture : le fichier clientes peut etre corrige ou
    # anonymise plus tard, l'avis publie ne doit pas changer de signature
    # sous les yeux des visiteurs.
    author_name = models.CharField(_("signature"), max_length=150)

    # ----- les notes --------------------------------------------------------
    #
    # Cinq criteres, et une note d'ensemble qui en decoule.
    #
    # ---------------------------------------------------------------------
    # Pourquoi cinq plutot qu'un
    # ---------------------------------------------------------------------
    #
    # Une note unique dit qu'un salon vaut 3 sur 5. Elle ne dit pas *quoi*
    # reparer - et c'est la seule chose qu'un avis puisse apporter a une
    # gerante. Le detail separe ce qui se corrige d'un geste (l'heure tenue,
    # le menage) de ce qui demande du temps (le geste technique).
    #
    # Ils sont facultatifs un par un : une cliente qui n'a pas d'avis sur le
    # rapport qualite-prix laisse la ligne vide plutot que de mettre 3 par
    # defaut, ce qui polluerait la moyenne d'une note qu'elle n'a pas voulu
    # donner.
    #
    # ---------------------------------------------------------------------
    # Pourquoi la note d'ensemble est calculee, et non demandee
    # ---------------------------------------------------------------------
    #
    # Demander six notes serait six decisions, et la derniere serait posee au
    # hasard. Surtout, une note d'ensemble saisie a la main peut contredire
    # le detail - 4 etoiles au-dessus de cinq criteres a 2 - et personne ne
    # saurait laquelle croire. Elle est donc la moyenne des criteres donnes,
    # arrondie : elle ne peut pas mentir sur ce qu'elle resume.
    CRITERIA = (
        ("rating_result", _("Le résultat")),
        ("rating_welcome", _("L'accueil")),
        ("rating_punctuality", _("La ponctualité")),
        ("rating_cleanliness", _("La propreté du salon")),
        ("rating_value", _("Le rapport qualité-prix")),
    )

    rating = models.PositiveSmallIntegerField(
        _("note d'ensemble"),
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text=_("Moyenne des critères notés, arrondie."),
    )

    rating_result = models.PositiveSmallIntegerField(
        _("le résultat"),
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    rating_welcome = models.PositiveSmallIntegerField(
        _("l'accueil"),
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    rating_punctuality = models.PositiveSmallIntegerField(
        _("la ponctualité"),
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    rating_cleanliness = models.PositiveSmallIntegerField(
        _("la propreté du salon"),
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    rating_value = models.PositiveSmallIntegerField(
        _("le rapport qualité-prix"),
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )

    comment = models.TextField(_("commentaire"), blank=True)

    # Publie par defaut : moderer a priori demanderait a l'equipe plateforme
    # de valider chaque avis, ce qu'aucune equipe ne tient dans la duree. Le
    # masquage reste possible a tout moment.
    status = models.CharField(
        _("statut"), max_length=12, choices=Status.choices, default=Status.PUBLISHED
    )

    class Meta:
        verbose_name = _("avis")
        verbose_name_plural = _("avis")
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["tenant", "status", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.author_name} — {self.rating}/5"

    def detail(self) -> list[dict]:
        """Les critères notés, dans l'ordre où ils ont été demandés.

        Les critères laissés vides sont écartés : afficher « Ponctualité — »
        sur une fiche d'avis fait chercher une note qui n'existe pas.
        """
        return [
            {"field": field, "label": str(label), "rating": getattr(self, field)}
            for field, label in self.CRITERIA
            if getattr(self, field) is not None
        ]
