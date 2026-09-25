"""Mise en route d'une installation.

Ne cree que ce dont la plateforme a reellement besoin pour fonctionner : le
catalogue des offres, et un compte d'administration. Aucune donnee fictive -
les salons, prestations et rendez-vous naissent de l'usage, pas d'un script.

    uv run python manage.py bootstrap_platform --email vous@exemple.com
"""

import getpass
from decimal import Decimal

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import User
from apps.billing.models import Plan, PlanPrice

# L'essai, et les deux offres payantes : la meme plateforme, reglee au mois
# ou a l'annee. Leur prix de reference est en yuans ; les autres devises se
# saisissent dans l'administration (« Tarifs d'abonnement »), jamais ici.
OFFRES = [
    {
        "code": Plan.Code.TRIAL,
        "name": "Essai",
        "description": "Deux semaines pour essayer, sans engagement.",
        "billing_months": 0,
        "reference_price": Decimal("0"),
        "max_staff": None,
        "allows_custom_domain": False,
    },
    {
        "code": Plan.Code.MONTHLY,
        "name": "Mensuel",
        "description": "Toute la plateforme, réglée chaque mois.",
        "billing_months": 1,
        "reference_price": Decimal("0"),
        "max_staff": None,
        "allows_custom_domain": False,
    },
    {
        "code": Plan.Code.YEARLY,
        "name": "Annuel",
        "description": "Toute la plateforme, réglée pour douze mois.",
        "billing_months": 12,
        "reference_price": Decimal("0"),
        "max_staff": None,
        "allows_custom_domain": False,
    },
]

# Prix de reference, poses seulement s'ils manquent : un tarif modifie depuis
# l'administration n'est jamais ecrase par une remise en route.
PRIX_CNY = {Plan.Code.MONTHLY: Decimal("99"), Plan.Code.YEARLY: Decimal("999")}

# Les offres des debuts : gardees pour l'historique, jamais reproposees.
ANCIENNES = (Plan.Code.SOLO, Plan.Code.SALON, Plan.Code.PRO)


class Command(BaseCommand):
    help = "Crée le catalogue des offres et le compte d'administration."

    def add_arguments(self, parser):
        parser.add_argument(
            "--email",
            help="Adresse du compte d'administration à créer ou mettre à jour.",
        )
        parser.add_argument(
            "--password",
            help=(
                "Mot de passe. Omettez-le pour une saisie masquée, "
                "ce qui évite de le laisser dans l'historique du terminal."
            ),
        )
        parser.add_argument(
            "--skip-plans",
            action="store_true",
            help="Ne pas toucher au catalogue des offres.",
        )

    def handle(self, *args, **options):
        if not options["skip_plans"]:
            self._sync_plans()

        if options["email"]:
            self._create_admin(options["email"], options.get("password"))
        else:
            self.stdout.write(
                "Aucun --email fourni : le catalogue est en place, "
                "aucun compte n'a été créé."
            )

    def _sync_plans(self) -> None:
        for position, offre in enumerate(OFFRES):
            plan, _ = Plan.objects.update_or_create(
                code=offre["code"],
                defaults={**offre, "position": position, "active": True},
            )
            if plan.code in PRIX_CNY:
                PlanPrice.objects.get_or_create(
                    plan=plan,
                    currency="CNY",
                    defaults={"amount": PRIX_CNY[plan.code], "active": True},
                )
        Plan.objects.filter(code__in=ANCIENNES).update(active=False)
        self.stdout.write(self.style.SUCCESS(f"{len(OFFRES)} offres en place."))

    def _create_admin(self, email: str, password: str | None) -> None:
        email = email.strip().lower()

        if not password:
            password = getpass.getpass("Mot de passe : ")
            if password != getpass.getpass("Confirmation : "):
                raise CommandError("Les deux saisies diffèrent.")

        user = User.objects.filter(email=email).first()
        try:
            validate_password(password, user=user)
        except ValidationError as error:
            raise CommandError("\n".join(error.messages)) from error

        if user is None:
            user = User(email=email, display_name="Administration plateforme")
            action = "créé"
        else:
            action = "mis à jour"

        user.is_staff = True
        user.is_superuser = True
        user.is_platform_admin = True
        user.is_active = True
        user.set_password(password)
        user.save()

        self.stdout.write(self.style.SUCCESS(f"Compte {email} {action}."))
        self.stdout.write(
            "La double authentification sera demandée à la première connexion "
            "à l'administration."
        )
