"""Classes de base partagees par tous les modules metier."""

import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from .db import get_current_tenant_id


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
