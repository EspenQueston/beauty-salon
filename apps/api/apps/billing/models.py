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

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.common.models import TenantOwnedModel, TimeStampedModel, UUIDModel

# Les devises dans lesquelles un abonnement se paie. Le yuan est la devise de
# reference (99 / 999) ; les trois autres n'ont de prix que celui qu'un
# administrateur a saisi — jamais un montant deduit d'un taux de change.
DEVISES_ABONNEMENT = [
    ("CNY", _("Yuan (CNY)")),
    ("USD", _("Dollar américain (USD)")),
    ("CDF", _("Franc congolais (CDF)")),
    ("XAF", _("Franc CFA (XAF)")),
]


class Plan(UUIDModel, TimeStampedModel):
    """Offre commerciale.

    Table plateforme : les offres sont communes a tous les salons.

    Deux offres payantes seulement, `monthly` et `yearly` : la meme
    plateforme, reglee au mois ou a l'annee. Leur prix par devise vit dans
    `PlanPrice`. Les offres Solo, Salon et Pro des debuts restent en base,
    desactivees : des abonnements anciens les referencent, et un historique
    ne se reecrit pas.
    """

    class Code(models.TextChoices):
        TRIAL = "trial", _("Essai")
        SOLO = "solo", _("Solo")
        SALON = "salon", _("Salon")
        PRO = "pro", _("Pro")
        MONTHLY = "monthly", _("Mensuel")
        YEARLY = "yearly", _("Annuel")

    code = models.CharField(max_length=20, choices=Code.choices, unique=True)
    name = models.CharField(max_length=80)
    description = models.TextField(blank=True)

    # Ce que l'offre achete : un mois ou douze. Zero pour l'essai, qui ne se
    # paie pas et ne s'achete pas.
    billing_months = models.PositiveSmallIntegerField(_("durée payée (mois)"), default=0)

    # Bornes fonctionnelles de l'offre. `None` vaut « sans limite ».
    max_staff = models.PositiveSmallIntegerField(null=True, blank=True)
    allows_custom_domain = models.BooleanField(default=False)

    # Tarif indicatif, en francs CFA, a titre de reference interne.
    reference_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
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
        # Periode (essai ou payee) terminee, sans renouvellement.
        EXPIRED = "expired", _("Expiré")
        # Periode terminee, et un paiement attend d'etre verifie. L'acces
        # n'en depend pas : seule l'approbation ouvre une periode.
        PENDING_PAYMENT = "pending_payment", _("Paiement en vérification")
        # Decision de l'equipe plateforme, independante des dates.
        SUSPENDED = "suspended", _("Suspendu")
        # Ancien statut du cycle a terme echu, conserve pour les lignes
        # existantes ; plus aucun abonnement n'y entre.
        PAST_DUE = "past_due", _("Impayé")
        CANCELLED = "cancelled", _("Résilié")

    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.TRIALING)

    price_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    currency = models.CharField(max_length=3, default="XAF")

    trial_ends_at = models.DateTimeField(null=True, blank=True)
    current_period_start = models.DateTimeField(default=timezone.now)
    current_period_end = models.DateTimeField()
    cancelled_at = models.DateTimeField(null=True, blank=True)

    # Frais de mise en route du document : ponctuels, distincts du mensuel.
    setup_fee_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    setup_fee_paid = models.BooleanField(default=False)

    notes = models.TextField(blank=True)

    # Point de depart de la suite de periodes payees en cours, et nombre de
    # mois qu'elle couvre. C'est ce qui garde le jour d'echeance : payer le
    # 31 janvier donne le 28 (ou 29) fevrier, puis le 31 mars — et non le
    # 28 mars, comme le ferait un mois ajoute a la fin precedente. Voir
    # `services.ajouter_mois`.
    period_anchor = models.DateTimeField(null=True, blank=True)
    anchor_months = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = _("abonnement")
        verbose_name_plural = _("abonnements")
        constraints = [
            models.UniqueConstraint(fields=["tenant"], name="one_subscription_per_tenant")
        ]
        permissions = [
            (
                "manage_subscription_manually",
                "Peut prolonger, suspendre ou réactiver un abonnement à la main",
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
        WECHAT = "wechat", _("WeChat Pay")
        ALIPAY = "alipay", _("Alipay")
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

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ISSUED)
    issued_at = models.DateTimeField(default=timezone.now)
    due_at = models.DateTimeField()
    paid_at = models.DateTimeField(null=True, blank=True)
    payment_method = models.CharField(max_length=20, choices=Method.choices, blank=True)
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


# ---------------------------------------------------------------------------
# Tarifs et moyens de reglement : reglages de la plateforme
# ---------------------------------------------------------------------------
#
# Deux tables sans salon, donc sans politique RLS : ce sont des catalogues
# communs, lus par tous les salons et ecrits par l'administration seule. Rien
# de ce qui s'y trouve — prix, numeros, QR codes — n'est ecrit en dur dans le
# frontend : il les lit ici, et un changement de numero Mobile Money ne
# demande aucun deploiement.


class PlanPrice(UUIDModel, TimeStampedModel):
    """Le prix d'une offre dans une devise.

    Un prix par devise, saisi par un administrateur. Une devise sans prix
    n'est tout simplement pas proposee : on ne devine pas 99 CNY en francs
    CFA au taux du jour, parce qu'un tarif affiche engage la plateforme et
    qu'un taux mal choisi ne se rattrape pas.
    """

    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="prices")
    currency = models.CharField(_("devise"), max_length=3, choices=DEVISES_ABONNEMENT)
    amount = models.DecimalField(
        _("montant"),
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    active = models.BooleanField(_("proposé"), default=True)

    class Meta:
        verbose_name = _("tarif d'abonnement")
        verbose_name_plural = _("tarifs d'abonnement")
        ordering = ("plan__position", "currency")
        constraints = [
            models.UniqueConstraint(
                fields=["plan", "currency"], name="un_tarif_par_offre_et_devise"
            ),
            models.CheckConstraint(condition=Q(amount__gt=0), name="tarif_strictement_positif"),
        ]

    def __str__(self) -> str:
        return f"{self.plan.name} — {self.amount} {self.currency}"


def chemin_qr(instance, filename: str) -> str:
    """Rangement d'un QR code de la plateforme.

    Sous `prive/` : le serveur de fichiers statiques ne le sert pas. Il ne
    sort que par la route authentifiee des proprietaires de salon, et par
    l'administration. Le nom est tire au hasard : il ne dit rien du compte.
    """
    import os
    import uuid

    # L'extension decide du type sous lequel le fichier sera servi : elle
    # n'est jamais reprise telle quelle du nom televerse.
    extension = os.path.splitext(filename)[1].lower()
    if extension not in QR_EXTENSIONS:
        extension = ".png"
    return f"prive/plateforme/qr/{uuid.uuid4().hex}{extension}"


# Les seules extensions sous lesquelles un QR code est range, et le type
# sous lequel chacune est servie.
QR_EXTENSIONS = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def type_du_qr(nom: str) -> str:
    """Le type d'un QR range : tire de la liste, jamais devine."""
    import os

    return QR_EXTENSIONS.get(os.path.splitext(nom)[1].lower(), "image/png")


class PlatformPaymentMethod(UUIDModel, TimeStampedModel):
    """Un compte sur lequel les salons reglent leur abonnement.

    WeChat Pay et Alipay se reglent en scannant un QR code ; Mobile Money,
    en envoyant l'argent a un numero. Un meme modele pour les trois, parce
    que la regle d'affichage est la meme : un moyen n'est propose que s'il
    est actif, complet, et accorde au pays et a la devise que le salon a
    choisis.
    """

    class Kind(models.TextChoices):
        WECHAT = "wechat", _("WeChat Pay")
        ALIPAY = "alipay", _("Alipay")
        MOBILE_MONEY = "mobile_money", _("Mobile Money")

    QR_KINDS = (Kind.WECHAT, Kind.ALIPAY)

    kind = models.CharField(_("moyen"), max_length=20, choices=Kind.choices)
    provider_name = models.CharField(
        _("opérateur"),
        max_length=80,
        blank=True,
        help_text=_("Obligatoire pour Mobile Money : MTN MoMo, Airtel Money, M-Pesa…"),
    )
    country = models.CharField(_("pays"), max_length=2)
    currency = models.CharField(_("devise"), max_length=3, choices=DEVISES_ABONNEMENT)

    account_number = models.CharField(
        _("numéro de téléphone ou de compte"), max_length=60, blank=True
    )
    account_holder = models.CharField(_("titulaire du compte"), max_length=120, blank=True)
    qr_image = models.ImageField(_("QR code"), upload_to=chemin_qr, blank=True, max_length=255)
    instructions = models.TextField(_("instructions"), max_length=1000, blank=True)

    active = models.BooleanField(_("actif"), default=True)
    position = models.PositiveSmallIntegerField(_("ordre"), default=0)

    class Meta:
        verbose_name = _("moyen de règlement de la plateforme")
        verbose_name_plural = _("moyens de règlement de la plateforme")
        ordering = ("position", "kind", "provider_name")

    def __str__(self) -> str:
        return f"{self.libelle} — {self.get_country_display()} ({self.currency})"

    @property
    def libelle(self) -> str:
        """Le nom affiche au salon : l'operateur, a defaut le moyen."""
        return self.provider_name.strip() or self.get_kind_display()

    def get_country_display(self) -> str:
        from apps.tenants.models import Tenant

        return dict(Tenant.Country.choices).get(self.country, self.country)

    def problemes(self) -> list[str]:
        """Ce qui empeche ce moyen d'etre propose. Vide s'il est utilisable."""
        from apps.tenants.models import Tenant

        manques = []
        if self.country not in Tenant.Country.values:
            manques.append(str(_("pays inconnu")))
        if self.kind in self.QR_KINDS and not self.qr_image:
            manques.append(str(_("QR code manquant")))
        if self.kind == self.Kind.MOBILE_MONEY:
            if not self.provider_name.strip():
                manques.append(str(_("opérateur manquant")))
            if not self.account_number.strip():
                manques.append(str(_("numéro manquant")))
            if not self.account_holder.strip():
                manques.append(str(_("titulaire manquant")))
        return manques

    @property
    def est_utilisable(self) -> bool:
        return self.active and not self.problemes()

    def clean(self):
        from django.core.exceptions import ValidationError

        # Un moyen inactif peut rester incomplet : on le prepare avant de
        # l'ouvrir. Actif, il doit pouvoir servir tout de suite.
        if self.active and self.problemes():
            raise ValidationError(
                _("Ce moyen ne peut pas être actif : %(manques)s.")
                % {"manques": ", ".join(self.problemes())}
            )


# ---------------------------------------------------------------------------
# Demandes de paiement et historique
# ---------------------------------------------------------------------------


class SubscriptionPaymentRequest(TenantOwnedModel):
    """Un salon declare avoir paye son abonnement.

    Tout ce qui fait foi est fige a la creation : l'offre, la devise, le
    montant et le compte crediteur. Un tarif modifie le lendemain, un numero
    Mobile Money remplace, ne changent rien a une demande deja envoyee — c'est
    ce montant-la que l'administrateur doit retrouver dans son historique.

    Declarer n'active rien. Seule l'approbation par un administrateur ouvre
    une periode (voir `services.approuver_paiement`).
    """

    class Status(models.TextChoices):
        PENDING = "pending", _("En attente de vérification")
        APPROVED = "approved", _("Approuvée")
        REJECTED = "rejected", _("Refusée")

    subscription = models.ForeignKey(
        Subscription, on_delete=models.PROTECT, related_name="payment_requests"
    )
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="+")
    billing_months = models.PositiveSmallIntegerField()
    country = models.CharField(_("pays"), max_length=2)
    currency = models.CharField(_("devise"), max_length=3, choices=DEVISES_ABONNEMENT)
    amount = models.DecimalField(_("montant"), max_digits=12, decimal_places=2)

    payment_method = models.ForeignKey(
        PlatformPaymentMethod,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="requests",
    )
    method_kind = models.CharField(
        _("moyen"), max_length=20, choices=PlatformPaymentMethod.Kind.choices
    )
    method_label = models.CharField(_("compte crédité"), max_length=120)
    method_account_number = models.CharField(max_length=60, blank=True)
    method_account_holder = models.CharField(max_length=120, blank=True)

    reference = models.CharField(_("référence de transaction"), max_length=100)
    # Sans espaces ni casse : « ab 12 » et « AB12 » sont la meme transaction.
    reference_normalisee = models.CharField(max_length=100, db_index=True)
    proof = models.ForeignKey(
        "media.MediaAsset",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name=_("preuve de paiement"),
    )
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    status = models.CharField(
        _("statut"), max_length=20, choices=Status.choices, default=Status.PENDING
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(_("note de vérification"), blank=True)
    rejection_reason = models.CharField(_("motif du refus"), max_length=255, blank=True)

    # Ce que l'approbation a accorde, pour qu'on le relise sans recalculer.
    period_start = models.DateTimeField(null=True, blank=True)
    period_end = models.DateTimeField(null=True, blank=True)
    invoice = models.ForeignKey(
        Invoice, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        verbose_name = _("paiement d'abonnement")
        verbose_name_plural = _("paiements d'abonnement")
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["tenant", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
        ]
        constraints = [
            # Une seule demande en attente par salon : un double clic, ou
            # deux onglets, ne produisent pas deux demandes a verifier.
            models.UniqueConstraint(
                fields=["tenant"],
                condition=Q(status="pending"),
                name="une_demande_en_attente_par_salon",
            ),
            # Une reference de transaction ne sert qu'une fois, tous salons
            # confondus : une meme capture presentee par deux salons est une
            # tentative, pas deux paiements.
            models.UniqueConstraint(
                fields=["method_kind", "reference_normalisee"],
                condition=Q(status__in=["pending", "approved"]),
                name="reference_de_paiement_unique",
            ),
            models.CheckConstraint(condition=Q(amount__gt=0), name="demande_montant_positif"),
        ]
        permissions = [
            (
                "review_subscriptionpaymentrequest",
                "Peut approuver ou refuser les paiements d'abonnement",
            )
        ]

    def __str__(self) -> str:
        return f"{self.plan.name} — {self.amount} {self.currency} ({self.get_status_display()})"


class SubscriptionEvent(TenantOwnedModel):
    """Une ligne d'historique : ce qui est arrive a l'abonnement, et par qui.

    L'abonnement lui-meme ne garde que son etat courant. C'est ici qu'on
    retrouve, dans l'ordre, l'essai, chaque paiement approuve ou refuse,
    chaque prolongation manuelle, chaque suspension — avec les dates d'avant
    et d'apres. Rien n'y est jamais modifie ni efface.
    """

    class Kind(models.TextChoices):
        TRIAL_STARTED = "trial_started", _("Essai ouvert")
        PAYMENT_SUBMITTED = "payment_submitted", _("Paiement déclaré")
        PAYMENT_APPROVED = "payment_approved", _("Paiement approuvé")
        PAYMENT_REJECTED = "payment_rejected", _("Paiement refusé")
        MANUAL_EXTENSION = "manual_extension", _("Prolongation manuelle")
        SUSPENDED = "suspended", _("Suspendu")
        REACTIVATED = "reactivated", _("Réactivé")
        EXPIRED = "expired", _("Expiré")
        MIGRATED = "migrated", _("Reprise des abonnements existants")

    subscription = models.ForeignKey(Subscription, on_delete=models.PROTECT, related_name="events")
    kind = models.CharField(_("événement"), max_length=30, choices=Kind.choices)
    status_before = models.CharField(max_length=20, blank=True)
    status_after = models.CharField(max_length=20, blank=True)
    period_end_before = models.DateTimeField(null=True, blank=True)
    period_end_after = models.DateTimeField(null=True, blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    payment_request = models.ForeignKey(
        SubscriptionPaymentRequest,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="events",
    )
    note = models.TextField(blank=True)

    class Meta:
        verbose_name = _("historique d'abonnement")
        verbose_name_plural = _("historique des abonnements")
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["tenant", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} — {self.created_at:%d/%m/%Y}"


class SubscriptionReminder(TenantOwnedModel):
    """Un rappel d'abonnement envoye par e-mail — une seule fois.

    La tache des rappels passe toutes les heures : sans trace de ce qui est
    parti, chaque passage renverrait le meme « votre essai se termine dans
    3 jours ». La contrainte d'unicite porte sur la fin de periode : une
    periode prolongee a une autre fin, donc ses propres rappels.
    """

    class Kind(models.TextChoices):
        TRIAL_7 = "trial_7", _("Fin d'essai dans 7 jours")
        TRIAL_3 = "trial_3", _("Fin d'essai dans 3 jours")
        TRIAL_1 = "trial_1", _("Fin d'essai demain")
        RENEWAL_30 = "renewal_30", _("Renouvellement dans 30 jours")
        RENEWAL_7 = "renewal_7", _("Renouvellement dans 7 jours")
        RENEWAL_3 = "renewal_3", _("Renouvellement dans 3 jours")
        RENEWAL_1 = "renewal_1", _("Renouvellement demain")
        GRACE = "grace", _("Période terminée, délai de grâce")
        CLOSED = "closed", _("Accès fermé")

    subscription = models.ForeignKey(
        Subscription, on_delete=models.CASCADE, related_name="reminders"
    )
    kind = models.CharField(_("rappel"), max_length=20, choices=Kind.choices)
    period_end = models.DateTimeField(_("fin de période visée"))
    recipients = models.PositiveSmallIntegerField(_("destinataires"), default=0)

    class Meta:
        verbose_name = _("rappel d'abonnement")
        verbose_name_plural = _("rappels d'abonnement")
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("subscription", "kind", "period_end"),
                name="un_rappel_par_periode",
            )
        ]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} — {self.created_at:%d/%m/%Y}"
