"""Parrainages distincts :

Cas A : un client recommande un salon à un nouveau client ; une réservation
confirmée débloque une réduction dans ce salon, selon des conditions figées.
Cas B : un salon ou un client recommande la plateforme à un nouveau salon.
L'essai total est de 30 jours. Le premier abonnement payé crée, pour un
salon parrain, une réduction unique de 10 %, disponible après le cooling.
Les données A sont protégées par RLS ; les données B vivent au niveau
plateforme, avec filtrage explicite dans chaque API. Aucun portefeuille.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.common.models import TenantOwnedModel


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
    essai_debut = models.DateTimeField(null=True, blank=True)
    essai_fin = models.DateTimeField(null=True, blank=True)
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
        EN_ATTENTE = "en_attente", _("En attente du délai de sécurité")
        SUSPENDUE = "suspendue", _("Suspendue pour vérification")
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
    expire_le = models.DateTimeField(_("expire le"), null=True, blank=True)
    paiement_declencheur = models.ForeignKey(
        "billing.SubscriptionPaymentRequest",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="recompenses_declenchees",
    )
    paiement_confirme_le = models.DateTimeField(null=True, blank=True)
    disponible_le = models.DateTimeField(null=True, blank=True)
    conditions = models.JSONField(default=dict, blank=True)
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


class PolitiquePlateforme(models.Model):
    """Paramètres explicitement validés, sans valeurs commerciales inventées."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    active = models.BooleanField(default=False)
    cooling_jours = models.PositiveSmallIntegerField(null=True, blank=True)
    cooling_mode = models.CharField(
        max_length=20,
        default="demi_periode",
        choices=[("demi_periode", "Moitié de la période payée"), ("jours", "Nombre de jours")],
    )
    validite_jours = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1)]
    )
    validite_depuis_disponibilite = models.BooleanField(default=False)
    recompenses_max_par_parrain = models.PositiveIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1)]
    )
    remises_max_par_echeance = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1)]
    )
    reservation_heures = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1)]
    )
    apres_remboursement = models.CharField(
        max_length=20,
        blank=True,
        choices=[
            ("revue", "Suspendre et demander une décision"),
            ("maintenir", "Maintenir les récompenses disponibles/utilisées"),
        ],
    )

    class Meta:
        verbose_name = "politique de parrainage plateforme (Cas B)"
        verbose_name_plural = "politique de parrainage plateforme (Cas B)"

    def __str__(self):
        return "Cas B — paramètres plateforme"

    def clean(self):
        if self.pk != 1:
            raise ValidationError("Une seule politique plateforme est autorisée.")
        if self.active and (
            (self.cooling_mode == "jours" and not self.cooling_jours)
            or not self.validite_jours
            or not self.validite_depuis_disponibilite
            or not self.recompenses_max_par_parrain
            or self.remises_max_par_echeance != 1
            or not self.reservation_heures
            or self.apres_remboursement != "maintenir"
        ):
            raise ValidationError(
                "Complétez et validez tous les paramètres avant activation. "
                "Cette version accepte une remise de 10 % par échéance."
            )


