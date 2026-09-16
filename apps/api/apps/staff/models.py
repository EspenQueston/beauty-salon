"""Prestataires du salon."""

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import TenantOwnedModel


class StaffMember(TenantOwnedModel):
    """Une personne qui realise des prestations.

    Le lien vers un Membership est optionnel : un salon doit pouvoir gerer
    l'agenda d'une collaboratrice qui n'a pas encore de compte, ou n'en
    voudra jamais.
    """

    membership = models.OneToOneField(
        "accounts.Membership",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="staff_member",
    )
    # Retiree de la liste sans etre effacee.
    #
    # Un prestataire qui a deja travaille ne peut pas etre supprime : ses
    # rendez-vous passes portent son nom, et les effacer reecrirait
    # l'historique du salon - y compris ses comptes. Mais il n'a plus rien a
    # faire dans la liste du quotidien une fois parti.
    archived_at = models.DateTimeField(_("retiré le"), null=True, blank=True)

    name = models.CharField(_("nom"), max_length=120)
    specialty = models.CharField(_("spécialité"), max_length=150, blank=True)
    bio = models.TextField(blank=True)
    photo = models.ForeignKey(
        "media.MediaAsset", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+",
    )
    position = models.PositiveSmallIntegerField(default=0)
    active = models.BooleanField(default=True)

    services = models.ManyToManyField(
        "catalog.Service",
        through="StaffService",
        related_name="staff_members",
        blank=True,
    )

    class Meta:
        verbose_name = _("prestataire")
        verbose_name_plural = _("prestataires")
        ordering = ("position", "name")
        indexes = [models.Index(fields=["tenant", "active"])]

    def __str__(self) -> str:
        return self.name


class StaffService(TenantOwnedModel):
    """Quelle prestation est realisee par qui.

    Sans cette table, proposer un prestataire pour une prestation qu'il ne
    maitrise pas produirait des rendez-vous impossibles a honorer.
    """

    staff_member = models.ForeignKey(
        StaffMember, on_delete=models.CASCADE, related_name="staff_services"
    )
    service = models.ForeignKey(
        "catalog.Service", on_delete=models.CASCADE, related_name="staff_services"
    )

    class Meta:
        verbose_name = _("compétence")
        verbose_name_plural = _("compétences")
        constraints = [
            models.UniqueConstraint(
                fields=["staff_member", "service"], name="unique_staff_service"
            )
        ]

    def __str__(self) -> str:
        return f"{self.staff_member.name} - {self.service.name}"
