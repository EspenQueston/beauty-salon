"""Rattrapage : traduit ce qui manque, salon par salon.

    python manage.py traduire_le_contenu             # tous les salons
    python manage.py traduire_le_contenu --salon x   # un seul, par slug
    python manage.py traduire_le_contenu --a-blanc   # compte, n'ecrit rien

Idempotent : un second passage ne refait que ce qui a change depuis le premier.
C'est ce qui permet de le lancer sans reflechir apres une reprise de contenu.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.tenants.models import Tenant
from apps.translations.services import a_traduire, traducteur, traduire_le_salon


def _modeles():
    """Les modeles a parcourir, importes tard pour ne pas figer le registre."""
    from apps.catalog.models import Service, ServiceCategory, ServiceOption
    from apps.payments.models import PaymentChannel
    from apps.salons.models import SalonProfile
    from apps.staff.models import StaffMember
    from apps.store.models import Product, Requirement

    return (
        SalonProfile,
        ServiceCategory,
        Service,
        ServiceOption,
        StaffMember,
        Product,
        Requirement,
        PaymentChannel,
    )


class Command(BaseCommand):
    help = "Traduit le contenu des salons vers une langue cible."

    def add_arguments(self, parser):
        parser.add_argument("--langue", default="en")
        parser.add_argument("--salon", default=None, help="slug d'un salon unique")
        parser.add_argument(
            "--a-blanc",
            action="store_true",
            help="compte ce qui serait traduit, sans rien appeler ni ecrire",
        )

    def handle(self, *args, **options):
        langue = options["langue"]
        salons = Tenant.objects.all()
        if options["salon"]:
            salons = salons.filter(slug=options["salon"])

        if not salons.exists():
            self.stderr.write("aucun salon ne correspond")
            return

        if not options["a_blanc"] and not traducteur().disponible():
            self.stderr.write(
                "aucune cle OPENAI_API_KEY : rien ne serait traduit. "
                "Posez-la dans apps/api/.env, ou relancez avec --a-blanc."
            )
            return

        total = 0
        for tenant in salons:
            if options["a_blanc"]:
                compte = self._compter(tenant, langue)
                self.stdout.write(f"  {tenant.slug} — {compte} champ(s) a traduire")
                total += compte
                continue
            ecrits = traduire_le_salon(tenant, langue)
            self.stdout.write(f"  {tenant.slug} — {ecrits} champ(s) traduits")
            total += ecrits

        verbe = "a traduire" if options["a_blanc"] else "traduits"
        self.stdout.write(self.style.SUCCESS(f"{total} champ(s) {verbe}"))

    def _compter(self, tenant, langue: str) -> int:
        from apps.common.db import tenant_context

        compte = 0
        with tenant_context(tenant.id):
            for modele in _modeles():
                for objet in modele.objects.all():
                    compte += len(a_traduire(objet, langue))
        return compte
