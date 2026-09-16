"""Liste d'attente : ce qu'on fait quand il n'y a plus rien de libre.

---------------------------------------------------------------------------
Ce que ce fichier ne fait pas
---------------------------------------------------------------------------

Il ne reserve rien. Une inscription en liste d'attente n'est pas un
rendez-vous, ne bloque aucun creneau et ne donne aucune priorite
automatique : c'est une demande de rappel, et le salon reste maitre de qui
il rappelle. Faire autrement - attribuer automatiquement un creneau libere a
la premiere inscrite - donnerait des rendez-vous a des gens qui ne les
attendent plus, et personne ne s'y presenterait.

Le seul automatisme est le signalement : quand une annulation libere de la
place sur une periode demandee, le salon le voit dans son agenda.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import TenantOwnedModel


class WaitlistEntry(TenantOwnedModel):
    """Une cliente qui veut etre rappelee si une place se libere."""

    class Status(models.TextChoices):
        WAITING = "waiting", _("En attente")
        CONTACTED = "contacted", _("Contactée")
        BOOKED = "booked", _("Rendez-vous pris")
        CLOSED = "closed", _("Classée")

    service = models.ForeignKey(
        "catalog.Service",
        on_delete=models.CASCADE,
        related_name="waitlist_entries",
        verbose_name=_("prestation souhaitée"),
    )
    # Facultatif : « peu importe qui » est une reponse frequente, et exiger
    # un choix ferait abandonner l'inscription.
    staff_member = models.ForeignKey(
        "staff.StaffMember",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="waitlist_entries",
        verbose_name=_("prestataire souhaité"),
    )

    full_name = models.CharField(_("nom"), max_length=150)
    phone = models.CharField(_("téléphone"), max_length=32)
    email = models.EmailField(blank=True)

    # Fenetre souhaitee, en jours. Sans elle, la liste devient un fourre-tout
    # ou le salon ne sait pas qui rappeler pour quelle date.
    preferred_from = models.DateField(_("à partir du"))
    preferred_to = models.DateField(_("jusqu'au"))
    note = models.CharField(_("précision"), max_length=255, blank=True)

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.WAITING
    )
    contacted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("inscription en liste d'attente")
        verbose_name_plural = _("liste d'attente")
        ordering = ("created_at",)
        indexes = [models.Index(fields=["tenant", "status", "preferred_from"])]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(preferred_to__gte=models.F("preferred_from")),
                name="waitlist_window_is_ordered",
            )
        ]

    def __str__(self) -> str:
        return f"{self.full_name} — {self.service_id}"

    @property
    def is_open(self) -> bool:
        return self.status in (self.Status.WAITING, self.Status.CONTACTED)
