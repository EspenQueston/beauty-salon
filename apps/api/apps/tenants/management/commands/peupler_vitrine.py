"""Remplit la *vitrine* d'un salon de démonstration : ce que voit une visiteuse.

---------------------------------------------------------------------------
Sa place à côté de `peupler_salon`
---------------------------------------------------------------------------

`peupler_salon` pose la mécanique : un catalogue, des horaires, des articles,
de quoi réserver. Elle s'arrête là où commence le mini-site — pas de photos,
pas de page « À propos », pas de réseaux sociaux, pas un seul avis, aucun
rendez-vous dans l'agenda.

Or c'est précisément ce qui manque pour juger le produit. Un mini-site sans
portraits montre quatre initiales ; sans avis, la section n'apparaît même
pas ; sans rendez-vous, l'agenda du tableau de bord est une grille vide. On
peut donc livrer une régression d'affichage sans jamais la voir.

Cette commande pose cette couche-là, et seulement elle.

    uv run python manage.py peupler_vitrine nailsbyfaty
    uv run python manage.py peupler_vitrine blondrose --portraits
    uv run python manage.py peupler_vitrine blondrose nailsbyfaty

---------------------------------------------------------------------------
Ce qu'elle n'est pas
---------------------------------------------------------------------------

Un amorçage de salon réel. Les noms de clientes, les numéros, les avis et
les rendez-vous sont **inventés**. Les numéros de téléphone sont en
`+86 138 0000 00xx` et les adresses e-mail en `@example.com` — deux plages
réservées à la documentation, qui ne joignent personne. Les comptes de
réseaux sociaux portent le suffixe `.demo`.

Les photographies viennent de Pexels, dont la licence autorise cet usage.
Elles sont importées par `fetch_remote_media`, la même fonction que le
bouton « coller une adresse » du tableau de bord : mêmes garde-fous, même
recopie chez nous, aucun code de téléchargement en double.

---------------------------------------------------------------------------
Quand le poste est derrière un tunnel
---------------------------------------------------------------------------

`fetch_remote_media` résout le nom de domaine et refuse toute adresse non
publique — c'est ce qui empêche un salon de faire lire `169.254.169.254` à
notre serveur. Or un client VPN qui détourne le DNS (WARP, Clash, Tailscale)
répond `198.18.x.x` pour *tous* les domaines, y compris `images.pexels.com`.
Le garde-fou fait alors exactement son travail, et la commande n'a plus
aucune photo.

D'où `--photos`, qui lit un dossier local au lieu du réseau. Les fichiers y
sont nommés d'après l'identifiant Pexels — `28582416.jpg` — et se récupèrent
avec la même adresse que celle construite plus bas :

    for id in 28582416 4045708 36322503 29991205 29086752 28513246 \\
              5386463 7016799 34997574 34885844 34835304 3997384 \\
              6135675 4530187 3631691 29229021 20849460 12684691; do
      curl -sL -o "$id.jpg" \\
        "https://images.pexels.com/photos/$id/pexels-photo-$id.jpeg?auto=compress&cs=tinysrgb&w=1000"
    done

L'option ne désactive rien côté produit : elle ne concerne que cette
commande de développement.

---------------------------------------------------------------------------
Pourquoi le jeu de données est indexé par sous-domaine
---------------------------------------------------------------------------

Parce qu'il est *écrit pour* ces salons-là. « by Faty » vend des ongles à
Guangzhou et facture en yuans ; lui poser le catalogue de tresses de
`peupler_salon` produirait un salon qui vend des box braids sous une enseigne
de manucure. Une fixture de démonstration qui ne tient pas debout ne
démontre rien : on passe son temps à expliquer ce qu'il faut ignorer.

Tout passe par `get_or_create` : la commande se relance sans rien écraser.
"""

from datetime import datetime, time, timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.catalog.models import Service, ServiceCategory, ServiceOption
from apps.common.db import tenant_context
from apps.customers.models import Customer
from apps.media.fetch import RemoteMediaError, fetch_remote_media
from apps.media.models import MediaAsset
from apps.payments.models import PaymentChannel
from apps.reviews.models import Review
from apps.salons.models import SalonProfile, ServiceMode, TravelZone
from apps.scheduling.models import Booking, BusinessHours
from apps.staff.models import StaffMember, StaffService
from apps.store.models import Product, Requirement, RequirementProduct
from apps.tenants.models import Tenant

OK = "  [ok]  "
INFO = "        "


def pexels(identifiant: int, largeur: int) -> str:
    """Adresse d'un cliché Pexels, redimensionné à la source.

    On demande la largeur utile plutôt que l'original : un portrait affiché
    sur 180 px n'a pas besoin de 6 000. C'est aussi ce que fait une gérante
    qui colle une adresse — elle prend le lien de la page, pas le fichier
    brut de 12 Mo que `fetch_remote_media` refuserait.
    """
    return (
        f"https://images.pexels.com/photos/{identifiant}/"
        f"pexels-photo-{identifiant}.jpeg?auto=compress&cs=tinysrgb&w={largeur}"
    )


