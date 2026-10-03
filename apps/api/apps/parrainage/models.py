"""Le parrainage : un salon ou une cliente recommande la plateforme a un salon.

---------------------------------------------------------------------------
Les regles, decidees avec le produit (2026-09-28)
---------------------------------------------------------------------------

  - un code personnel par salon et par utilisateur, aleatoire, non devinable ;
  - un seul parrain par salon filleul, fige a l'inscription ;
  - le filleul devient **admissible** quand il est publie par
    l'administration depuis 14 jours (sans suspension a ce moment), ou des
    son premier paiement d'abonnement approuve ;
  - admissible, il donne a son parrain une **remise de 10 %** ;
  - un salon parrain recoit en plus 10 % a **chaque paiement approuve** du
    filleul, 12 au plus par filleul ; une cliente marraine, une seule fois ;
  - une remise s'applique a un paiement d'abonnement : celui du salon
    parrain, ou — pour une cliente — celui d'un salon qu'elle possede ;
  - 30 % au plus par paiement (trois remises), valables 12 mois ;
  - une remise n'est **jamais de l'argent** : ni retrait, ni portefeuille.

---------------------------------------------------------------------------
Pourquoi des tables de plateforme, sans RLS
---------------------------------------------------------------------------

Un parrainage relie deux comptes differents — deux salons, ou une cliente et
un salon. Aucun des deux ne « possede » la ligne : elle vit au niveau de la
plateforme, comme les domaines. Chaque vue filtre donc explicitement sur le
salon ou l'utilisateur courant, et n'expose du filleul que son nom public.

---------------------------------------------------------------------------
Pourquoi la remise est separee du paiement et de l'abonnement
---------------------------------------------------------------------------

Pour que chaque etape laisse une trace : quel evenement l'a creee
(`reference`, unique : un meme evenement ne cree jamais deux remises), quelle
demande de paiement l'a reservee, puis consommee, et combien elle a deduit.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _


class CodeParrainage(models.Model):
    """Le code personnel d'un salon ou d'un utilisateur, et lui seul."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(_("code"), max_length=16, unique=True)
    tenant = models.OneToOneField(
        "tenants.Tenant",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="code_parrainage",
        verbose_name=_("salon"),
    )
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="code_parrainage",
        verbose_name=_("utilisateur"),
    )
    actif = models.BooleanField(_("actif"), default=True)
    cree_le = models.DateTimeField(_("créé le"), auto_now_add=True)

    class Meta:
        verbose_name = _("code de parrainage")
        verbose_name_plural = _("codes de parrainage")
        constraints = [
            # Exactement un titulaire : un salon, ou un utilisateur.
            models.CheckConstraint(
                condition=(Q(tenant__isnull=False) & Q(user__isnull=True))
                | (Q(tenant__isnull=True) & Q(user__isnull=False)),
                name="code_parrainage_un_seul_titulaire",
            )
        ]

    def __str__(self) -> str:
        return self.code

    @property
    def type_parrain(self) -> str:
        return (
            Parrainage.TypeParrain.SALON if self.tenant_id else Parrainage.TypeParrain.UTILISATEUR
        )


class Parrainage(models.Model):
    """Un salon filleul et son parrain. Un seul par filleul, fige a l'inscription."""

    class TypeParrain(models.TextChoices):
        SALON = "salon", _("Salon")
        UTILISATEUR = "utilisateur", _("Utilisateur")

    class Statut(models.TextChoices):
        EN_VERIFICATION = "en_verification", _("En vérification")
        ADMISSIBLE = "admissible", _("Admissible")
        REFUSE = "refuse", _("Refusé")
        INVALIDE = "invalide", _("Invalidé")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    filleul = models.OneToOneField(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="parrainage_recu",
        verbose_name=_("salon filleul"),
    )
    # SET_NULL et non PROTECT : supprimer un salon parrain (et son code) ne
    # doit pas etre bloque par ses filleuls. Le parrain reste lisible plus bas.
    code = models.ForeignKey(
        CodeParrainage,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="parrainages",
        verbose_name=_("code utilisé"),
    )
    type_parrain = models.CharField(
        _("type de parrain"), max_length=12, choices=TypeParrain.choices
    )
    # Le parrain, retenu a l'inscription : un code desactive ou reattribue
    # plus tard ne change pas qui a parraine.
    parrain_tenant = models.ForeignKey(
        "tenants.Tenant",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="parrainages_donnes",
        verbose_name=_("salon parrain"),
    )
    parrain_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="parrainages_donnes",
        verbose_name=_("utilisateur parrain"),
    )
    statut = models.CharField(
        _("statut"), max_length=20, choices=Statut.choices, default=Statut.EN_VERIFICATION
    )
    motif = models.CharField(_("motif"), max_length=255, blank=True)
    # Trop de filleuls d'un meme parrain en peu de temps : l'admissibilite
    # attend une validation humaine.
    revue_requise = models.BooleanField(_("revue requise"), default=False)
    publie_le = models.DateTimeField(_("filleul publié le"), null=True, blank=True)
    admissible_le = models.DateTimeField(_("admissible le"), null=True, blank=True)
    # Empreintes (HMAC) : de quoi rapprocher des inscriptions sans garder
    # l'adresse IP ni les coordonnees en clair.
    empreinte_ip = models.CharField(max_length=64, blank=True)
    cree_le = models.DateTimeField(_("détecté le"), auto_now_add=True)
    maj_le = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("parrainage")
        verbose_name_plural = _("parrainages")
        ordering = ("-cree_le",)
        # Valider, invalider, annuler une remise : des gestes qui touchent a
        # des montants. Distincts de la simple lecture.
        permissions = [("corriger_parrainage", "Peut corriger les parrainages et leurs remises")]
        indexes = [models.Index(fields=["statut"])]

    def __str__(self) -> str:
        return f"{self.filleul} ← {self.code}"


