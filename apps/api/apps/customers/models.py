"""Fichier clientes du salon.

C'est la donnee la plus sensible de la plateforme, et celle qui attache
durablement un salon au produit. Deux salons ne doivent jamais se voir :
d'ou l'heritage de TenantOwnedModel et la politique RLS associee.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import TenantOwnedModel


class Customer(TenantOwnedModel):
    full_name = models.CharField(_("nom complet"), max_length=150)
    phone = models.CharField(_("téléphone"), max_length=32)
    email = models.EmailField(blank=True)

    class ContactPreference(models.TextChoices):
        WHATSAPP = "whatsapp", _("WhatsApp")
        PHONE = "phone", _("Téléphone")
        EMAIL = "email", _("E-mail")

    contact_preference = models.CharField(
        max_length=20, choices=ContactPreference.choices, default=ContactPreference.WHATSAPP
    )

    # Consentement explicite, requis avant toute relance commerciale.
    marketing_consent = models.BooleanField(default=False)
    marketing_consent_at = models.DateTimeField(null=True, blank=True)

    # Notes internes (allergies, sensibilite du cuir chevelu, historique de
    # coloration). Lecture reservee aux roles owner/manager : ni la cliente
    # ni un prestataire de passage n'y ont acces.
    #
    # Le chiffrement au repos n'est pas encore en place : il viendra avec la
    # phase paiements, ou une gestion de cles devient de toute facon
    # necessaire. En attendant, la protection repose sur le chiffrement disque
    # de l'hote et sur le filtrage par role.
    private_notes = models.TextField(blank=True)

    class Meta:
        verbose_name = _("cliente")
        verbose_name_plural = _("clientes")
        ordering = ("full_name",)
        indexes = [models.Index(fields=["tenant", "phone"])]
        constraints = [
            # Un meme numero ne doit pas creer deux fiches dans le meme salon :
            # sinon l'historique se scinde a la premiere faute de frappe.
            models.UniqueConstraint(
                fields=["tenant", "phone"], name="unique_customer_phone_per_tenant"
            )
        ]

    def __str__(self) -> str:
        return self.full_name