# ---------------------------------------------------------------------------
# Les portraits
# ---------------------------------------------------------------------------
#
# Attribués par *nom* et non par rang : l'ordre des prestataires change dès
# qu'on en archive un, et une photo qui se déplace d'une personne à l'autre
# entre deux exécutions est exactement le genre de bizarrerie qu'on met une
# heure à comprendre.
PORTRAITS = {
    "blondrose": {
        "Fatou Nkounkou": (28582416, "Fatou, tresses et nattes"),
        "Chantal Kouka": (4045708, "Chantal, perruques et tissages"),
        "Awa Diallo": (36322503, "Awa, soin du cheveu"),
        "Espoir Moukendi": (29991205, "Espoir, ongles et nail art"),
    },
    "nailsbyfaty": {
        "Faty Nguesso": (29086752, "Faty, nail art et pose gel"),
        "Mireille Bantsimba": (28513246, "Mireille, manucure"),
        "Lin Xiaowen": (5386463, "Lin, pédicure et soin des pieds"),
        "Grâce Loubaki": (7016799, "Grâce, baby hair et finitions"),
    },
}


# ---------------------------------------------------------------------------
# « by Faty » — salon d'ongles, Guangzhou, yuans
# ---------------------------------------------------------------------------

FATY_IDENTITE = {
    "description": (
        "Ongles, nail art et baby hair, à Tianhe. Sur rendez-vous, "
        "en français, en lingala et en mandarin."
    ),
    "address": "Room 1204, Tianxiu Building, 228 Tianhe Road",
    "city": "Guangzhou",
    "service_mode": ServiceMode.HYBRID,
    "service_area": "Tianhe, Yuexiu, Haizhu",
    "latitude": Decimal("23.135800"),
    "longitude": Decimal("113.324500"),
    "phone": "+86 138 0000 0012",
    "whatsapp_number": "+86 138 0000 0012",
    # Le suffixe `.demo` rend la collision avec un vrai pseudonyme à peu près
    # impossible, et signale du premier coup d'œil que le lien est factice.
    #
    # WeChat n'est pas dans cette liste : il ne se rejoint pas par une
    # adresse. Son identifiant et son QR ont leurs propres champs, plus bas.
    "social_links": {
        "instagram": "https://www.instagram.com/byfaty.demo/",
        "tiktok": "https://www.tiktok.com/@byfaty.demo",
        "facebook": "https://www.facebook.com/byfaty.demo",
    },
    # L'identifiant WeChat. Le QR qui l'accompagne est fabrique plus bas
    # plutot que telecharge : un vrai QR de contact WeChat pointe vers un
    # vrai compte, et on n'en invente pas.
    "wechat_id": "byfaty-demo-gz",
    "cancellation_policy": (
        "Prévenez-nous au moins 24 h avant et l'acompte est reporté sur votre "
        "prochain rendez-vous. En deçà, il reste acquis au salon : le créneau "
        "ne se remplit plus."
    ),
    "cancellation_deadline_hours": 24,
    # Sans taux ni plancher, les prestations marquées « acompte » en
    # demandent zéro : la page de paiement ne s'ouvre jamais et la moitié du
    # parcours reste invisible. Le champ vaut 0 par défaut, donc il compte
    # comme vide et sera complété.
    "deposit_rate": 30,
    "deposit_minimum": Decimal("50.00"),
    "late_tolerance_minutes": 15,
    "late_policy": (
        "Au-delà de quinze minutes, la pose peut être raccourcie pour ne pas "
        "décaler la cliente suivante."
    ),
}

FATY_ABOUT_TITLE = "Des ongles faits main, à Tianhe"

FATY_ABOUT = """\
by Faty est né d'une frustration : à Guangzhou, une pose gel correcte se
trouvait, mais il fallait expliquer trois fois ce qu'on voulait, et repartir
avec autre chose.

Faty Nguesso a ouvert en 2021, dans une pièce du Tianxiu Building, avec une
lampe UV et un carnet de rendez-vous en papier. Les premières clientes
venaient de la communauté congolaise de Xiaobei ; elles revenaient avec des
photos trouvées sur Instagram, et repartaient avec exactement ça.

Nous sommes quatre aujourd'hui, et nous recevons en français, en lingala et
en mandarin. Ce n'est pas un argument commercial : c'est ce qui permet de
comprendre ce qu'une cliente veut vraiment quand elle décrit une forme
d'ongle.

Le nail art est notre spécialité. Un modèle complet demande une heure, parfois
plus, et nous ne l'écourtons pas. Un tracé bâclé s'écaille en une semaine au
lieu de trois — et c'est la cliente qui revient, pas le temps gagné.

Nous nous déplaçons aussi à domicile dans Tianhe, Yuexiu et Haizhu, pour les
mariages et les veilles de fête.
"""

