"""Reinitialisation d'un compte d'administration depuis le serveur.

Le parcours « mot de passe oublie » par e-mail suppose que l'envoi de mail
fonctionne. Quand ce n'est pas le cas - SMTP mal configure, domaine pas
encore branche, boite inaccessible - il faut une porte de secours qui ne
depende que d'un acces au serveur.

    uv run python manage.py reset_admin_password --email vous@exemple.com
    uv run python manage.py reset_admin_password --email vous@exemple.com --reset-mfa
"""

import getpass

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django_otp.plugins.otp_static.models import StaticDevice
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.models import User


class Command(BaseCommand):
    help = "Réinitialise le mot de passe d'un compte d'administration."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument(
            "--password",
            help="Omettez-le pour une saisie masquée.",
        )
        parser.add_argument(
            "--reset-mfa",
            action="store_true",
            help=(
                "Supprime aussi l'appareil de double authentification. "
                "À utiliser en cas de téléphone perdu : un nouvel enrôlement "
                "sera demandé à la prochaine connexion."
            ),
        )

    def handle(self, *args, **options):
        email = options["email"].strip().lower()

        user = User.objects.filter(email=email).first()
        if user is None:
            raise CommandError(f"Aucun compte avec l'adresse {email}.")
        if not user.is_staff:
            raise CommandError(
                f"{email} n'est pas un compte d'administration. "
                "Cette commande ne sert qu'à ceux-là."
            )

        password = options.get("password")
        if not password:
            password = getpass.getpass("Nouveau mot de passe : ")
            if password != getpass.getpass("Confirmation : "):
                raise CommandError("Les deux saisies diffèrent.")

        try:
            validate_password(password, user=user)
        except ValidationError as error:
            raise CommandError("\n".join(error.messages)) from error

        user.set_password(password)
        user.is_active = True
        user.save(update_fields=["password", "is_active", "updated_at"])
        self.stdout.write(self.style.SUCCESS(f"Mot de passe de {email} réinitialisé."))

        if options["reset_mfa"]:
            supprimes = TOTPDevice.objects.filter(user=user).delete()[0]
            StaticDevice.objects.filter(user=user).delete()
            self.stdout.write(
                self.style.WARNING(
                    f"Double authentification remise à zéro ({supprimes} appareil·s). "
                    "Un nouvel enrôlement sera demandé à la prochaine connexion."
                )
            )
        elif TOTPDevice.objects.filter(user=user, confirmed=True).exists():
            self.stdout.write(
                "La double authentification reste active. "
                "Ajoutez --reset-mfa si le téléphone est perdu."
            )
