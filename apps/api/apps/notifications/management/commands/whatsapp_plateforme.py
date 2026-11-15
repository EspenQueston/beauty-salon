"""Relier le numero WhatsApp de la plateforme a Evolution, et le verifier.

    python manage.py whatsapp_plateforme etat
    python manage.py whatsapp_plateforme connecter --qr /tmp/qr-whatsapp.png
    python manage.py whatsapp_plateforme essai +242061112233

`connecter` cree l'instance `WHATSAPP_INSTANCE` (avec le webhook STOP si
`WHATSAPP_WEBHOOK_TOKEN` est pose), puis ecrit le QR code dans un fichier :
on l'ouvre et on le scanne depuis le telephone du numero Beauty Salon
(WhatsApp › Appareils connectes). Rien n'est affiche de la cle d'Evolution.

`essai` envoie un message de test, tout de suite, sans passer par la file.
"""

from __future__ import annotations

import base64

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.assistants import evolution
from apps.notifications import whatsapp


class Command(BaseCommand):
    help = "Relie et verifie le numero WhatsApp de la plateforme (Evolution)."

    def add_arguments(self, parser):
        parser.add_argument("action", choices=["etat", "connecter", "essai"])
        parser.add_argument("numero", nargs="?", default="")
        parser.add_argument("--qr", default="qr-whatsapp.png", help="Fichier du QR code.")

    def handle(self, action, numero, qr, **options):
        instance = settings.WHATSAPP_INSTANCE
        if not instance:
            raise CommandError("WHATSAPP_INSTANCE est vide dans l'environnement.")
        if not evolution.configuree():
            raise CommandError("EVOLUTION_API_URL ou EVOLUTION_API_KEY est vide.")

        try:
            if action == "etat":
                self.stdout.write(f"{instance} : {evolution.etat(instance) or 'inconnu'}")
            elif action == "connecter":
                self._connecter(instance, qr)
            else:
                chiffres = whatsapp.numero(numero)
                if not chiffres:
                    raise CommandError("Numéro attendu avec son indicatif : +242…, +86…")
                identifiant = whatsapp._envoyer(
                    chiffres, "Test Beauty Salon : les notifications WhatsApp fonctionnent."
                )
                self.stdout.write(self.style.SUCCESS(f"Envoyé (identifiant {identifiant})."))
        except evolution.EvolutionIndisponible as erreur:
            raise CommandError(str(erreur)) from erreur

    def _connecter(self, instance: str, fichier: str):
        if evolution.etat_ou_vide(instance) == "open":
            self.stdout.write(self.style.SUCCESS(f"{instance} est déjà connectée."))
            return
        if not evolution.etat_ou_vide(instance):
            jeton = settings.WHATSAPP_WEBHOOK_TOKEN
            base = settings.API_BASE_URL.rstrip("/")
            webhook = f"{base}/api/v1/webhooks/whatsapp-plateforme/{jeton}" if jeton else ""
            evolution.creer_instance(instance, webhook)
            self.stdout.write(f"Instance {instance} créée.")
        image = evolution.qr_code(instance)
        if not image:
            self.stdout.write(self.style.SUCCESS("Déjà connectée : aucun QR code à scanner."))
            return
        donnees = image.split(",", 1)[-1]
        with open(fichier, "wb") as sortie:
            sortie.write(base64.b64decode(donnees))
        self.stdout.write(
            f"QR code écrit dans {fichier}. Scannez-le depuis le téléphone du numéro "
            "Beauty Salon : WhatsApp › Appareils connectés › Connecter un appareil. "
            "Puis vérifiez avec : whatsapp_plateforme etat"
        )