# Le catalogue vient *compléter* les trois prestations déjà saisies à la main
# — manicure, pedicure, baby hair. On n'y touche pas : ce sont les vraies, et
# elles portent les prix que la gérante a choisis.
FATY_CATALOGUE = [
    (
        "ongles",
        [
            ("Pose gel couleur", 90, "280", True),
            ("Remplissage gel", 75, "200", True),
            ("Dépose et soin des mains", 30, "80", False),
        ],
    ),
    (
        "Nail art",
        [
            ("Nail art deux ongles", 30, "60", False),
            ("Nail art intégral", 60, "180", True),
            ("Bijoux d'ongles et strass", 20, "50", False),
        ],
    ),
]

FATY_OPTIONS = {
    "Pose gel couleur": [
        ("French manucure", "Finition classique", "40", 15),
        ("Ongles XL", "Rallongement au chablon", "60", 20),
    ],
    "Nail art intégral": [
        ("Feuille d'or", "Sur deux ongles", "50", 10),
        ("Effet chrome", "", "40", 10),
    ],
    "manicure": [
        ("Vernis semi-permanent", "Tient trois semaines", "60", 20),
    ],
}

# Un article en rupture et un en stock illimité : ce sont les deux états qu'on
# ne voit jamais tant qu'on ne vide pas un stock à la main.
FATY_BOUTIQUE = [
    ("Vernis semi-permanent", "Flacon 10 ml, trente teintes au choix",
     "90", "piece", 24, 3631691),
    ("Huile à cuticules", "Roll-on 5 ml, amande douce",
     "45", "piece", 6, 20849460),
    ("Top coat brillance", "Finition longue tenue, sans lampe",
     "60", "piece", 0, 12684691),
    ("Kit lime et repousse-cuticules", "Pour l'entretien entre deux poses",
     "120", "piece", None, 29229021),
]

FATY_FOURNITURES = [
    ("Pose gel couleur", "Vos mains sans vernis",
     "Venez dépose faite si vous le pouvez", False, ["Huile à cuticules"]),
    ("Nail art intégral", "Votre modèle", "Une photo suffit", False, []),
]

FATY_ZONES = [("Tianhe", "50"), ("Yuexiu", "80"), ("Haizhu", "80")]

FATY_MOYENS = [
    ("wechat", "by Faty", "Mettez votre prénom en commentaire du virement."),
    ("alipay", "by Faty", "Envoyez la capture une fois le paiement fait."),
]

FATY_EQUIPE = [
    ("Faty Nguesso", "Nail art et pose gel",
     "Fondatrice. Douze ans de métier, dont quatre à Brazzaville. "
     "Elle prend les modèles compliqués, ceux qu'on apporte en photo."),
    ("Mireille Bantsimba", "Manucure et soin des mains",
     "La plus rapide de l'équipe sur une manucure classique, "
     "et la plus patiente sur une dépose abîmée."),
    ("Lin Xiaowen", "Pédicure et soin des pieds",
     "Formée à Shenzhen. Elle reçoit en mandarin et en anglais."),
    ("Grâce Loubaki", "Baby hair et finitions",
     "Arrivée en 2023. Elle s'occupe des baby hair et des retouches "
     "avant les mariages."),
]

FATY_GALERIE = [
    (34997574, "French manucure et bagues dorées", True),
    (34885844, "Nail art rose, tracé à la main", True),
    (34835304, "Ongles noirs et motif léopard", True),
    (3997384, "Manucure rouge en cabine", False),
    (6135675, "Pose en cours au salon", False),
    (4530187, "Le tracé, au pinceau fin", False),
]

# Les clientes. Numéros en +86 138 0000 00xx et adresses en @example.com :
# deux plages réservées, qui ne joignent personne si un envoi part par erreur.
FATY_CLIENTES = [
    ("Aminata Sow", "+86 138 0000 0021", "aminata.sow@example.com"),
    ("Chen Jiaying", "+86 138 0000 0022", "chen.jiaying@example.com"),
    ("Prudence Mabiala", "+86 138 0000 0023", ""),
    ("Lisa Kouassi", "+86 138 0000 0024", "lisa.kouassi@example.com"),
]

