"""Remplit un salon de données de démonstration cohérentes.

---------------------------------------------------------------------------
À quoi ça sert, et à quoi ça ne sert pas
---------------------------------------------------------------------------

À voir le produit tourner : un mini-site vide ne dit rien de ce qu'il sera
une fois rempli, et une capture d'écran d'un catalogue à trois lignes ne
convainc personne. Cette commande pose de quoi juger — quatre prestations au
moins par section, des options, des fournitures, une boutique, des horaires.

Elle ne sert **pas** à amorcer un salon réel. Les prestations et les tarifs
qu'elle écrit sont inventés ; un salon qui les garderait vendrait des choses
qu'il ne fait pas. D'où le nom des articles, volontairement génériques, et le
refus par défaut d'écrire dans un salon qui a déjà un catalogue.

    uv run python manage.py peupler_salon blondrose
    uv run python manage.py peupler_salon blondrose --remplacer

---------------------------------------------------------------------------
Pourquoi `get_or_create` partout
---------------------------------------------------------------------------

Pour pouvoir la relancer. Une commande de démonstration qu'on n'ose relancer
qu'une fois finit par n'être lancée jamais — on préfère cliquer à la main
plutôt que risquer des doublons.
"""

from datetime import time
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.catalog.models import Service, ServiceCategory, ServiceOption
from apps.common.db import tenant_context
from apps.salons.models import SalonProfile, TravelZone
from apps.scheduling.models import BusinessHours
from apps.staff.models import StaffMember, StaffService
from apps.store.models import Product, Requirement, RequirementProduct
from apps.tenants.models import Tenant

OK = "  [ok]  "
INFO = "        "


# Le catalogue : quatre catégories, quatre prestations chacune.
#
# Les durées sont réalistes — une pose de box braids prend bien quatre heures
# — parce que c'est ce qui rend la grille de créneaux crédible. Des durées de
# trente minutes partout donneraient un agenda qui ne ressemble à aucun salon.
CATALOGUE = [
    (
        "Tresses et nattes",
        [
            ("Box braids", 240, "25000", "5000"),
            ("Twists sénégalais", 180, "18000", "3000"),
            ("Cornrows", 120, "12000", "0"),
            ("Fulani braids", 210, "22000", "4000"),
        ],
    ),
    (
        "Perruques et tissages",
        [
            ("Pose de perruque", 90, "15000", "3000"),
            ("Closure sur mesure", 150, "28000", "6000"),
            ("Tissage complet", 180, "32000", "6000"),
            ("Révision de perruque", 60, "8000", "0"),
        ],
    ),
    (
        "Soin du cheveu",
        [
            ("Soin profond", 60, "8000", "0"),
            ("Défrisage", 90, "14000", "0"),
            ("Coupe et brushing", 45, "6000", "0"),
            ("Rituel hydratation", 75, "11000", "0"),
        ],
    ),
    (
        "Ongles",
        [
            ("Pose de gel", 90, "12000", "0"),
            ("Manucure classique", 45, "5000", "0"),
            ("Nail art", 60, "9000", "0"),
            ("Dépose et soin", 30, "4000", "0"),
        ],
    ),
]

# Les options : un supplément de prix, et surtout de temps.
#
# Le temps compte autant que le prix : il entre dans la recherche de créneau.
# Une option qui rallonge la pose d'une heure sans le dire produit un
# rendez-vous suivant qu'on ne peut pas tenir.
OPTIONS = {
    "Box braids": [
        ("Mèches XXL", "Jusqu'à la taille", "4000", 60),
        ("Motif aux tempes", "Dessin au choix", "2000", 20),
        ("Perles et anneaux", "", "1500", 15),
    ],
    "Twists sénégalais": [
        ("Mèches colorées", "Une ou deux teintes", "2500", 0),
        ("Frange", "", "1500", 20),
    ],
    "Pose de perruque": [
        ("Personnalisation des baby hairs", "", "2000", 20),
        ("Coupe sur mesure", "Adaptée à votre visage", "3000", 30),
    ],
    "Soin profond": [
        ("Masque au karité", "", "1500", 15),
        ("Massage du cuir chevelu", "10 minutes", "1000", 10),
    ],
    "Pose de gel": [
        ("Couleur unie", "", "0", 0),
        ("French manucure", "", "1500", 15),
        ("Strass", "Sur deux ongles", "1000", 10),
    ],
}