class PolitiqueSalon(TenantOwnedModel):
    active = models.BooleanField(default=False)
    taux = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(10), MaxValueValidator(100)],
    )
    validite_jours = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1)]
    )
    plafond_montant = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    devise = models.CharField(max_length=3, blank=True)
    nature_plafond = models.CharField(
        max_length=30,
        blank=True,
        choices=[("montant_par_reservation", "Montant maximal de réduction par réservation")],
    )
    reservations_annulees_excluent = models.BooleanField(null=True, blank=True)
    attribution = models.CharField(
        max_length=20, blank=True, choices=[("premier_code", "Premier code valide")]
    )
    formule = models.CharField(
        max_length=40,
        blank=True,
        choices=[("apres_promotions_prestation", "Après promotions, prestation et options")],
    )
    recompenses_par_reservation = models.PositiveSmallIntegerField(null=True, blank=True)
    annulation_declencheur = models.CharField(
        max_length=20,
        blank=True,
        choices=[("revue", "Suspendre pour décision"), ("maintenir", "Maintenir")],
    )
    annulation_utilisation = models.CharField(
        max_length=20,
        blank=True,
        choices=[
            ("revue", "Suspendre pour décision"),
            ("restituer", "Restituer si encore valide"),
            ("maintenir", "Maintenir la consommation"),
        ],
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tenant"], name="politique_parrainage_salon_unique")
        ]
        verbose_name = "politique de parrainage salon (Cas A)"
        verbose_name_plural = "politiques de parrainage des salons (Cas A)"

    def __str__(self):
        return f"Cas A — {self.tenant}"

    def clean(self):
        if self.active and (
            self.taux is None
            or not 10 <= self.taux <= 100
            or not self.validite_jours
            or not self.plafond_montant
            or not self.devise
            or self.nature_plafond != "montant_par_reservation"
            or self.reservations_annulees_excluent is not True
            or not self.attribution
            or not self.formule
            or self.recompenses_par_reservation != 1
            or self.annulation_declencheur != "maintenir"
            or self.annulation_utilisation != "restituer"
        ):
            raise ValidationError(
                "Configuration incomplète : taux (10 % minimum), durée, "
                "plafond monétaire et politiques validées sont obligatoires."
            )
        if (
            self.active
            and self.devise in {"XAF", "XOF", "CDF"}
            and self.plafond_montant != self.plafond_montant.to_integral_value()
        ):
            raise ValidationError("Le plafond doit être un montant entier dans cette devise.")


class CodeClientSalon(TenantOwnedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    code = models.CharField(max_length=16, unique=True)
    actif = models.BooleanField(default=True)

    class Meta:
        verbose_name = "code de parrainage client"
        verbose_name_plural = "codes de parrainage clients (Cas A)"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "user"], name="code_client_salon_unique")
        ]

    def __str__(self):
        return self.code


class RecompenseClient(TenantOwnedModel):
    class Statut(models.TextChoices):
        EN_ATTENTE = "en_attente", "Première réservation à confirmer"
        DISPONIBLE = "disponible", "Disponible"
        RESERVEE = "reservee", "Réservée"
        UTILISEE = "utilisee", "Utilisée"
        ANNULEE = "annulee", "Annulée"
        EXPIREE = "expiree", "Expirée"
        SUSPENDUE = "suspendue", "À vérifier"

    parrain = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recompenses_clients",
    )
    filleul = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="parrainages_clients_recus",
    )
    identite_filleul = models.CharField(max_length=64)
    declencheur = models.OneToOneField(
        "scheduling.Booking", on_delete=models.PROTECT, related_name="parrainage_client"
    )
    utilisation = models.OneToOneField(
        "scheduling.Booking",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reduction_parrainage_client",
    )
    taux = models.DecimalField(max_digits=5, decimal_places=2)
    plafond_montant = models.DecimalField(max_digits=12, decimal_places=2)
    devise = models.CharField(max_length=3)
    conditions = models.JSONField(default=dict)
    statut = models.CharField(max_length=12, choices=Statut.choices, default=Statut.EN_ATTENTE)
    disponible_le = models.DateTimeField(null=True, blank=True)
    expire_le = models.DateTimeField(null=True, blank=True)
    montant_deduit = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    class Meta:
        verbose_name = "récompense client"
        verbose_name_plural = "récompenses clients (Cas A)"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "identite_filleul"], name="premier_parrainage_client_salon"
            )
        ]
        indexes = [models.Index(fields=["tenant", "parrain", "statut"])]

    def __str__(self):
        return f"{self.taux} % — {self.get_statut_display()}"


class EvenementParrainage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cas = models.CharField(max_length=1, choices=[("A", "Client vers client"), ("B", "Vers salon")])
    tenant = models.ForeignKey("tenants.Tenant", null=True, on_delete=models.SET_NULL)
    ressource = models.UUIDField()
    action = models.CharField(max_length=40)
    details = models.JSONField(default=dict)
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "événement de parrainage"
        verbose_name_plural = "journal du parrainage (Cas A/B)"
        ordering = ["-cree_le"]
        indexes = [models.Index(fields=["cas", "ressource", "cree_le"])]

    def __str__(self):
        return f"{self.cas} — {self.action} — {self.ressource}"
