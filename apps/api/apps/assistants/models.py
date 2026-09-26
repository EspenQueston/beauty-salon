"""Reglages des assistants IA d'un salon (offre Pro).

Un seul enregistrement par salon. Aucun secret en clair : le jeton du
webhook WhatsApp n'est garde que sous forme d'empreinte, et la cle de
l'API Evolution est un reglage de la plateforme, jamais une donnee de salon.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import TenantOwnedModel


class AssistantReglages(TenantOwnedModel):
    class StatutWhatsApp(models.TextChoices):
        AUCUN = "aucun", _("Non connecté")
        EN_ATTENTE = "en_attente", _("QR code à scanner")
        CONNECTE = "connecte", _("Connecté")
        DECONNECTE = "deconnecte", _("Déconnecté")

    # Assistant des clientes sur le mini-site : ouvert par defaut aux salons
    # Pro, le salon peut le couper.
    clientes_actif = models.BooleanField(_("assistant du mini-site actif"), default=True)

    # WhatsApp, par l'API Evolution : une instance par salon.
    whatsapp_actif = models.BooleanField(_("réponses automatiques WhatsApp"), default=False)
    whatsapp_instance = models.CharField(max_length=64, blank=True, db_index=True)
    whatsapp_empreinte = models.CharField(
        _("empreinte du jeton du webhook"), max_length=64, blank=True
    )
    whatsapp_statut = models.CharField(
        max_length=12, choices=StatutWhatsApp.choices, default=StatutWhatsApp.AUCUN
    )
    whatsapp_numero = models.CharField(max_length=32, blank=True)
    whatsapp_derniere_activite = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("réglages des assistants")
        verbose_name_plural = _("réglages des assistants")
        constraints = [
            models.UniqueConstraint(fields=["tenant"], name="un_reglage_assistant_par_salon")
        ]

    def __str__(self) -> str:
        return f"Assistants — {self.tenant_id}"