class Remise(models.Model):
    """Un droit a reduction, jamais de l'argent. Suit son cycle jusqu'au bout."""

    class Statut(models.TextChoices):
        DISPONIBLE = "disponible", _("Disponible")
        RESERVEE = "reservee", _("Réservée")
        UTILISEE = "utilisee", _("Utilisée")
        EXPIREE = "expiree", _("Expirée")
        ANNULEE = "annulee", _("Annulée")

    class Declencheur(models.TextChoices):
        INSCRIPTION = "inscription", _("Inscription admissible du filleul")
        PAIEMENT = "paiement", _("Paiement approuvé du filleul")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # SET_NULL : la remise survit a la suppression du salon filleul, avec son
    # nom retenu, pour que le parrain garde l'historique de ce qu'il a obtenu.
    parrainage = models.ForeignKey(
        Parrainage, null=True, blank=True, on_delete=models.SET_NULL, related_name="remises"
    )
    filleul_nom = models.CharField(_("salon filleul"), max_length=120)
    beneficiaire_tenant = models.ForeignKey(
        "tenants.Tenant",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="remises_parrainage",
        verbose_name=_("salon bénéficiaire"),
    )
    beneficiaire_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="remises_parrainage",
        verbose_name=_("utilisateur bénéficiaire"),
    )
    declencheur = models.CharField(_("déclencheur"), max_length=12, choices=Declencheur.choices)
    # « inscription:<parrainage> » ou « paiement:<demande> » : unique en base,
    # c'est ce qui rend la creation idempotente.
    reference = models.CharField(_("référence de l'événement"), max_length=80, unique=True)
    pourcentage = models.DecimalField(_("pourcentage"), max_digits=5, decimal_places=2)
    statut = models.CharField(
        _("statut"), max_length=12, choices=Statut.choices, default=Statut.DISPONIBLE
    )
    expire_le = models.DateTimeField(_("expire le"))
    demande = models.ForeignKey(
        "billing.SubscriptionPaymentRequest",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="remises_parrainage",
        verbose_name=_("paiement concerné"),
    )
    montant_deduit = models.DecimalField(
        _("montant déduit"), max_digits=12, decimal_places=2, null=True, blank=True
    )
    devise = models.CharField(_("devise"), max_length=3, blank=True)
    utilisee_le = models.DateTimeField(_("utilisée le"), null=True, blank=True)
    annulee_le = models.DateTimeField(_("annulée le"), null=True, blank=True)
    motif = models.CharField(_("motif"), max_length=255, blank=True)
    cree_le = models.DateTimeField(_("créée le"), auto_now_add=True)
    maj_le = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("remise de parrainage")
        verbose_name_plural = _("remises de parrainage")
        ordering = ("expire_le",)
        indexes = [models.Index(fields=["statut", "expire_le"])]
        constraints = [
            models.CheckConstraint(
                condition=(Q(beneficiaire_tenant__isnull=False) & Q(beneficiaire_user__isnull=True))
                | (Q(beneficiaire_tenant__isnull=True) & Q(beneficiaire_user__isnull=False)),
                name="remise_un_seul_beneficiaire",
            ),
            models.CheckConstraint(
                condition=Q(pourcentage__gt=0) & Q(pourcentage__lte=100),
                name="remise_pourcentage_valide",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.pourcentage} % — {self.get_statut_display()}"