# Les rendez-vous, en jours par rapport à maintenant.
#
#   (jours, heure, prestation, prestataire, cliente, statut, extras)
#
# Trois passés et terminés — ce sont eux qui portent les avis —, un annulé,
# et trois à venir couvrant les trois états vivants : confirmé, en attente de
# paiement, demandé. C'est le jeu minimal pour que l'agenda, la page de suivi
# et l'espace cliente montrent chacun quelque chose de différent.
FATY_RENDEZVOUS = [
    (-21, time(10, 0), "manicure", "Mireille Bantsimba", "Aminata Sow",
     Booking.Status.COMPLETED, {"acompte_paye": True}),
    (-14, time(14, 30), "Pose gel couleur", "Faty Nguesso", "Chen Jiaying",
     Booking.Status.COMPLETED,
     {"acompte_paye": True, "options": ["French manucure"],
      "articles": [("Vernis semi-permanent", 1)]}),
    # Une visite a domicile deja honoree : c'est la seule facon de voir la
    # recette « Deplacement » apparaitre dans l'ecran Finances, a cote de la
    # depense de transport qu'elle est censee couvrir.
    (-7, time(11, 0), "pedicure", "Lin Xiaowen", "Prudence Mabiala",
     Booking.Status.COMPLETED,
     {"acompte_paye": True, "zone": "Yuexiu",
      "adresse": "48 Beijing Road, Yuexiu",
      "note": "Portail vert, sonner deux fois."}),
    (-5, time(16, 0), "Nail art intégral", "Faty Nguesso", "Lisa Kouassi",
     Booking.Status.CANCELLED,
     {"motif": "Empêchement de dernière minute, reportée par téléphone."}),
    (2, time(10, 30), "Pose gel couleur", "Faty Nguesso", "Aminata Sow",
     Booking.Status.CONFIRMED,
     {"acompte_paye": True, "articles": [("Huile à cuticules", 1)]}),
    (5, time(15, 0), "Nail art intégral", "Grâce Loubaki", "Chen Jiaying",
     Booking.Status.PENDING_PAYMENT, {}),
    (9, time(9, 30), "baby hair", "Grâce Loubaki", "Lisa Kouassi",
     Booking.Status.REQUESTED,
     {"zone": "Tianhe", "adresse": "12 Xingsheng Road, Tianhe",
      "note": "Deuxième étage, l'interphone ne marche pas."}),
]

# Les avis, rattachés aux trois visites terminées.
#
#   (cliente, note d'ensemble, {critères}, commentaire)
#
# Pas que des 5 : une page d'avis où tout le monde met la note maximale ne
# ressemble à aucun salon réel, et on ne verrait jamais à quoi ressemble une
# note moyenne dans la grille.
FATY_AVIS = [
    ("Aminata Sow", {"result": 5, "welcome": 5, "punctuality": 4,
                     "cleanliness": 5, "value": 5},
     "Manucure impeccable et on m'a reçue à l'heure ou presque. "
     "Je reviens tous les mois maintenant."),
    ("Chen Jiaying", {"result": 5, "welcome": 4, "punctuality": 3,
                      "cleanliness": 4, "value": 4},
     "Le résultat est exactement la photo que j'avais apportée. "
     "Une demi-heure d'attente en revanche, prévoyez large."),
    ("Prudence Mabiala", {"result": 5, "welcome": 5, "punctuality": 5,
                          "cleanliness": 5, "value": 4},
     "Première pédicure ici, je ne changerai plus. Lin prend son temps "
     "et explique ce qu'elle fait."),
]


