"""Diagnostic complet de l'envoi d'e-mails.

---------------------------------------------------------------------------
Pourquoi une commande plutot qu'une explication
---------------------------------------------------------------------------

Quand un e-mail n'arrive pas, la cause est presque toujours ailleurs que
dans le code : un port ferme par le pare-feu, un mot de passe change, un
worker qui ne tourne pas, une chaine de caracteres avalee par le shell. Sur
quatre maillons, chacun echoue differemment et aucun ne le dit clairement.

Cette commande les teste **dans l'ordre**, et s'arrete au premier qui casse
en disant lequel. Elle se lance sur la machine qui a le probleme, ce qu'aucun
diagnostic a distance ne peut remplacer.

    uv run python manage.py tester_emails
    uv run python manage.py tester_emails --envoyer vous@exemple.com
"""

import smtplib
import socket
import ssl

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.core.management.base import BaseCommand

OK = "  [ok]   "
KO = "  [ECHEC]"
INFO = "         "


class Command(BaseCommand):
    help = "Vérifie la configuration d'envoi d'e-mails, maillon par maillon."

    def add_arguments(self, parser):
        parser.add_argument(
            "--envoyer",
            metavar="ADRESSE",
            help="Envoie réellement un message de test à cette adresse.",
        )

    def handle(self, *args, **options):
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("1. Configuration"))

        host = getattr(settings, "EMAIL_HOST", "")
        port = getattr(settings, "EMAIL_PORT", 0)
        user = getattr(settings, "EMAIL_HOST_USER", "")
        password = getattr(settings, "EMAIL_HOST_PASSWORD", "")
        use_ssl = getattr(settings, "EMAIL_USE_SSL", False)
        use_tls = getattr(settings, "EMAIL_USE_TLS", False)

        self.stdout.write(f"{INFO} serveur     : {host}:{port}")
        self.stdout.write(f"{INFO} compte      : {user}")
        chiffrement = "SSL direct" if use_ssl else "STARTTLS" if use_tls else "aucun"
        self.stdout.write(f"{INFO} chiffrement : {chiffrement}")
        self.stdout.write(f"{INFO} expéditeur  : {settings.DEFAULT_FROM_EMAIL}")

        if not host or not user:
            self.stdout.write(f"{KO} Configuration incomplète — vérifiez le fichier .env.")
            return

        # Un mot de passe vide ou tronque est la cause la plus frequente, et
        # la plus invisible : on ne l'affiche jamais, on ne verifie que sa
        # longueur et ses bornes.
        if not password:
            self.stdout.write(f"{KO} Mot de passe vide.")
            return
        self.stdout.write(
            f"{INFO} mot de passe: {len(password)} caractères, "
            f"commence par « {password[0]} », finit par « {password[-1]} »"
        )
        if password != password.strip():
            self.stdout.write(
                f"{KO} Le mot de passe a des espaces au début ou à la fin — "
                "souvent un copier-coller de trop."
            )
        self.stdout.write(f"{OK} Configuration lue.")

        # ----- 2. Le nom se resout-il ? -----------------------------------
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("2. Résolution du nom"))
        try:
            ip = socket.gethostbyname(host)
        except OSError as exc:
            self.stdout.write(f"{KO} {host} introuvable : {exc}")
            return

        self.stdout.write(f"{INFO} {host} -> {ip}")
        if ip.startswith(("198.18.", "198.19.", "127.", "10.", "192.168.")):
            self.stdout.write(
                f"{KO} Cette adresse est un réseau interne ou un proxy, "
                "pas le vrai serveur. Un VPN, un antivirus ou un pare-feu "
                "d'entreprise intercepte la connexion."
            )
        else:
            self.stdout.write(f"{OK} Nom résolu vers une adresse publique.")

        # ----- 3. Le port repond-il ? --------------------------------------
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("3. Connexion au serveur"))
        try:
            sock = socket.create_connection((host, port), timeout=10)
        except OSError as exc:
            self.stdout.write(
                f"{KO} Port {port} injoignable : {exc}\n"
                f"{INFO} Beaucoup de fournisseurs d'accès bloquent le port 465 "
                "et le 587. Essayez l'autre."
            )
            return

        try:
            if use_ssl:
                context = ssl.create_default_context()
                sock = context.wrap_socket(sock, server_hostname=host)
            banner = sock.recv(200).decode(errors="replace").strip()
            self.stdout.write(f"{INFO} réponse : {banner[:70]}")
            self.stdout.write(f"{OK} Le serveur répond.")
        except ssl.SSLError as exc:
            self.stdout.write(
                f"{KO} Le chiffrement échoue : {exc}\n"
                f"{INFO} Si EMAIL_USE_SSL vaut True, le port doit être 465. "
                "Pour le port 587, mettez EMAIL_USE_TLS=True à la place."
            )
            return
        finally:
            sock.close()

        # ----- 4. Le mot de passe passe-t-il ? -----------------------------
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("4. Authentification"))
        try:
            server = (
                smtplib.SMTP_SSL(host, port, timeout=15)
                if use_ssl
                else smtplib.SMTP(host, port, timeout=15)
            )
            with server:
                if use_tls and not use_ssl:
                    server.starttls()
                server.login(user, password)
            self.stdout.write(f"{OK} Le serveur accepte le compte et le mot de passe.")
        except smtplib.SMTPAuthenticationError as exc:
            self.stdout.write(
                f"{KO} Compte ou mot de passe refusé : {exc.smtp_error}\n"
                f"{INFO} Vérifiez le mot de passe dans .env. S'il contient « # », "
                "entourez-le de guillemets."
            )
            return
        except Exception as exc:  # noqa: BLE001 - on veut la cause exacte affichée
            self.stdout.write(f"{KO} {type(exc).__name__} : {exc}")
            return

        # ----- 5. Un envoi reel, si demande --------------------------------
        destinataire = options.get("envoyer")
        if not destinataire:
            self.stdout.write("")
            self.stdout.write(
                self.style.SUCCESS(
                    "Tout est bon. Pour un envoi réel :\n"
                    "  uv run python manage.py tester_emails --envoyer vous@exemple.com"
                )
            )
            return

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("5. Envoi réel"))
        try:
            message = EmailMultiAlternatives(
                subject="Beauty Salon — test d'envoi",
                body=(
                    "Si vous lisez ceci, la configuration d'envoi fonctionne.\n\n"
                    f"Serveur   : {host}:{port}\n"
                    f"Expéditeur: {settings.DEFAULT_FROM_EMAIL}\n"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[destinataire],
            )
            message.send(fail_silently=False)
        except Exception as exc:  # noqa: BLE001
            self.stdout.write(f"{KO} {type(exc).__name__} : {exc}")
            return

        self.stdout.write(f"{OK} Message remis au serveur pour {destinataire}.")
        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                "Le serveur l'a accepté. S'il n'arrive pas, regardez les "
                "indésirables : un domaine sans SPF ni DKIM y tombe souvent."
            )
        )
