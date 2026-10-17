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

    # n8n : le salon branche sa propre automatisation WhatsApp et nous envoie
    # chaque message pour l'historique. `n8n_cle` designe le salon dans
    # l'adresse du webhook ; le jeton qui l'accompagne n'est garde qu'en
    # empreinte (SHA-256), comme celui de WhatsApp.
    n8n_numero = models.CharField(_("numéro WhatsApp de l'assistant"), max_length=32, blank=True)
    n8n_cle = models.CharField(max_length=24, blank=True, db_index=True)
    n8n_empreinte = models.CharField(max_length=64, blank=True)
    n8n_derniere_reception = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("réglages des assistants")
        verbose_name_plural = _("réglages des assistants")
        constraints = [
            models.UniqueConstraint(fields=["tenant"], name="un_reglage_assistant_par_salon")
        ]

    def __str__(self) -> str:
        return f"Assistants — {self.tenant_id}"


class ConversationAssistant(TenantOwnedModel):
    """Un fil de discussion entre l'assistant du salon et un contact.

    Un fil par canal et par contact (un numero WhatsApp le plus souvent) :
    l'historique se lit comme une messagerie, contact par contact.
    """

    class Canal(models.TextChoices):
        WHATSAPP = "whatsapp", _("WhatsApp (passerelle de la plateforme)")
        N8N = "n8n", _("n8n")

    canal = models.CharField(max_length=12, choices=Canal.choices)
    contact = models.CharField(_("contact"), max_length=64)
    nom = models.CharField(_("nom affiché"), max_length=120, blank=True)
    dernier_message_le = models.DateTimeField(db_index=True)
    dernier_apercu = models.CharField(max_length=200, blank=True)
    nombre_messages = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = _("conversation de l'assistant")
        verbose_name_plural = _("conversations de l'assistant")
        ordering = ("-dernier_message_le",)
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "canal", "contact"], name="une_conversation_par_contact"
            )
        ]

    def __str__(self) -> str:
        return self.nom or self.contact


class MessageAssistant(TenantOwnedModel):
    """Un message du fil : recu de la cliente, ou envoye par l'assistant."""

    class Direction(models.TextChoices):
        ENTRANT = "entrant", _("Reçu")
        SORTANT = "sortant", _("Envoyé")

    conversation = models.ForeignKey(
        ConversationAssistant, on_delete=models.CASCADE, related_name="messages"
    )
    direction = models.CharField(max_length=8, choices=Direction.choices)
    texte = models.TextField()
    envoye_le = models.DateTimeField(db_index=True)
    # L'identifiant du message chez l'expediteur (n8n, WhatsApp) : un meme
    # message envoye deux fois n'apparait qu'une fois.
    reference = models.CharField(max_length=120, blank=True)

    class Meta:
        verbose_name = _("message de l'assistant")
        verbose_name_plural = _("messages de l'assistant")
        ordering = ("envoye_le",)
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "reference"],
                condition=~models.Q(reference=""),
                name="un_message_par_reference",
            )
        ]
