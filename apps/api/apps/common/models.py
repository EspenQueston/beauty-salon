"""Classes de base partagees par tous les modules metier."""

import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from .db import get_current_tenant_id


class HomeReference(models.Model):
    """Publication volontaire par la plateforme, distincte des données privées du salon."""

    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE)
    author = models.CharField("responsable", max_length=100)
    quote_fr = models.TextField("témoignage français", max_length=1000, blank=True)
    quote_en = models.TextField("témoignage anglais", max_length=1000, blank=True)
    portrait = models.URLField("portrait autorisé (HTTPS)", blank=True)
    consent = models.BooleanField("autorisation de publication obtenue", default=False)
    verified = models.BooleanField("identité et propos vérifiés", default=False)
    active = models.BooleanField("publier", default=False)
    showcase = models.BooleanField("proposer le mini-site comme exemple", default=False)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = "référence de la page d’accueil"
        verbose_name_plural = "références de la page d’accueil"
        ordering = ("position", "pk")

    def __str__(self):
        return f"{self.tenant} · {self.author}"

    def clean(self):
        super().clean()
        if self.active and not (self.consent and self.verified):
            raise ValidationError("Une publication exige l’autorisation et la vérification.")
        if self.portrait and not self.portrait.startswith("https://"):
            raise ValidationError({"portrait": "Le portrait doit utiliser HTTPS."})



class HomeSettings(models.Model):
    key = models.CharField(max_length=12, default="home", unique=True, editable=False)
    support_email = models.EmailField("adresse d’assistance", blank=True)
    support_whatsapp = models.CharField(
        "WhatsApp d’assistance (indicatif inclus)", max_length=20, blank=True
    )

    class Meta:
        verbose_name = "contact de la page d’accueil"
        verbose_name_plural = "contact de la page d’accueil"

    def __str__(self):
        return "Assistance du site principal"

    def clean(self):
        super().clean()
        if self.support_whatsapp and not self.support_whatsapp.lstrip("+").isdigit():
            raise ValidationError(
                {"support_whatsapp": "Utilisez uniquement l’indicatif et les chiffres."}
            )



class HomeMetric(models.Model):
    day = models.DateField()
    event = models.CharField(max_length=32)
    language = models.CharField(max_length=2)
    count = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "mesure du parcours de création"
        verbose_name_plural = "mesures du parcours de création"
        constraints = [
            models.UniqueConstraint(fields=("day", "event", "language"), name="home_metric_daily")
        ]
        ordering = ("-day", "event")

    def __str__(self):
        return f"{self.day} · {self.event} · {self.count}"


class HomeBookingMilestone(models.Model):
    """Repère interne : un premier rendez-vous ne se compte qu'une fois par salon."""

    tenant = models.OneToOneField("tenants.Tenant", on_delete=models.CASCADE)

    def __str__(self):
        return str(self.tenant_id)


class UUIDModel(models.Model):
    """Cle primaire UUID : aucun identifiant devinable n'apparait dans les URL."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class TenantQuerySet(models.QuerySet):
    pass


class TenantManager(models.Manager.from_queryset(TenantQuerySet)):
    """Manager par defaut des modeles tenant : filtre sur le contexte courant.

    Hors contexte tenant il renvoie un queryset vide plutot que l'ensemble
    des lignes. Un oubli de contexte produit donc une page vide, jamais une
    fuite de donnees.
    """

    def get_queryset(self):
        queryset = super().get_queryset()
        tenant_id = get_current_tenant_id()
        if tenant_id is None:
            return queryset.none()
        return queryset.filter(tenant_id=tenant_id)


class TenantOwnedModel(UUIDModel, TimeStampedModel):
    """Toute donnee appartenant a un salon herite de cette classe.

    En heriter declenche deux choses :
      - le filtrage applicatif via `objects` ;
      - la verification, par tests/test_rls.py, que la table porte bien une
        politique RLS. Ajouter un modele sans sa migration RLS fait echouer
        la suite de tests.

    `all_tenants` contourne le filtrage applicatif et sert uniquement a
    l'admin plateforme et aux taches inter-tenants, toujours sur l'alias
    `admin` : la couche RLS reste, elle, en place.
    """

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="%(class)ss",
        db_index=True,
        verbose_name=_("salon"),
    )

    # L'ordre compte : Django retient le premier manager declare comme
    # _default_manager. TenantManager doit donc rester en tete, sinon l'admin
    # et les descripteurs de relations basculeraient sur le manager non filtre.
    objects = TenantManager()
    all_tenants = models.Manager()  # noqa: DJ012

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        # Confort et garde-fou : on ne cree jamais une ligne orpheline de tenant
        # quand le contexte en fournit un.
        if self.tenant_id is None:
            current = get_current_tenant_id()
            if current is not None:
                self.tenant_id = current
        return super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        self._validate_related_tenants()

    def _validate_related_tenants(self):
        """Interdit de relier deux objets appartenant a des salons differents.

        En exploitation normale, ce cas ne peut pas se produire : les
        politiques RLS ne laissent voir que les lignes du salon courant. Mais
        l'admin plateforme travaille avec un role BYPASSRLS et voit tous les
        salons a la fois - rien ne l'empecherait, dans un menu deroulant,
        d'attribuer a une prestataire de Kinshasa une prestation de
        Brazzaville. Cette verification ferme ce chemin.
        """
        if self.tenant_id is None:
            return

        errors = {}
        for field in self._meta.concrete_fields:
            # Les deux formes de relation sortante : cle etrangere et
            # relation un-a-un. Omettre la seconde laisserait passer, par
            # exemple, le lien StaffMember -> Membership.
            if not (field.many_to_one or field.one_to_one) or field.name == "tenant":
                continue
            # Toute relation vers un objet lui-meme rattache a un salon.
            if not hasattr(field.related_model, "tenant_id"):
                continue
            if getattr(self, field.attname, None) is None:
                continue

            related = getattr(self, field.name, None)
            if related is not None and str(related.tenant_id) != str(self.tenant_id):
                errors[field.name] = ValidationError(
                    _("Cet element appartient a un autre salon."),
                    code="cross_tenant",
                )

        if errors:
            raise ValidationError(errors)
