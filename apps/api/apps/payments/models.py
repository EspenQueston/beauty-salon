"""Encaissement de l'acompte, par QR code et preuve de versement.

---------------------------------------------------------------------------
Pourquoi un QR code et pas une passerelle de paiement
---------------------------------------------------------------------------

Parce que c'est ainsi qu'on paie reellement sur les marches vises. En Chine,
WeChat Pay et Alipay se reglent en scannant le code du commercant depuis son
telephone ; a Brazzaville et Kinshasa, c'est Mobile Money par le meme geste.
Dans les trois cas l'argent va **directement** du telephone de la cliente au
compte du salon : la plateforme n'est jamais sur le chemin.

Cela a trois consequences qui structurent tout ce module :

  1. **Nous ne voyons pas le paiement.** Aucun webhook, aucune confirmation
     automatique. C'est la cliente qui dit avoir paye, et le salon qui
     verifie sur son propre telephone.
  2. **La preuve est une image.** Une capture d'ecran de l'application de
     paiement. Elle ne prouve rien cryptographiquement - elle sert a ce que
     le salon retrouve le versement dans son historique.
  3. **L'acceptation est humaine, et double.** Le salon confirme deux choses
     a la fois : qu'il a bien recu l'argent, et qu'il peut assurer la
     prestation. Les separer aurait produit des rendez-vous payes que
     personne ne peut honorer.

Ne pas encaisser nous-memes est ici un avantage, pas un pis-aller : aucune
licence d'etablissement de paiement, aucun fonds de tiers a detenir, aucun
remboursement a arbitrer. Le jour ou une passerelle sera branchee, ce module
restera valable pour les salons qui preferent l'espece et le QR.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import TenantOwnedModel


class PaymentChannel(TenantOwnedModel):
    """Un moyen d'encaisser l'acompte, avec le QR code du salon.

    Le modele porte un `kind` ouvert plutot que deux colonnes `wechat_qr` et
    `alipay_qr` : les salons de Brazzaville et Kinshasa encaissent par Mobile
    Money, et ils arriveront. Ajouter une valeur a une liste de choix coute
    une migration ; ajouter une colonne par pays en couterait une par pays.
    """

    class Kind(models.TextChoices):
        WECHAT = "wechat", _("WeChat Pay")
        ALIPAY = "alipay", _("Alipay")
        # Prevus, pas encore proposes a l'inscription : les salons chinois
        # sont les premiers servis.
        MOBILE_MONEY = "mobile_money", _("Mobile Money")
        AIRTEL_MONEY = "airtel_money", _("Airtel Money")
        ORANGE_MONEY = "orange_money", _("Orange Money")
        BANK = "bank", _("Virement bancaire")

    kind = models.CharField(_("moyen de paiement"), max_length=20, choices=Kind.choices)

    # Le QR code du salon, televerse par lui. Sans image, le moyen reste
    # affichable avec ses seules instructions - un numero Mobile Money se
    # compose a la main.
    qr_image = models.ForeignKey(
        "media.MediaAsset",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name=_("QR code"),
    )

    account_name = models.CharField(
        _("nom du compte"),
        max_length=150,
        blank=True,
        help_text=_("Ce que la cliente verra s'afficher en scannant."),
    )
    instructions = models.CharField(
        _("précision"),
        max_length=255,
        blank=True,
        help_text=_("« Mettez votre nom en commentaire », par exemple."),
    )

    active = models.BooleanField(_("proposé à la réservation"), default=True)
    position = models.PositiveSmallIntegerField(_("ordre d'affichage"), default=0)

    class Meta:
        verbose_name = _("moyen d'encaissement")
        verbose_name_plural = _("moyens d'encaissement")
        ordering = ("position", "kind")
        constraints = [
            # Un salon n'a qu'un compte WeChat. Deux lignes du meme moyen
            # laisseraient la cliente devant deux QR codes sans savoir lequel
            # scanner.
            models.UniqueConstraint(
                fields=("tenant", "kind"), name="unique_payment_channel_per_tenant"
            )
        ]

    def __str__(self) -> str:
        return self.get_kind_display()

    @property
    def usable(self) -> bool:
        """Affichable a la cliente : un QR, ou au moins une consigne.

        Un moyen active mais entierement vide ne serait qu'une impasse.
        """
        return self.active and bool(self.qr_image_id or self.instructions)


class DepositProof(TenantOwnedModel):
    """La capture d'ecran par laquelle la cliente dit avoir paye.

    Elle ne prouve rien en soi - une image se fabrique. Son role est de
    permettre au salon de **retrouver** le versement dans l'historique de son
    application de paiement : montant, heure, nom de l'emetteur.

    C'est pourquoi rien ici n'est automatique : l'etat du rendez-vous
    n'avance que lorsqu'une personne du salon a regarde son telephone et
    confirme.
    """

    class Status(models.TextChoices):
        SUBMITTED = "submitted", _("Envoyée, en attente de vérification")
        ACCEPTED = "accepted", _("Versement retrouvé")
        REJECTED = "rejected", _("Versement introuvable")

    booking = models.OneToOneField(
        "scheduling.Booking",
        on_delete=models.CASCADE,
        related_name="deposit_proof",
        verbose_name=_("rendez-vous"),
    )

    image = models.ForeignKey(
        "media.MediaAsset",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name=_("capture d'écran"),
    )
    channel = models.CharField(
        _("moyen utilisé"),
        max_length=20,
        choices=PaymentChannel.Kind.choices,
        blank=True,
    )
    reference = models.CharField(
        _("référence du versement"),
        max_length=120,
        blank=True,
        help_text=_("Numéro de transaction, si la cliente l'a noté."),
    )
    note = models.TextField(_("message de la cliente"), blank=True)

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.SUBMITTED
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name=_("vérifié par"),
    )
    rejection_reason = models.CharField(
        _("motif du refus"), max_length=255, blank=True
    )

    class Meta:
        verbose_name = _("preuve de versement")
        verbose_name_plural = _("preuves de versement")
        ordering = ("-submitted_at",)

    def __str__(self) -> str:
        return f"Acompte {self.get_status_display()}"