class Command(BaseCommand):
    help = "Remplit la vitrine d'un salon de démonstration (photos, avis, agenda)."

    def add_arguments(self, parser):
        parser.add_argument("slugs", nargs="+", help="Sous-domaines des salons.")
        parser.add_argument(
            "--portraits",
            action="store_true",
            help="Ne pose que les photos des prestataires.",
        )
        parser.add_argument(
            "--photos",
            default="",
            metavar="DOSSIER",
            help=(
                "Lit les clichés dans ce dossier (fichiers « <id Pexels>.jpg ») "
                "au lieu de les télécharger. Utile derrière un VPN qui détourne "
                "le DNS."
            ),
        )

    def handle(self, *args, **options):
        self.dossier_photos = Path(options["photos"]) if options["photos"] else None
        if self.dossier_photos and not self.dossier_photos.is_dir():
            raise CommandError(f"Dossier introuvable : {self.dossier_photos}")

        for slug in options["slugs"]:
            try:
                tenant = Tenant.objects.get(slug=slug)
            except Tenant.DoesNotExist as exc:
                raise CommandError(f"Aucun salon « {slug} ».") from exc

            if slug not in PORTRAITS:
                raise CommandError(
                    f"« {slug} » ne fait pas partie des salons de démonstration. "
                    f"Connus : {', '.join(sorted(PORTRAITS))}."
                )

            self.stdout.write("")
            self.stdout.write(self.style.MIGRATE_HEADING(f"{tenant.name} ({slug})"))

            with tenant_context(tenant.id):
                if slug == "nailsbyfaty" and not options["portraits"]:
                    # Les imports d'images restent *hors* transaction : dix
                    # téléchargements de trois secondes tiendraient une
                    # transaction ouverte une demi-minute, et un lien mort
                    # ferait perdre le reste du travail.
                    self._galerie(tenant, FATY_GALERIE)
                    produits = self._boutique(tenant, FATY_BOUTIQUE)

                    with transaction.atomic():
                        self._identite(tenant, FATY_IDENTITE)
                        self._a_propos(tenant, FATY_ABOUT_TITLE, FATY_ABOUT)
                        services = self._catalogue(tenant, FATY_CATALOGUE)
                        self._options(tenant, FATY_OPTIONS)
                        self._equipe(tenant, FATY_EQUIPE, services)
                        self._fournitures(tenant, FATY_FOURNITURES, produits)
                        self._zones(tenant, FATY_ZONES)
                        self._moyens(tenant, FATY_MOYENS)
                        self._horaires(tenant)
                        clientes = self._clientes(tenant, FATY_CLIENTES)
                        self._rendezvous(tenant, FATY_RENDEZVOUS, clientes)
                        self._avis(tenant, FATY_AVIS)

                    self._qr_wechat(tenant, FATY_IDENTITE["wechat_id"])
                elif not options["portraits"]:
                    self.stdout.write(
                        f"{INFO} vitrine déjà écrite à la main : portraits seuls"
                    )

                # En dernier, et c'est le point : les prestataires viennent
                # peut-être d'être créés par `_equipe`. Placés en tête, les
                # portraits ne trouvaient que les fiches déjà en base, et il
                # fallait relancer la commande pour que les trois nouvelles
                # aient un visage.
                self._portraits(tenant, slug)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Vitrine remplie."))

    # -- médias -----------------------------------------------------------

    def _importer(self, tenant, identifiant: int, genre: str, legende: str,
                  largeur: int) -> MediaAsset | None:
        """Recopie un cliché Pexels dans la médiathèque du salon.

        Renvoie `None` si l'import échoue : une photo manquante ne doit pas
        faire tomber le reste du peuplement, et le mini-site sait déjà se
        passer d'image.
        """
        existant = MediaAsset.objects.filter(tenant=tenant, alt_text=legende).first()
        if existant:
            return existant

        if self.dossier_photos:
            chemin = self.dossier_photos / f"{identifiant}.jpg"
            if not chemin.is_file():
                self.stdout.write(
                    self.style.WARNING(f"{INFO} photo {identifiant} : fichier absent")
                )
                return None
            contenu = ContentFile(chemin.read_bytes(), name=chemin.name)
            type_mime = "image/jpeg"
        else:
            try:
                contenu, type_mime = fetch_remote_media(pexels(identifiant, largeur))
            except RemoteMediaError as exc:
                self.stdout.write(
                    self.style.WARNING(f"{INFO} photo {identifiant} : {exc}")
                )
                return None

        return MediaAsset.objects.create(
            tenant=tenant,
            file=contenu,
            content_type=type_mime,
            byte_size=contenu.size,
            kind=genre,
            alt_text=legende,
        )

    def _portraits(self, tenant, slug):
        pose = 0
        for nom, (identifiant, legende) in PORTRAITS[slug].items():
            membre = StaffMember.objects.filter(tenant=tenant, name=nom).first()
            if membre is None or membre.photo_id:
                continue
            photo = self._importer(tenant, identifiant, MediaAsset.Kind.STAFF,
                                   legende, 800)
            if photo:
                membre.photo = photo
                membre.save(update_fields=["photo", "updated_at"])
                pose += 1

        sans = StaffMember.objects.filter(
            tenant=tenant, active=True, photo__isnull=True
        ).count()
        self.stdout.write(f"{OK} {pose} portraits posés")
        if sans:
            self.stdout.write(
                f"{INFO} {sans} prestataire(s) encore sans photo : "
                "la fiche affiche l'initiale, c'est prévu"
            )

    def _qr_wechat(self, tenant, identifiant: str):
        """Fabrique le QR de contact au lieu de le telecharger.

        Un vrai QR WeChat encode un vrai compte : en publier un pris ailleurs
        ferait ajouter un inconnu par les visiteuses du salon de
        demonstration. Celui-ci encode l'adresse de son propre mini-site —
        un code valide, scannable, et qui ne mene chez personne.
        """
        import qrcode

        profil = SalonProfile.objects.get(tenant=tenant)
        if profil.wechat_qr_id is not None:
            self.stdout.write(f"{INFO} QR WeChat deja en place")
            return

        legende = f"QR WeChat — {tenant.name}"
        image = qrcode.make(f"https://{tenant.slug}.localhost:3100")
        tampon = BytesIO()
        image.save(tampon, format="PNG")
        tampon.seek(0)

        code = MediaAsset.objects.create(
            tenant=tenant,
            file=ContentFile(tampon.read(), name="qr-wechat.png"),
            content_type="image/png",
            byte_size=tampon.tell(),
            kind=MediaAsset.Kind.WECHAT,
            alt_text=legende,
        )
        profil.wechat_qr = code
        profil.save(update_fields=["wechat_qr", "updated_at"])
        self.stdout.write(f"{OK} QR WeChat (identifiant : {identifiant})")

    def _galerie(self, tenant, planches):
        pose = 0
        for rang, (identifiant, legende, vedette) in enumerate(planches):
            photo = self._importer(tenant, identifiant, MediaAsset.Kind.GALLERY,
                                   legende, 1200)
            if photo is None:
                continue
            if photo.position != rang or photo.featured != vedette:
                photo.position = rang
                photo.featured = vedette
                photo.save(update_fields=["position", "featured", "updated_at"])
            pose += 1
        self.stdout.write(f"{OK} {pose} réalisations en galerie")

    # -- sections ---------------------------------------------------------

    def _identite(self, tenant, champs):
        """Complète les champs vides du profil, jamais ceux qui sont remplis.

        La gérante a pu corriger un numéro ou une adresse : une commande de
        démonstration n'a pas à décider que sa version vaut mieux.

        `service_mode` fait exception. Sa valeur par défaut — « au salon » —
        est une valeur comme une autre, pas un vide : le test ci-dessous ne
        la verrait jamais, et le salon garderait des zones de déplacement
        qu'aucune cliente ne peut choisir.
        """
        profil, _ = SalonProfile.objects.get_or_create(tenant=tenant)
        touches = []

        for champ, valeur in champs.items():
            vide = (
                profil.service_mode == ServiceMode.SALON
                if champ == "service_mode"
                else not getattr(profil, champ)
            )
            if vide:
                setattr(profil, champ, valeur)
                touches.append(champ)

        if touches:
            profil.save(update_fields=[*touches, "updated_at"])
        self.stdout.write(f"{OK} identité ({len(touches)} champs complétés)")

    def _a_propos(self, tenant, titre, texte):
        profil = SalonProfile.objects.get(tenant=tenant)
        if profil.about_content.strip():
            self.stdout.write(f"{INFO} page « À propos » déjà rédigée")
            return
        profil.about_title = titre
        profil.about_content = texte
        profil.save(update_fields=["about_title", "about_content", "updated_at"])
        self.stdout.write(f"{OK} page « À propos »")

    def _catalogue(self, tenant, catalogue) -> dict[str, Service]:
        rang_categorie = ServiceCategory.objects.count()
        for nom_cat, prestations in catalogue:
            categorie, neuve = ServiceCategory.objects.get_or_create(
                tenant=tenant, name=nom_cat, defaults={"position": rang_categorie}
            )
            rang_categorie += int(neuve)

            place = Service.objects.filter(category=categorie).count()
            for nom, minutes, prix, acompte in prestations:
                _, cree = Service.objects.get_or_create(
                    tenant=tenant,
                    name=nom,
                    defaults={
                        "category": categorie,
                        "duration_minutes": minutes,
                        "price_amount": Decimal(prix),
                        "requires_deposit": acompte,
                        "position": place,
                        "active": True,
                    },
                )
                place += int(cree)

        services = {s.name: s for s in Service.objects.all()}
        self.stdout.write(f"{OK} {len(services)} prestations au catalogue")
        return services

    def _options(self, tenant, options):
        total = 0
        for nom_service, liste in options.items():
            service = Service.objects.filter(tenant=tenant, name=nom_service).first()
            if service is None:
                continue
            for place, (nom, detail, prix, minutes) in enumerate(liste):
                _, cree = ServiceOption.objects.get_or_create(
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
                total += int(cree)
        self.stdout.write(f"{OK} {total} options ajoutées")

    def _equipe(self, tenant, equipe, services):
        membres = []
        for rang, (nom, specialite, presentation) in enumerate(equipe):
            membre, cree = StaffMember.objects.get_or_create(
                tenant=tenant,
                name=nom,
                defaults={
                    "specialty": specialite,
                    "bio": presentation,
                    "active": True,
                    "position": rang,
                },
            )
            if not cree:
                touches = []
                if not membre.specialty:
                    membre.specialty = specialite
                    touches.append("specialty")
                if not membre.bio:
                    membre.bio = presentation
                    touches.append("bio")
                if touches:
                    membre.save(update_fields=[*touches, "updated_at"])
            membres.append(membre)

        # Chacune sait tout faire. Sans rattachement, aucune prestation n'est
        # réservable — et une démonstration où l'on ne peut rien réserver ne
        # démontre rien.
        for membre in membres:
            for service in services.values():
                StaffService.objects.get_or_create(
                    tenant=tenant, staff_member=membre, service=service
                )
        self.stdout.write(f"{OK} {len(membres)} prestataires rattachés au catalogue")

    def _boutique(self, tenant, boutique) -> dict[str, Product]:
        produits: dict[str, Product] = {}
        for rang, (nom, detail, prix, unite, stock, identifiant) in enumerate(boutique):
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
            if not produit.image_id:
                image = self._importer(tenant, identifiant,
                                       MediaAsset.Kind.PRODUCT, f"{nom} — boutique", 800)
                if image:
                    produit.image = image
                    produit.save(update_fields=["image", "updated_at"])
            produits[nom] = produit
        self.stdout.write(f"{OK} {len(produits)} articles en boutique")
        return produits

    def _fournitures(self, tenant, fournitures, produits):
        total = 0
        for rang, (nom_service, libelle, detail, obligatoire, articles) in enumerate(
            fournitures
        ):
            service = Service.objects.filter(tenant=tenant, name=nom_service).first()
            if service is None:
                continue
            exigence, cree = Requirement.objects.get_or_create(
                tenant=tenant,
                service=service,
                label=libelle,
                defaults={"detail": detail, "mandatory": obligatoire, "position": rang},
            )
            for nom_article in articles:
                produit = produits.get(nom_article)
                if produit:
                    RequirementProduct.objects.get_or_create(
                        tenant=tenant, requirement=exigence, product=produit
                    )
            total += int(cree)
        self.stdout.write(f"{OK} {total} fournitures à prévoir")

    def _zones(self, tenant, zones):
        for rang, (nom, frais) in enumerate(zones):
            TravelZone.objects.get_or_create(
                tenant=tenant,
                name=nom,
                defaults={"fee_amount": Decimal(frais), "position": rang, "active": True},
            )
        self.stdout.write(f"{OK} {len(zones)} zones de déplacement")

    def _moyens(self, tenant, moyens):
        for rang, (genre, compte, consigne) in enumerate(moyens):
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
        self.stdout.write(f"{OK} {len(moyens)} moyens de paiement")

    def _horaires(self, tenant):
        if BusinessHours.objects.exists():
            self.stdout.write(f"{INFO} horaires déjà saisis")
            return
        for jour in range(1, 6):
            for debut, fin in ((time(9, 30), time(13, 0)), (time(14, 0), time(19, 0))):
                BusinessHours.objects.get_or_create(
                    tenant=tenant,
                    staff_member=None,
                    weekday=jour,
                    starts_at=debut,
                    defaults={"ends_at": fin},
                )
        self.stdout.write(f"{OK} horaires du mardi au samedi")

    def _clientes(self, tenant, clientes) -> dict[str, Customer]:
        fiches = {}
        for nom, numero, courriel in clientes:
            fiche, _ = Customer.objects.get_or_create(
                tenant=tenant,
                phone=numero,
                defaults={"full_name": nom, "email": courriel},
            )
            fiches[nom] = fiche
        self.stdout.write(f"{OK} {len(fiches)} fiches clientes")
        return fiches

    def _rendezvous(self, tenant, planning, clientes) -> int:
        """Pose l'agenda, sans passer par `create_booking`.

        Le service de réservation vérifie la disponibilité, réserve le
        créneau et déclenche des notifications. Pour une fixture, les trois
        sont des nuisances : un créneau hors horaires ferait échouer la
        commande, et un rendez-vous de démonstration n'a pas à faire partir
        un courriel. On écrit donc les lignes directement — ce que fait déjà
        l'agenda du salon quand la gérante saisit à la main.
        """
        maintenant = timezone.now()
        crees = 0

        # L'heure est celle du salon, pas celle du serveur.
        #
        # « 10 h 30 » dans une fixture veut dire dix heures et demie chez la
        # gérante. Composée dans le fuseau de Django, la même valeur tombait
        # à 18 h 30 à Guangzhou — donc hors des horaires d'ouverture, sur des
        # créneaux que l'agenda refuse d'afficher.
        fuseau = ZoneInfo(tenant.timezone)

        for jours, heure, nom_service, nom_membre, nom_cliente, statut, extra in planning:
            service = Service.objects.filter(tenant=tenant, name=nom_service).first()
            membre = StaffMember.objects.filter(tenant=tenant, name=nom_membre).first()
            cliente = clientes.get(nom_cliente)
            if not (service and membre and cliente):
                continue

            jour = maintenant.astimezone(fuseau).date() + timedelta(days=jours)
            debut = datetime.combine(jour, heure, tzinfo=fuseau)

            # Le doublon se reconnait a la cliente, la prestation et l'etat -
            # pas a l'horaire.
            #
            # Les dates de cette fixture sont relatives a aujourd'hui.
            # Dedoublonner sur `starts_at` marchait le premier jour et plus
            # jamais ensuite : relancee le lendemain, la commande calculait
            # des horaires decales d'un jour, n'y reconnaissait rien, et
            # doublait tout l'agenda - donc aussi le chiffre d'affaires de
            # demonstration. La promesse « elle se relance sans rien
            # ecraser » ne tenait qu'une journee.
            if Booking.objects.filter(
                tenant=tenant,
                customer=cliente,
                service=service,
                status=statut,
            ).exists():
                continue

            options = list(
                ServiceOption.objects.filter(
                    tenant=tenant, service=service, name__in=extra.get("options", [])
                )
            )
            options_montant = sum((o.price_delta for o in options), Decimal("0"))
            options_minutes = sum(o.duration_delta_minutes for o in options)

            articles = []
            articles_montant = Decimal("0")
            for nom_article, quantite in extra.get("articles", []):
                produit = Product.objects.filter(tenant=tenant, name=nom_article).first()
                if produit is None:
                    continue
                ligne = produit.price * quantite
                articles_montant += ligne
                articles.append(
                    {
                        "product_id": str(produit.id),
                        "name": produit.name,
                        "quantity": quantite,
                        "unit_price": str(produit.price),
                        "total": str(ligne),
                    }
                )

            zone = None
            if extra.get("zone"):
                zone = TravelZone.objects.filter(
                    tenant=tenant, name=extra["zone"]
                ).first()
            frais = zone.fee_amount if zone else Decimal("0")

            total = service.price_amount + options_montant + articles_montant + frais
            profil = SalonProfile.objects.get(tenant=tenant)

            # L'acompte se calcule par `compute_deposit`, pas ici.
            #
            # J'en avais ecrit une seconde version - pourcentage arrondi au
            # centime, borne par le plancher. Elle ignorait deux regles que
            # la vraie applique : l'arrondi vers le bas au pas de la devise,
            # et le fait que la marchandise et le trajet n'entrent pas
            # forcement dans l'assiette. Les montants de demonstration
            # auraient donc differe de ceux que le produit facture, et c'est
            # precisement sur ces montants qu'on regarde si l'ecran est
            # juste.
            from apps.scheduling.services.deposit import compute_deposit

            acompte = compute_deposit(
                service_amount=service.price_amount,
                options_amount=options_montant,
                items_amount=articles_montant,
                travel_amount=frais,
                requires_deposit=bool(service.requires_deposit),
                rate=profil.deposit_rate or 0,
                minimum=profil.deposit_minimum or Decimal("0"),
                covers_items=profil.deposit_covers_items,
                currency=tenant.currency,
            )

            paye = bool(extra.get("acompte_paye"))
            annule = statut == Booking.Status.CANCELLED

            Booking.objects.create(
                tenant=tenant,
                customer=cliente,
                staff_member=membre,
                service=service,
                starts_at=debut,
                ends_at=debut
                + timedelta(minutes=service.duration_minutes + options_minutes),
                status=statut,
                source=Booking.Source.WEB,
                service_name=service.name,
                total_amount=total,
                options_snapshot=[
                    {
                        "name": o.name,
                        "price": str(o.price_delta),
                        "minutes": o.duration_delta_minutes,
                    }
                    for o in options
                ],
                options_amount=options_montant,
                items_snapshot=articles,
                items_amount=articles_montant,
                deposit_amount=acompte,
                deposit_paid=paye,
                deposit_paid_at=debut - timedelta(days=1) if paye else None,
                deposit_received=acompte if paye else Decimal("0"),
                deposit_method="wechat" if paye else "",
                location_mode=ServiceMode.HOME if zone else ServiceMode.SALON,
                address=extra.get("adresse", ""),
                travel_zone_name=zone.name if zone else "",
                travel_fee_amount=frais,
                customer_note=extra.get("note", ""),
                cancelled_at=maintenant if annule else None,
                cancellation_reason=extra.get("motif", ""),
            )
            crees += 1

        # Les visites honorees produisent leurs ecritures, comme le ferait
        # l'agenda quand la gerante coche « terminee ». Sans elles, l'ecran
        # Finances reste une page vide et l'on ne peut rien y juger — ni la
        # repartition des recettes, ni la ligne « Deplacement » qu'on vient
        # d'ajouter.
        from apps.finance.services import record_booking_income

        ecritures = 0
        for reservation in Booking.objects.filter(
            tenant=tenant, status=Booking.Status.COMPLETED
        ):
            if record_booking_income(reservation) is not None:
                ecritures += 1

        self.stdout.write(f"{OK} {crees} rendez-vous à l'agenda, {ecritures} en recette")
        return crees

    def _avis(self, tenant, avis):
        """Rattache un avis à la visite terminée de chaque cliente.

        On repart de la base plutôt que du dictionnaire renvoyé par
        `_rendezvous` : à la deuxième exécution, celui-ci est vide — les
        rendez-vous existaient déjà — et les avis ne seraient jamais posés si
        un import réseau avait échoué au premier passage.
        """
        pose = 0
        termines = {
            b.customer.full_name: b
            for b in Booking.objects.filter(
                tenant=tenant, status=Booking.Status.COMPLETED
            ).select_related("customer")
        }

        for nom, criteres, commentaire in avis:
            reservation = termines.get(nom)
            if reservation is None or Review.objects.filter(
                booking=reservation
            ).exists():
                continue

            notes = {f"rating_{champ}": note for champ, note in criteres.items()}
            # La note d'ensemble est la moyenne des critères, arrondie —
            # exactement ce que calcule le formulaire d'avis. La saisir à la
            # main produirait une fiche où le résumé contredit le détail.
            ensemble = round(sum(criteres.values()) / len(criteres))

            Review.objects.create(
                tenant=tenant,
                booking=reservation,
                customer=reservation.customer,
                author_name=reservation.customer.full_name,
                rating=ensemble,
                comment=commentaire,
                status=Review.Status.PUBLISHED,
                **notes,
            )
            pose += 1
        self.stdout.write(f"{OK} {pose} avis publiés")
