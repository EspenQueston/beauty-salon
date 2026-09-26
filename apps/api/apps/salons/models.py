"""Vitrine publique et reglages operationnels du salon."""

from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import TenantOwnedModel


class ServiceMode(models.TextChoices):
    SALON = "salon", _("Au salon")
    HOME = "home", _("À domicile")
    HYBRID = "hybrid", _("Les deux")


class SalonProfile(TenantOwnedModel):
    """Contenu du mini-site et parametres de reservation.

    Une seule fiche par salon (contrainte d'unicite sur tenant). Le
    ThemeConfig est un JSON libre cote base mais valide cote serializer :
    le salon personnalise son apparence, pas la structure du produit.
    """

    description = models.TextField(_("présentation"), blank=True)
    address = models.CharField(_("adresse"), max_length=255, blank=True)
    city = models.CharField(_("ville"), max_length=120, blank=True)
    service_mode = models.CharField(
        max_length=10, choices=ServiceMode.choices, default=ServiceMode.SALON
    )

    # ----- ou le salon se deplace ------------------------------------------
    # Texte libre plutot qu'une liste fermee : les decoupages administratifs
    # ne correspondent nulle part a la maniere dont les gens nomment leur
    # quartier, et « Bacongo, Makelekele, Moungali » se comprend des deux
    # cotes sans qu'on ait a modeliser la geographie de trois pays.
    service_area = models.CharField(
        _("zone desservie"),
        max_length=255,
        blank=True,
        help_text=_("Les quartiers où vous vous déplacez, séparés par des virgules."),
    )

    # Coordonnees facultatives, posees a la main par le salon.
    #
    # Sans elles, l'itineraire passe par une recherche textuelle de l'adresse,
    # ce qui suffit en centre-ville et echoue des qu'on s'en eloigne : dans
    # une bonne partie de Brazzaville ou de Kinshasa, aucune adresse postale
    # n'est indexee. Un point pose a la main est alors la seule donnee juste.
    #
    # Elles ne servent qu'a ouvrir la bonne carte : rien n'est facture au
    # kilometre a partir d'elles, la tarification passe par les zones.
    latitude = models.DecimalField(
        _("latitude"),
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        validators=[MinValueValidator(-90), MaxValueValidator(90)],
    )
    longitude = models.DecimalField(
        _("longitude"),
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        validators=[MinValueValidator(-180), MaxValueValidator(180)],
    )

    phone = models.CharField(_("téléphone"), max_length=32, blank=True)
    whatsapp_number = models.CharField(_("numéro WhatsApp"), max_length=32, blank=True)
    # L'adresse publiee sur le mini-site, distincte de celle du compte : un
    # salon ne veut pas forcement exposer l'adresse avec laquelle il se
    # connecte. Vide tant qu'il ne l'a pas renseignee — rien n'est publie a
    # sa place.
    contact_email = models.EmailField(_("e-mail de contact"), blank=True)
    # {"instagram": "...", "tiktok": "...", "wechat": "...", "facebook": "..."}
    social_links = models.JSONField(default=dict, blank=True)

    # ----- WeChat --------------------------------------------------------
    #
    # Pourquoi deux colonnes plutot qu'une entree de plus dans `social_links`
    # -------------------------------------------------------------------
    #
    # Parce que WeChat ne s'ajoute pas par une adresse. Les autres reseaux se
    # partagent par un lien qu'on ouvre ; WeChat se rejoint en scannant un QR
    # ou en tapant un identifiant dans la barre de recherche. Ranger l'un des
    # deux sous une cle « wechat » a cote d'URL Instagram donnerait un bouton
    # qui ne mene nulle part - et c'est exactement ce qui se passait.
    #
    # Les deux sont montres ensemble, jamais l'un a la place de l'autre : le
    # QR sert quand on lit la page sur un ordinateur ou une affichette, et
    # l'identifiant sert quand on lit la page *dans* WeChat, ou l'on ne peut
    # pas scanner son propre ecran.
    #
    # A ne pas confondre avec le QR de `PaymentChannel` : celui-la encaisse
    # un acompte, celui-ci ajoute le salon en contact. Les afficher au meme
    # endroit ferait payer une cliente qui voulait poser une question.
    wechat_id = models.CharField(
        _("identifiant WeChat"),
        max_length=64,
        blank=True,
        help_text=_("Le numero WeChat du salon, tel qu'on le tape pour le chercher."),
    )
    wechat_qr = models.ForeignKey(
        "media.MediaAsset",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name=_("QR code WeChat"),
        help_text=_("Le code a scanner pour ajouter le salon en contact."),
    )

    # {"primary": "#8B5CF6", "accent": "...", "font": "...", "radius": "..."}
    theme_config = models.JSONField(default=dict, blank=True)
    # Personnalisation avancee (offre Pro) : polices, menu, ordre des sections
    # de l'accueil, accroche. Validee par `personnalisation.valider` — jamais
    # de HTML, de CSS ni de script. Conservee sans Pro, mais le mini-site ne
    # l'applique que si le salon a la fonction.
    site_config = models.JSONField(default=dict, blank=True)

    logo = models.ForeignKey(
        "media.MediaAsset",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    banner = models.ForeignKey(
        "media.MediaAsset",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    # ----- page « A propos » -----------------------------------------------
    # Le champ `description` du haut de page tient en trois lignes : c'est
    # une accroche. Un salon qui existe depuis quinze ans a une histoire plus
    # longue a raconter, et c'est souvent elle qui decide une nouvelle
    # cliente. Elle a donc sa propre page, et le salon la redige lui-meme.
    about_title = models.CharField(_("titre de la page À propos"), max_length=120, blank=True)
    about_content = models.TextField(_("texte de la page À propos"), blank=True)
    about_image = models.ForeignKey(
        "media.MediaAsset",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name=_("photo de la page À propos"),
    )

    cancellation_policy = models.TextField(_("politique d'annulation"), blank=True)
    # Delai minimal avant annulation sans penalite, en heures.
    cancellation_deadline_hours = models.PositiveSmallIntegerField(
        _("annulation gratuite jusqu'à (heures avant)"), default=24
    )

    # ----- acompte ----------------------------------------------------------
    #
    # Comment l'acompte se calcule, et pourquoi ainsi.
    #
    # Un montant fixe par prestation protegeait de moins en moins a mesure
    # que le panier grossissait : 150 sur 450 font 33 %, les memes 150 sur
    # 690 n'en font plus que 22 - alors qu'un rendez-vous a 690 qui ne vient
    # pas coute *davantage*.
    #
    # La regle retenue distingue deux natures de montant :
    #
    #   - **le temps** (prestation + options) est reserve a un pourcentage.
    #     Un creneau libere assez tot peut etre repris : le salon ne perd
    #     pas tout, l'acompte n'a donc pas a tout couvrir.
    #   - **la marchandise** (articles de la boutique) est reglee en entier.
    #     Des meches achetees pour une cliente precise ne se revendent pas
    #     toujours, et le salon les a deja payees. Ce n'est pas une severite :
    #     c'est ce que fait tout commercant sur une commande speciale.
    #
    # Le « combien » vit ici, et **seulement** ici.
    #
    # Chaque prestation portait autrefois son propre montant d'acompte, qui
    # servait a la fois d'interrupteur et de plancher. Deux reglages pour une
    # meme notion, a deux endroits, avec une consequence visible par les
    # clientes : la fiche annoncait « acompte de 5 000 » et la reservation en
    # reclamait 7 500, parce que le pourcentage l'emportait sur le montant
    # affiche.
    #
    # La fiche de la prestation ne dit donc plus que « oui » ou « non ». Le
    # taux et le plancher sont ici, ensemble, et tout l'ecran les lit.
    deposit_rate = models.PositiveSmallIntegerField(
        _("acompte demandé (%)"),
        default=0,
        validators=[MaxValueValidator(100)],
        help_text=_("Part de la prestation et des options demandée à la réservation."),
    )
    deposit_minimum = models.DecimalField(
        _("acompte minimum"),
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
        help_text=_(
            "Plancher, quel que soit le pourcentage. Utile sur les petites "
            "prestations, où un pourcentage ne couvre pas le créneau perdu."
        ),
    )
    deposit_covers_items = models.BooleanField(
        _("faire régler les fournitures en entier"),
        default=True,
        help_text=_(
            "Les articles de votre boutique sont payés d'avance : vous les avez déjà achetés."
        ),
    )

    # ----- retard -----------------------------------------------------------
    # Le retard est le premier motif de friction en salon, et le seul qui se
    # regle entierement en le disant a l'avance. Une cliente qui sait qu'au
    # dela de quinze minutes son creneau saute arrive a l'heure ; une cliente
    # qui l'apprend sur place se sent flouee, et le salon perd les deux.
    #
    # Deux champs plutot qu'un : la tolerance est un nombre, donc l'agenda
    # peut s'en servir pour signaler un rendez-vous en retard. Le texte, lui,
    # dit ce qu'il se passe ensuite - report, acompte perdu, prestation
    # raccourcie - et cela, aucun salon ne le regle pareil.
    late_tolerance_minutes = models.PositiveSmallIntegerField(
        _("tolérance de retard (minutes)"),
        default=15,
        help_text=_("Au-delà de ce délai, l'agenda signale le rendez-vous comme en retard."),
    )
    late_policy = models.TextField(
        _("politique de retard"),
        blank=True,
        help_text=_(
            "Ce qu'il advient d'un rendez-vous au-delà de la tolérance. "
            "Affiché sur votre mini-site et rappelé dans l'e-mail de confirmation."
        ),
    )

    # ----- parametres du moteur de creneaux --------------------------------
    # Pas d'affichage des creneaux proposes a la cliente.
    slot_granularity_minutes = models.PositiveSmallIntegerField(
        default=15, validators=[MinValueValidator(5), MaxValueValidator(120)]
    )
    # Temps de remise en etat ajoute apres chaque prestation.
    buffer_minutes = models.PositiveSmallIntegerField(
        default=0, validators=[MaxValueValidator(240)]
    )
    # Delai minimal entre la reservation et le rendez-vous.
    min_lead_time_minutes = models.PositiveSmallIntegerField(
        default=120,
        # Sept jours au plus. Au-dela, le delai d'attente depasserait la
        # fenetre de reservation elle-meme et *aucun* creneau ne serait
        # jamais proposé - une panne silencieuse que personne ne sait
        # diagnostiquer depuis l'ecran.
        validators=[MaxValueValidator(60 * 24 * 7)],
    )
    # Horizon de reservation ouvert a la clientele.
    max_advance_days = models.PositiveSmallIntegerField(
        default=30,
        # Trente jours, pas davantage.
        #
        # Ce n'est pas une limite technique : c'est que personne ne sait dire
        # en janvier de quoi sera fait son mois de mai. Un agenda ouvert sur
        # un an se remplit de rendez-vous qui seront deplaces ou oublies, et
        # chacun bloque un creneau que quelqu'un d'autre aurait pris.
        validators=[MinValueValidator(1), MaxValueValidator(30)],
    )

    class Meta:
        verbose_name = _("profil de salon")
        verbose_name_plural = _("profils de salon")
        constraints = [models.UniqueConstraint(fields=["tenant"], name="one_profile_per_tenant")]

    def __str__(self) -> str:
        return f"Profil de {self.tenant_id}"


class TravelZone(TenantOwnedModel):
    """Un quartier desservi et son forfait de deplacement.

    ---------------------------------------------------------------------
    Pourquoi un forfait par quartier, et pas un tarif au kilometre
    ---------------------------------------------------------------------

    Facturer la distance suppose deux adresses geocodables. Sur les marches
    vises, l'adresse de la cliente n'en est pas une : on se repere par
    quartier et par point de reference, pas par numero de rue. Un calcul au
    kilometre produirait donc des montants faux avec l'apparence de la
    precision - le pire des deux mondes.

    Le forfait par quartier, lui, est la grille que le salon utilise deja
    au telephone. La cliente reconnait son quartier, voit le montant avant
    de confirmer, et personne n'a de surprise a l'arrivee.
    """

    name = models.CharField(_("quartier ou zone"), max_length=120)
    fee_amount = models.DecimalField(
        _("frais de déplacement"),
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
        help_text=_("0 pour une zone desservie gratuitement."),
    )
    position = models.PositiveSmallIntegerField(_("ordre d'affichage"), default=0)
    active = models.BooleanField(_("proposée à la réservation"), default=True)

    class Meta:
        verbose_name = _("zone de déplacement")
        verbose_name_plural = _("zones de déplacement")
        ordering = ("position", "name")
        constraints = [
            # Deux zones du meme nom rendraient le choix de la cliente
            # ambigu, et le salon ne saurait pas laquelle il a tarifee.
            models.UniqueConstraint(fields=("tenant", "name"), name="unique_travel_zone_per_tenant")
        ]

    def __str__(self) -> str:
        return self.name