STAFF = [
    ("Fatou Nkounkou", "Tresses et nattes africaines"),
    ("Chantal Kouka", "Perruques et tissages"),
    ("Awa Diallo", "Soin du cheveu et défrisage"),
    ("Espoir Moukendi", "Ongles et nail art"),
]

# La boutique : ce qu'on vend au comptoir, avec des stocks variés.
#
# Un article en rupture et un article sous le seuil d'alerte sont volontaires :
# c'est ce qui permet de voir à quoi ressemblent ces deux états sans devoir
# vider un stock à la main.
BOUTIQUE = [
    ("Mèches Kanekalon", "Paquet de 3, longueur 24 pouces", "3500", "pack", 24),
    ("Mèches Xpression", "Qualité premium, 26 pouces", "4500", "pack", 8),
    ("Bonnet en satin", "Protège la coiffure la nuit", "2500", "piece", 2),
    ("Huile de ricin", "Flacon 100 ml, pressée à froid", "3000", "piece", None),
    ("Gel fixateur", "Tenue longue durée, sans alcool", "2000", "piece", 0),
    ("Filet à cheveux", "Lot de 5", "1500", "pack", 40),
]

# Ce qu'il faut prévoir, et ce que le salon propose à la place.
FOURNITURES = [
    ("Box braids", "3 paquets de mèches", "24 pouces, couleur au choix", True,
     ["Mèches Kanekalon", "Mèches Xpression"]),
    ("Twists sénégalais", "2 paquets de mèches", "", True, ["Mèches Kanekalon"]),
    ("Pose de perruque", "Votre perruque", "Ou choisissez-en une au salon", False, []),
    ("Soin profond", "Rien à prévoir", "Tout est fourni", False, []),
]

# Moyens d'encaissement.
#
# Sans au moins un, le parcours d'acompte ne s'ouvre pas : `needs_payment`
# exige une prestation avec acompte **et** un moyen affichable, et la cliente
# lit « le salon vous indiquera comment regler » au lieu de voir un QR code.
# Un salon de demonstration sans moyen de paiement ne demontre donc pas la
# moitie du produit.
#
# Les consignes suffisent a les rendre affichables : un `PaymentChannel` est
# utilisable des qu'il porte un QR **ou** une consigne. On n'invente pas de
# QR code - il n'y a rien a scanner derriere.
MOYENS = [
    ("wechat", "Beauty Salon Demo", "Mettez votre nom en commentaire du virement."),
    ("alipay", "Beauty Salon Demo", "Envoyez la capture une fois le paiement fait."),
]

ZONES = [
    ("Centre-ville", "2000"),
    ("Bacongo", "3000"),
    ("Poto-Poto", "3000"),
    ("Moungali", "4000"),
]


