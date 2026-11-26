"""Ouvre SASPAY : tarifs dans chaque devise, et un moyen SASPAY par pays et devise.

    python manage.py ouvrir_saspay              # montre ce qui serait fait
    python manage.py ouvrir_saspay --appliquer  # le fait

Grille décidée le 16/10/2026 : les prix des salons en Chine, convertis au
taux du 15/10/2026 (1 USD = 6,7065 CNY), puis arrondis. Les montants sont
écrits ici en clair, pas recalculés depuis un taux du jour : un tarif ne
bouge que par une décision, jamais par une variation de change.

  - USD, XAF, XOF : les montants validés par l'utilisateur ;
  - autres devises : deux chiffres significatifs pour le mois, l'année à
    dix mois (deux mois offerts, comme en CNY : 999 pour 12 × 99).

Sans risque à rejouer : un tarif déjà présent n'est **jamais** modifié (il est
signalé s'il diffère de la grille), un moyen déjà présent n'est pas recréé.
"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.billing import saspay
from apps.billing.models import Plan, PlanPrice, PlatformPaymentMethod
from apps.common.db import bypass_tenant_context

# devise : (Standard mois, Standard an, Pro mois, Pro an)
GRILLE = {
    "USD": (15, 149, 59, 599),
    "XAF": (9_000, 90_000, 35_000, 350_000),
    "XOF": (9_000, 90_000, 35_000, 350_000),
    "CDF": (34_000, 340_000, 140_000, 1_400_000),
    "GHS": (170, 1_700, 700, 7_000),
    "GNF": (130_000, 1_300_000, 520_000, 5_200_000),
    "KES": (1_900, 19_000, 7_700, 77_000),
    "MWK": (26_000, 260_000, 100_000, 1_000_000),
    "NGN": (20_000, 200_000, 79_000, 790_000),
    "RWF": (22_000, 220_000, 88_000, 880_000),
    "TZS": (39_000, 390_000, 160_000, 1_600_000),
    "UGX": (59_000, 590_000, 240_000, 2_400_000),
    "ZMW": (290, 2_900, 1_200, 12_000),
}
OFFRES = (Plan.Code.MONTHLY, Plan.Code.YEARLY, Plan.Code.PRO_MONTHLY, Plan.Code.PRO_YEARLY)


def devises_du_pays(pays: str) -> list[str]:
    """Mobile Money dans la devise du pays d'abord, puis la carte en USD."""
    return [saspay.MOBILE_MONEY[pays], saspay.DEVISE_CARTE]


class Command(BaseCommand):
    help = "Crée les tarifs et les moyens SASPAY des pays couverts (sans rien écraser)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--appliquer", action="store_true", help="Écrire en base (sinon : aperçu seulement)."
        )
        parser.add_argument(
            "--pays",
            nargs="+",
            metavar="CODE",
            help="Limiter à ces pays (par défaut : tous les pays SASPAY).",
        )

    def handle(self, *args, appliquer=False, pays=None, **options):
        cibles = sorted(saspay.PAYS_COUVERTS if not pays else {p.upper() for p in pays})
        inconnus = [p for p in cibles if p not in saspay.PAYS_COUVERTS]
        if inconnus:
            self.stderr.write(f"Pays non couverts par SASPAY : {', '.join(inconnus)}")
            return
        devises = sorted({d for p in cibles for d in devises_du_pays(p)})

        with bypass_tenant_context(), transaction.atomic():
            offres = {p.code: p for p in Plan.objects.filter(code__in=OFFRES)}
            manquantes = [c for c in OFFRES if c not in offres]
            if manquantes:
                self.stderr.write(f"Offres absentes : {', '.join(manquantes)}")
                return

            self.stdout.write(self.style.MIGRATE_HEADING("Tarifs"))
            for devise in devises:
                for code, montant in zip(OFFRES, GRILLE[devise], strict=True):
                    montant = Decimal(montant)
                    existant = PlanPrice.objects.filter(plan=offres[code], currency=devise).first()
                    if existant is None:
                        if appliquer:
                            PlanPrice.objects.create(
                                plan=offres[code], currency=devise, amount=montant, active=True
                            )
                        self.stdout.write(f"  + {code:<12} {montant:>12,} {devise}")
                    elif existant.amount != montant:
                        self.stdout.write(
                            self.style.WARNING(
                                f"  ! {code:<12} {existant.amount:>12,} {devise} conservé "
                                f"(grille : {montant:,})"
                            )
                        )
                    else:
                        self.stdout.write(f"  = {code:<12} {montant:>12,} {devise}")

            self.stdout.write(self.style.MIGRATE_HEADING("Moyens SASPAY"))
            position = (
                PlatformPaymentMethod.objects.order_by("-position")
                .values_list("position", flat=True)
                .first()
                or 0
            )
            for code_pays in cibles:
                for devise in devises_du_pays(code_pays):
                    moyen = PlatformPaymentMethod.objects.filter(
                        kind=PlatformPaymentMethod.Kind.SASPAY, country=code_pays, currency=devise
                    ).first()
                    if moyen:
                        etat = "actif" if moyen.active else "inactif, laissé tel quel"
                        self.stdout.write(f"  = {code_pays} {devise} ({etat})")
                        continue
                    position += 1
                    if appliquer:
                        PlatformPaymentMethod.objects.create(
                            kind=PlatformPaymentMethod.Kind.SASPAY,
                            provider_name="SASPAY",
                            country=code_pays,
                            currency=devise,
                            active=True,
                            position=position,
                        )
                    canal = saspay.canal(code_pays, devise).replace("_", " ")
                    self.stdout.write(f"  + {code_pays} {devise} ({canal})")

            if not appliquer:
                transaction.set_rollback(True)
                self.stdout.write(
                    self.style.NOTICE("\nAperçu seulement : relancer avec --appliquer pour écrire.")
                )
                return

        if not saspay.disponible():
            self.stdout.write(
                self.style.WARNING(
                    "SASPAY est désactivé ou incomplet sur ce serveur : ces moyens "
                    "n'apparaîtront qu'une fois les clés et le secret du webhook renseignés."
                )
            )
        self.stdout.write(self.style.SUCCESS("SASPAY ouvert."))
