"""Ce que la plateforme a a dire, et a qui.

---------------------------------------------------------------------------
Trois tables, et pourquoi elles ne peuvent pas n'en faire qu'une
---------------------------------------------------------------------------

`Notification` appartient a un salon. C'est une donnee metier comme une
reservation : elle nomme une cliente, un montant, un creneau. Elle herite
donc de TenantOwnedModel et porte une politique RLS, au meme titre que le
reste. Une requete mal ecrite ne peut pas montrer les notifications d'un
salon a un autre, meme si le filtre applicatif saute.

`PlatformNotification` n'appartient a aucun salon : elle parle *des* salons
a qui exploite la plateforme (« un salon vient de s'inscrire », « une
facture est impayee »). Lui poser une politique tenant la rendrait invisible
a son seul lecteur, qui travaille precisement hors contexte tenant. Elle
reste donc hors RLS, et son controle d'acces est applicatif : `is_staff`.

`PushSubscription` appartient a une **personne**, pas a un salon. La meme
gerante peut tenir deux salons depuis le meme telephone : un abonnement par
salon ferait sonner l'appareil deux fois pour un seul evenement, et le
couperait pour les deux le jour ou elle quitte un salon. L'appareil est
rattache au compte, et c'est le contenu qui dit de quel salon il s'agit.

---------------------------------------------------------------------------
Pourquoi la notification est stockee, et pas seulement poussee
---------------------------------------------------------------------------

Un push n'arrive pas toujours : permission refusee, telephone eteint depuis
trois jours, navigateur qui a mis l'abonnement a la poubelle. Si l'envoi
etait le seul support, l'information disparaitrait sans que personne ne le
sache — et c'est le genre de perte qu'on ne decouvre qu'en perdant une
cliente.

La ligne en base est donc la source de verite, et le push n'en est qu'un
rappel. La cloche affiche ce que la base contient, que le push soit passe ou
non.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.common.models import TenantOwnedModel, TimeStampedModel, UUIDModel


class Genre(models.TextChoices):
    """Ce dont il est question.

    Le genre porte le sens ; le titre et le corps ne portent que les mots.
    C'est lui qui choisit l'icone et la couleur cote navigateur, et c'est lui
    qu'on filtre le jour ou quelqu'un voudra couper une categorie.

    Les valeurs sont figees : elles sont ecrites en base et relues par le
    frontend. En renommer une casse l'affichage des lignes deja enregistrees.
    """

    # --- Salon -------------------------------------------------------------
    RESERVATION = "reservation", _("Nouvelle demande")
    ACOMPTE_A_VERIFIER = "acompte_a_verifier", _("Acompte à vérifier")
    ACOMPTE_EXPIRE = "acompte_expire", _("Acompte non réglé")
    ANNULATION = "annulation", _("Rendez-vous annulé")
    AVIS = "avis", _("Nouvel avis")
    LISTE_ATTENTE = "liste_attente", _("Liste d'attente")

    # --- Plateforme --------------------------------------------------------
    SALON_INSCRIT = "salon_inscrit", _("Nouveau salon")
    FACTURE = "facture", _("Facturation")
    INCIDENT = "incident", _("Incident")


class BaseNotification(UUIDModel, TimeStampedModel):
    """Le tronc commun des deux familles.

    Abstrait : il ne cree pas de table. Les deux modeles concrets different
    par leur rattachement — salon ou plateforme —, pas par leur forme.
    """

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="%(class)ss",
        verbose_name=_("destinataire"),
    )
    genre = models.CharField(
        _("genre"), max_length=32, choices=Genre.choices, db_index=True
    )
    titre = models.CharField(_("titre"), max_length=120)
    corps = models.CharField(_("détail"), max_length=300, blank=True)

    # Chemin relatif, jamais une URL absolue : la meme notification est lue
    # dans le navigateur et depuis une notification systeme, sur deux hotes
    # differents (le tableau de bord et l'administration). C'est au moment de
    # l'affichage qu'on sait sur lequel on se trouve.
    lien = models.CharField(_("lien"), max_length=200, blank=True)

    lu_le = models.DateTimeField(_("lu le"), null=True, blank=True)

    class Meta:
        abstract = True
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.get_genre_display()} — {self.titre}"

    @property
    def lue(self) -> bool:
        return self.lu_le is not None

    def marquer_lue(self) -> bool:
        """Rend True si l'appel a change quelque chose.

        Relire deux fois n'est pas une erreur, mais ce n'est pas non plus un
        evenement : sans ce test, chaque ouverture du panneau ecrirait autant
        de lignes qu'il en affiche.
        """
        if self.lu_le is not None:
            return False
        self.lu_le = timezone.now()
        self.save(update_fields=["lu_le", "updated_at"])
        return True


class Notification(TenantOwnedModel, BaseNotification):
    """Ce qu'un salon doit savoir.

    L'ordre des parents compte : TenantOwnedModel doit venir en premier pour
    que son `objects` filtre reste le gestionnaire par defaut. Herite dans
    l'autre sens, l'admin et les relations basculeraient sur le manager non
    filtre.
    """

    class Meta(BaseNotification.Meta):
        abstract = False
        verbose_name = _("notification de salon")
        verbose_name_plural = _("notifications de salon")
        indexes = [
            # La requete de la cloche : « mes non-lues, dans ce salon, les
            # plus recentes d'abord ». Sans cet index elle parcourt la table
            # entiere a chaque ouverture du tableau de bord.
            models.Index(
                fields=["tenant", "recipient", "-created_at"],
                name="notif_salon_boite_idx",
            ),
        ]


class PlatformNotification(BaseNotification):
    """Ce que la plateforme doit savoir de ses salons.

    Le salon concerne est une simple reference, pas un rattachement : cette
    ligne ne lui appartient pas et il ne doit jamais la voir. Elle peut
    d'ailleurs etre vide — une panne d'envoi d'e-mail ne concerne personne en
    particulier.

    `SET_NULL` et non `CASCADE` : le jour ou un salon est supprime, la trace
    de son passage a la plateforme reste. C'est souvent le moment ou l'on
    veut la relire.
    """

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="platform_notifications",
        verbose_name=_("salon concerné"),
    )

    class Meta(BaseNotification.Meta):
        abstract = False
        verbose_name = _("notification plateforme")
        verbose_name_plural = _("notifications plateforme")
        indexes = [
            models.Index(
                fields=["recipient", "-created_at"], name="notif_plateforme_boite_idx"
            ),
        ]


class PushSubscription(UUIDModel, TimeStampedModel):
    """Un appareil qui a accepte d'etre prevenu.

    -----------------------------------------------------------------------
    Ce que contient vraiment une ligne
    -----------------------------------------------------------------------

    `endpoint` est une URL chez Google, Mozilla ou Apple, propre a ce
    navigateur. `cle_p256dh` et `cle_auth` sont les deux cles publiques que
    le navigateur nous confie pour qu'on chiffre le message *avant* de le
    remettre a ces services : ni Google ni personne d'autre ne lit le contenu
    d'une notification. C'est la norme qui l'impose, pas une precaution
    maison.

    -----------------------------------------------------------------------
    Pourquoi l'endpoint est unique
    -----------------------------------------------------------------------

    Il designe un navigateur, pas un compte. Sur un poste partage a
    l'accueil, la derniere personne qui accepte reprend l'abonnement a son
    nom. C'est le sens le plus sur : les notifications suivent qui vient de
    dire oui, et jamais la personne partie avant.
    """

    class Portee(models.TextChoices):
        """De quel site vient cet abonnement.

        Le tableau de bord et l'administration plateforme sont deux sites
        differents pour le navigateur : deux service workers, deux
        abonnements, deux boites aux lettres. Une meme personne peut tenir
        les deux.

        Sans cette distinction, une notification de salon serait poussee
        aussi sur l'abonnement de l'administration — ou son lien
        `/agenda` ne mene nulle part. On ne pousse donc jamais qu'aux
        appareils de la bonne portee.
        """

        SALON = "salon", _("Tableau de bord")
        PLATEFORME = "plateforme", _("Administration")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="push_subscriptions",
        verbose_name=_("compte"),
    )
    portee = models.CharField(
        _("portée"),
        max_length=12,
        choices=Portee.choices,
        default=Portee.SALON,
        db_index=True,
    )

    # Pas de max_length : certains endpoints depassent largement 255
    # caracteres, et un TextField unique s'indexe tres bien sous PostgreSQL.
    endpoint = models.TextField(_("adresse de remise"), unique=True)
    cle_p256dh = models.CharField(_("clé p256dh"), max_length=200)
    cle_auth = models.CharField(_("clé auth"), max_length=100)

    # Pour que quelqu'un puisse reconnaitre l'appareil qu'il revoque :
    # « Chrome sur Android » se lit, une chaine d'agent utilisateur non.
    appareil = models.CharField(_("appareil"), max_length=80, blank=True)

    derniere_reussite = models.DateTimeField(
        _("dernier envoi réussi"), null=True, blank=True
    )
    echecs = models.PositiveSmallIntegerField(_("échecs consécutifs"), default=0)

    class Meta:
        verbose_name = _("appareil abonné")
        verbose_name_plural = _("appareils abonnés")
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["user", "portee"], name="push_par_compte_idx")
        ]

    def __str__(self) -> str:
        return f"{self.appareil or 'Appareil'} — {self.user}"