class Command(BaseCommand):
    help = "Remplit un salon de données de démonstration."

    def add_arguments(self, parser):
        parser.add_argument("slug", help="Sous-domaine du salon.")
        parser.add_argument(
            "--remplacer",
            action="store_true",
            help="Écrase le catalogue existant au lieu de refuser.",
        )

    def handle(self, *args, **options):
        slug = options["slug"]
        try:
            tenant = Tenant.objects.get(slug=slug)
        except Tenant.DoesNotExist as exc:
            raise CommandError(f"Aucun salon « {slug} ».") from exc

        with tenant_context(tenant.id):
            existant = Service.objects.count()

            # Par defaut, on complete ce qui manque plutot que de refuser.
            #
            # Tout passe par `get_or_create` : relancer la commande n'ecrase
            # jamais rien, elle ajoute ce qui n'est pas la. Refuser au motif
            # qu'un catalogue existe obligeait a passer `--remplacer`, donc a
            # tout detruire, pour ajouter deux moyens de paiement oublies.
            if existant and not options["remplacer"]:
                self.stdout.write(
                    f"{INFO} {existant} prestations déjà là : on complète ce "
                    "qui manque, rien n'est écrasé."
                )

            if existant and options["remplacer"]:
                # On ne touche ni aux rendez-vous ni aux clientes : écraser un
                # catalogue est une chose, effacer l'historique en est une
                # autre, et personne ne l'a demandé ici.
                from django.db.models import ProtectedError

                try:
                    ServiceOption.objects.all().delete()
                    RequirementProduct.objects.all().delete()
                    Requirement.objects.all().delete()
                    StaffService.objects.all().delete()
                    Service.objects.all().delete()
                    ServiceCategory.objects.all().delete()
                    Product.objects.all().delete()
                except ProtectedError as exc:
                    # Une prestation reservee ne se supprime pas, et c'est la
                    # bonne regle : effacer la prestation d'un rendez-vous
                    # passe rendrait l'historique du salon illisible.
                    raise CommandError(
                        "Des rendez-vous s'appuient sur ce catalogue : il ne "
                        "peut pas être écrasé. Relancez sans --remplacer pour "
                        "compléter ce qui manque, ou supprimez d'abord les "
                        "rendez-vous concernés."
                    ) from exc

                self.stdout.write(f"{INFO} catalogue précédent effacé")

            with transaction.atomic():
                self._profil(tenant)
                services = self._catalogue(tenant)
                self._options(tenant, services)
                staff = self._equipe(tenant, services)
                produits = self._boutique(tenant)
                self._fournitures(tenant, services, produits)
                self._horaires(tenant)
                self._zones(tenant)
                self._moyens(tenant)

            self.stdout.write("")
            self.stdout.write(
                self.style.SUCCESS(
                    f"{tenant.name} est rempli : "
                    f"{Service.objects.count()} prestations, "
                    f"{len(staff)} prestataires, "
                    f"{Product.objects.count()} articles."
                )
            )

    # -- sections ---------------------------------------------------------

    def _profil(self, tenant):
        profile, _ = SalonProfile.objects.get_or_create(tenant=tenant)
        if not profile.description:
            profile.description = (
                "Tresses, perruques sur mesure et soin du cheveu afro. "
                "Sur rendez-vous, en français, en lingala et en anglais."
            )
            profile.late_tolerance_minutes = 15
            profile.late_policy = (
                "Nous faisons notre possible pour vous prendre quand même, "
                "mais la prestation peut être raccourcie."
            )
            profile.save()
        self.stdout.write(f"{OK} profil")

    def _catalogue(self, tenant) -> dict[str, Service]:
        services: dict[str, Service] = {}
        for rang, (nom_cat, prestations) in enumerate(CATALOGUE):
            categorie, _ = ServiceCategory.objects.get_or_create(
                tenant=tenant, name=nom_cat, defaults={"position": rang}
            )
            for place, (nom, minutes, prix, acompte) in enumerate(prestations):
                service, _ = Service.objects.get_or_create(
                    tenant=tenant,
                    name=nom,
                    defaults={
                        "category": categorie,
                        "duration_minutes": minutes,
                        "price_amount": Decimal(prix),
                        # L'acompte ne se chiffre plus ici : la fiche du
                        # salon porte le taux et le plancher. Le catalogue ne
                        # dit que « oui » ou « non ».
                        "requires_deposit": Decimal(acompte) > 0,
                        "position": place,
                        "active": True,
                    },
                )
                services[nom] = service
        self.stdout.write(f"{OK} {len(services)} prestations en {len(CATALOGUE)} catégories")
        return services

    def _options(self, tenant, services):
        total = 0
        for nom_service, liste in OPTIONS.items():
            service = services.get(nom_service)
            if service is None:
                continue
            for place, (nom, detail, prix, minutes) in enumerate(liste):
                ServiceOption.objects.get_or_create(
                    tenant=tenant,
                    service=service,
                    name=nom,
                    defaults={
                        "description": detail,
                        "price_delta": Decimal(prix),
                        "duration_delta_minutes": minutes,
                        "position": place,
                    },
                )
                total += 1
        self.stdout.write(f"{OK} {total} options")

    def _equipe(self, tenant, services):
        membres = []
        for rang, (nom, specialite) in enumerate(STAFF):
            membre, _ = StaffMember.objects.get_or_create(
                tenant=tenant,
                name=nom,
                defaults={"specialty": specialite, "active": True, "position": rang},
            )
            membres.append(membre)

        # Chacun sait tout faire : sans rattachement, aucune prestation n'est
        # réservable, et une démonstration où l'on ne peut rien réserver ne
        # démontre rien.
        for membre in membres:
            for service in services.values():
                StaffService.objects.get_or_create(
                    tenant=tenant, staff_member=membre, service=service
                )
        self.stdout.write(f"{OK} {len(membres)} prestataires, tous rattachés au catalogue")
        return membres

    def _boutique(self, tenant) -> dict[str, Product]:
        produits: dict[str, Product] = {}
        for rang, (nom, detail, prix, unite, stock) in enumerate(BOUTIQUE):
            produit, _ = Product.objects.get_or_create(
                tenant=tenant,
                name=nom,
                defaults={
                    "description": detail,
                    "price": Decimal(prix),
                    "unit": unite,
                    "stock": stock,
                    "position": rang,
                    "active": True,
                },
            )
            produits[nom] = produit
        self.stdout.write(f"{OK} {len(produits)} articles en boutique")
        return produits

    def _fournitures(self, tenant, services, produits):
        total = 0
        for rang, (nom_service, libelle, detail, obligatoire, articles) in enumerate(
            FOURNITURES
        ):
            service = services.get(nom_service)
            if service is None:
                continue
            exigence, _ = Requirement.objects.get_or_create(
                tenant=tenant,
                service=service,
                label=libelle,
                defaults={
                    "detail": detail,
                    "mandatory": obligatoire,
                    "position": rang,
                },
            )
            for nom_article in articles:
                produit = produits.get(nom_article)
                if produit:
                    RequirementProduct.objects.get_or_create(
                        tenant=tenant, requirement=exigence, product=produit
                    )
            total += 1
        self.stdout.write(f"{OK} {total} fournitures à prévoir")

    def _horaires(self, tenant):
        # Mardi au samedi, avec coupure du midi : c'est la grille la plus
        # courante, et la coupure est ce qui rend la grille de créneaux
        # intéressante à regarder.
        cree = 0
        for jour in range(1, 6):
            for debut, fin in ((time(9, 0), time(13, 0)), (time(14, 0), time(18, 30))):
                _, neuf = BusinessHours.objects.get_or_create(
                    tenant=tenant,
                    staff_member=None,
                    weekday=jour,
                    starts_at=debut,
                    defaults={"ends_at": fin},
                )
                cree += int(neuf)
        self.stdout.write(f"{OK} horaires du mardi au samedi ({cree} plages)")

    def _moyens(self, tenant):
        from apps.payments.models import PaymentChannel

        for rang, (genre, compte, consigne) in enumerate(MOYENS):
            PaymentChannel.objects.get_or_create(
                tenant=tenant,
                kind=genre,
                defaults={
                    "account_name": compte,
                    "instructions": consigne,
                    "active": True,
                    "position": rang,
                },
            )
        self.stdout.write(f"{OK} {len(MOYENS)} moyens de paiement")

    def _zones(self, tenant):
        for rang, (nom, frais) in enumerate(ZONES):
            TravelZone.objects.get_or_create(
                tenant=tenant,
                name=nom,
                defaults={"fee_amount": Decimal(frais), "position": rang, "active": True},
            )
        self.stdout.write(f"{OK} {len(ZONES)} zones de déplacement")
