"""La facture d'abonnement, en PDF.

---------------------------------------------------------------------------
Pourquoi un PDF ecrit a la main
---------------------------------------------------------------------------

Le serveur n'a aucune bibliotheque PDF, et une facture n'en demande pas :
une page A4, deux polices, des filets, deux images. Le format PDF ecrit ici
est le plus simple qui soit — objets, flux compresses, table des references —
et le resultat est un vrai document vectoriel : texte selectionnable et
recherchable, nettete a toute echelle, quelques dizaines de kilo-octets.

Les polices sont Helvetica et Helvetica-Bold, deux des quatorze polices que
tout lecteur PDF fournit lui-meme : rien a embarquer. Elles couvrent le
francais (accents, guillemets, espace insecable) par l'encodage WinAnsi ; les
largeurs de leurs caracteres sont reprises de leurs metriques officielles,
pour aligner les montants a droite au point pres.

---------------------------------------------------------------------------
Ce que porte la page
---------------------------------------------------------------------------

En-tete aux couleurs de Beauty Salon (logo, numero, statut), emetteur et
salon facture, dates, detail (tarif, remise de parrainage eventuelle,
total), reglement, pied de page. En filigrane : la marque B, tres claire,
et le statut de la facture en diagonale (« PAYÉE », « À RÉGLER »,
« ANNULÉE »). La langue est celle de la page qui demande la facture.
"""

from __future__ import annotations

import zlib
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.utils import timezone
from PIL import Image

from .courriers import argent, date_longue, nom_offre

DOSSIER = Path(__file__).resolve().parent / "pdf"
LARGEUR, HAUTEUR = 595.28, 841.89  # A4, en points
MARGE = 48

FRAMBOISE = (0.686, 0.145, 0.329)  # #AF2554
ROSE = (0.980, 0.737, 0.808)  # #FABCCE
ROSE_PALE = (0.992, 0.914, 0.941)  # #FDE9F0
ENCRE = (0.165, 0.055, 0.106)  # #2A0E1B
DOUX = (0.478, 0.333, 0.400)  # #7A5566
FILET = (0.925, 0.871, 0.894)
VERT = (0.122, 0.541, 0.357)

# ---------------------------------------------------------------------------
# Metriques (unites pour mille) d'Helvetica et Helvetica-Bold, Adobe AFM.
# ---------------------------------------------------------------------------
_ASCII = (
    " !\"#$%&'()*+,-./0123456789:;<=>?@"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~"
)
_REG = [
    278,
    278,
    355,
    556,
    556,
    889,
    667,
    191,
    333,
    333,
    389,
    584,
    278,
    333,
    278,
    278,
    556,
    556,
    556,
    556,
    556,
    556,
    556,
    556,
    556,
    556,
    278,
    278,
    584,
    584,
    584,
    556,
    1015,
    667,
    667,
    722,
    722,
    667,
    611,
    778,
    722,
    278,
    500,
    667,
    556,
    833,
    722,
    778,
    667,
    778,
    722,
    667,
    611,
    722,
    667,
    944,
    667,
    667,
    611,
    278,
    278,
    278,
    469,
    556,
    333,
    556,
    556,
    500,
    556,
    556,
    278,
    556,
    556,
    222,
    222,
    500,
    222,
    833,
    556,
    556,
    556,
    556,
    333,
    500,
    278,
    556,
    500,
    722,
    500,
    500,
    500,
    334,
    260,
    334,
    584,
]
_GRAS = [
    278,
    333,
    474,
    556,
    556,
    889,
    722,
    238,
    333,
    333,
    389,
    584,
    278,
    333,
    278,
    278,
    556,
    556,
    556,
    556,
    556,
    556,
    556,
    556,
    556,
    556,
    333,
    333,
    584,
    584,
    584,
    611,
    975,
    722,
    722,
    722,
    722,
    667,
    611,
    778,
    722,
    278,
    556,
    722,
    611,
    833,
    722,
    778,
    667,
    778,
    722,
    667,
    611,
    722,
    667,
    944,
    667,
    667,
    611,
    333,
    278,
    333,
    584,
    556,
    333,
    556,
    611,
    556,
    611,
    556,
    333,
    611,
    611,
    278,
    278,
    556,
    278,
    889,
    611,
    611,
    611,
    611,
    389,
    556,
    333,
    611,
    556,
    778,
    556,
    556,
    500,
    389,
    280,
    389,
    584,
]
LARGEURS = {
    "F1": dict(zip(_ASCII, _REG, strict=True)),
    "F2": dict(zip(_ASCII, _GRAS, strict=True)),
}
# Les lettres accentuees ont la largeur de leur lettre de base ; quelques signes a part.
_BASE = str.maketrans(
    "àâäáãåçéèêëíìîïñóòôöõúùûüýÿÀÂÄÁÃÅÇÉÈÊËÍÌÎÏÑÓÒÔÖÕÚÙÛÜÝœŒ",
    "aaaaaaceeeeiiiinooooouuuuyyAAAAAACEEEEIIIINOOOOOUUUUYoO",
)
_SIGNES = {
    "’": 222,
    "‘": 222,
    "«": 556,
    "»": 556,
    "€": 556,
    "¥": 556,
    " ": 278,
    "·": 278,
    "–": 556,
    "—": 1000,
    "°": 400,
    "…": 1000,
    "×": 584,
    "−": 584,
}


def largeur(texte: str, police: str, taille: float) -> float:
    table = LARGEURS[police]
    total = 0
    for c in texte:
        if c in _SIGNES:
            total += _SIGNES[c]
        else:
            total += table.get(c.translate(_BASE), 556)
    return total * taille / 1000


def _winansi(texte: str) -> bytes:
    """Le texte dans l'encodage des polices standard, echappe pour un flux PDF."""
    propre = texte.replace(" ", " ").replace("−", "-").replace(" ", " ").replace("\n", " ")
    octets = propre.encode("cp1252", errors="replace")
    return octets.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


# ---------------------------------------------------------------------------
# Une page, des operations de dessin
# ---------------------------------------------------------------------------
class Page:
    def __init__(self):
        self.ops: list[bytes] = []
        self.images: dict[str, Path] = {}
        self.transparences: dict[str, float] = {}

    def _y(self, y: float) -> float:  # coordonnees depuis le haut de la page
        return HAUTEUR - y

    def couleur(self, rgb, trait=False):
        operateur = "RG" if trait else "rg"
        self.ops.append(f"{rgb[0]:.3f} {rgb[1]:.3f} {rgb[2]:.3f} {operateur}".encode())

    def rect(self, x, y, larg, h, rgb, rayon=0):
        self.couleur(rgb)
        if not rayon:
            self.ops.append(b"%.2f %.2f %.2f %.2f re f" % (x, self._y(y + h), larg, h))
            return
        r, k = rayon, 0.5523 * rayon
        x0, y0, x1, y1 = x, self._y(y + h), x + larg, self._y(y)
        self.ops.append(
            (
                f"{x0 + r:.2f} {y0:.2f} m {x1 - r:.2f} {y0:.2f} l "
                f"{x1 - r + k:.2f} {y0:.2f} {x1:.2f} {y0 + r - k:.2f} {x1:.2f} {y0 + r:.2f} c "
                f"{x1:.2f} {y1 - r:.2f} l {x1:.2f} {y1 - r + k:.2f} "
                f"{x1 - r + k:.2f} {y1:.2f} {x1 - r:.2f} {y1:.2f} c "
                f"{x0 + r:.2f} {y1:.2f} l {x0 + r - k:.2f} {y1:.2f} "
                f"{x0:.2f} {y1 - r + k:.2f} {x0:.2f} {y1 - r:.2f} c "
                f"{x0:.2f} {y0 + r:.2f} l {x0:.2f} {y0 + r - k:.2f} "
                f"{x0 + r - k:.2f} {y0:.2f} {x0 + r:.2f} {y0:.2f} c f"
            ).encode()
        )

    def ligne(self, x0, y0, x1, y1, rgb=FILET, epaisseur=0.8):
        self.couleur(rgb, trait=True)
        self.ops.append(
            b"%.2f w %.2f %.2f m %.2f %.2f l S" % (epaisseur, x0, self._y(y0), x1, self._y(y1))
        )

    def texte(self, x, y, chaine, taille=10, gras=False, rgb=ENCRE, aligne="g", espacement=0.0):
        police = "F2" if gras else "F1"
        if aligne == "d":
            x -= largeur(chaine, police, taille) + espacement * max(0, len(chaine) - 1)
        elif aligne == "c":
            x -= (largeur(chaine, police, taille) + espacement * max(0, len(chaine) - 1)) / 2
        self.couleur(rgb)
        tc = b" %.2f Tc" % espacement if espacement else b""
        self.ops.append(
            b"BT /%s %.2f Tf%s %.2f %.2f Td (%s) Tj ET%s"
            % (
                police.encode(),
                taille,
                tc,
                x,
                self._y(y),
                _winansi(chaine),
                b" 0 Tc" if espacement else b"",
            )
        )

    def image(self, nom, chemin, x, y, larg, h, opacite=1.0):
        self.images[nom] = chemin
        self.ops.append(b"q")
        if opacite < 1:
            self.transparences[f"GS{nom}"] = opacite
            self.ops.append(b"/GS%s gs" % nom.encode())
        self.ops.append(
            b"%.2f 0 0 %.2f %.2f %.2f cm /%s Do Q" % (larg, h, x, self._y(y + h), nom.encode())
        )

    def tampon(self, chaine, rgb, opacite, taille, angle=35):
        """Le statut en diagonale, au centre de la page."""
        import math

        self.transparences["GSTampon"] = opacite
        a = math.radians(angle)
        w = largeur(chaine, "F2", taille) + 6 * (len(chaine) - 1)
        cx, cy = LARGEUR / 2, HAUTEUR / 2 - 30
        x = cx - math.cos(a) * w / 2 + math.sin(a) * taille * 0.35
        y = cy - math.sin(a) * w / 2 - math.cos(a) * taille * 0.35
        self.ops.append(
            b"q /GSTampon gs %.3f %.3f %.3f rg BT /F2 %.2f Tf 6 Tc "
            b"%.4f %.4f %.4f %.4f %.2f %.2f Tm (%s) Tj ET Q"
            % (
                *rgb,
                taille,
                math.cos(a),
                math.sin(a),
                -math.sin(a),
                math.cos(a),
                x,
                y,
                _winansi(chaine),
            )
        )


# ---------------------------------------------------------------------------
# Ecriture du fichier PDF
# ---------------------------------------------------------------------------
def _flux_image(chemin: Path) -> tuple[bytes, bytes, int, int]:
    im = Image.open(chemin).convert("RGBA")
    rgb = im.convert("RGB").tobytes()
    alpha = im.getchannel("A").tobytes()
    return zlib.compress(rgb, 9), zlib.compress(alpha, 9), im.width, im.height


def _assembler(page: Page, titre: str) -> bytes:
    objets: list[bytes] = []

    def ajouter(contenu: bytes) -> int:
        objets.append(contenu)
        return len(objets)

    def flux(dico: bytes, donnees: bytes) -> bytes:
        return b"<< %s /Length %d >>\nstream\n%s\nendstream" % (dico, len(donnees), donnees)

    polices = {
        "F1": ajouter(
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
        ),
        "F2": ajouter(
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold "
            b"/Encoding /WinAnsiEncoding >>"
        ),
    }
    images = {}
    for nom, chemin in page.images.items():
        rgb, alpha, w, h = _flux_image(chemin)
        masque = ajouter(
            flux(
                b"/Type /XObject /Subtype /Image /Width %d /Height %d "
                b"/ColorSpace /DeviceGray /BitsPerComponent 8 /Filter /FlateDecode"
                % (w, h),
                alpha,
            )
        )
        images[nom] = ajouter(
            flux(
                b"/Type /XObject /Subtype /Image /Width %d /Height %d "
                b"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode /SMask %d 0 R"
                % (w, h, masque),
                rgb,
            )
        )
    etats = {
        nom: ajouter(b"<< /Type /ExtGState /ca %.3f /CA %.3f >>" % (o, o))
        for nom, o in page.transparences.items()
    }

    contenu = zlib.compress(b"\n".join(page.ops), 9)
    flux_page = ajouter(flux(b"/Filter /FlateDecode", contenu))
    ressources = b"<< /Font << %s >> /XObject << %s >> /ExtGState << %s >> >>" % (
        b" ".join(b"/%s %d 0 R" % (k.encode(), v) for k, v in polices.items()),
        b" ".join(b"/%s %d 0 R" % (k.encode(), v) for k, v in images.items()),
        b" ".join(b"/%s %d 0 R" % (k.encode(), v) for k, v in etats.items()),
    )
    pages_id = len(objets) + 2
    page_id = ajouter(
        b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %.2f %.2f] /Resources %s /Contents %d 0 R >>"
        % (pages_id, LARGEUR, HAUTEUR, ressources, flux_page)
    )
    assert ajouter(b"<< /Type /Pages /Kids [%d 0 R] /Count 1 >>" % page_id) == pages_id
    infos = ajouter(
        b"<< /Title (%s) /Author (Beauty Salon) /Producer (Beauty Salon) /CreationDate (D:%s) >>"
        % (_winansi(titre), timezone.now().strftime("%Y%m%d%H%M%SZ").encode())
    )
    catalogue = ajouter(b"<< /Type /Catalog /Pages %d 0 R >>" % pages_id)

    sortie = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    positions = []
    for numero, contenu in enumerate(objets, start=1):
        positions.append(len(sortie))
        sortie += b"%d 0 obj\n%s\nendobj\n" % (numero, contenu)
    xref = len(sortie)
    sortie += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objets) + 1)
    for p in positions:
        sortie += b"%010d 00000 n \n" % p
    sortie += b"trailer\n<< /Size %d /Root %d 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objets) + 1,
        catalogue,
        infos,
        xref,
    )
    return bytes(sortie)


# ---------------------------------------------------------------------------
# La facture
# ---------------------------------------------------------------------------
TEXTES = {
    "fr": {
        "facture": "FACTURE",
        "numero": "N°",
        "emise_par": "ÉMISE PAR",
        "facturee_a": "FACTURÉE À",
        "emission": "Date d’émission",
        "echeance": "Échéance",
        "payee_le": "Payée le",
        "designation": "DÉSIGNATION",
        "periode": "PÉRIODE",
        "montant": "MONTANT",
        "abonnement": "Abonnement Beauty Salon",
        "offre": "Offre {offre}",
        "mois": "{n} mois",
        "tarif": "Tarif de l’offre",
        "remise": "Remise de parrainage (−{pct} %)",
        "total": "TOTAL",
        "regle": "Montant réglé",
        "reste": "Reste à régler",
        "reglement": "RÈGLEMENT",
        "moyen": "Moyen",
        "reference": "Référence",
        "merci": "Merci pour votre confiance.",
        "pied": "Document généré le {date} · {site}",
        "statuts": {"paid": "PAYÉE", "issued": "À RÉGLER", "void": "ANNULÉE", "draft": "BROUILLON"},
        "proprietaire": "Propriétaire",
    },
    "en": {
        "facture": "INVOICE",
        "numero": "No.",
        "emise_par": "ISSUED BY",
        "facturee_a": "BILLED TO",
        "emission": "Issue date",
        "echeance": "Due date",
        "payee_le": "Paid on",
        "designation": "DESCRIPTION",
        "periode": "PERIOD",
        "montant": "AMOUNT",
        "abonnement": "Beauty Salon subscription",
        "offre": "{offre} plan",
        "mois": "{n} month(s)",
        "tarif": "Plan price",
        "remise": "Referral discount (−{pct}%)",
        "total": "TOTAL",
        "regle": "Amount paid",
        "reste": "Balance due",
        "reglement": "PAYMENT",
        "moyen": "Method",
        "reference": "Reference",
        "merci": "Thank you for your trust.",
        "pied": "Generated on {date} · {site}",
        "statuts": {"paid": "PAID", "issued": "DUE", "void": "CANCELLED", "draft": "DRAFT"},
        "proprietaire": "Owner",
    },
}
MOYENS_EN = {
    "cash": "Cash",
    "mobile_money": "Mobile Money",
    "wechat": "WeChat Pay",
    "alipay": "Alipay",
    "transfer": "Bank transfer",
    "other": "Other",
}


def nom_de_fichier(facture, langue: str = "fr") -> str:
    prefixe = "invoice" if langue == "en" else "facture"
    return f"{prefixe}-{facture.number}.pdf"


def generer(facture, langue: str = "fr") -> bytes:
    """Le PDF d'une facture. A appeler dans le contexte du salon."""
    from apps.accounts.models import Membership
    from apps.salons.models import SalonProfile

    from .models import SubscriptionPaymentRequest

    t = TEXTES["en" if langue == "en" else "fr"]
    tenant = facture.tenant
    fuseau = getattr(tenant, "timezone", "") or "UTC"
    demande = (
        SubscriptionPaymentRequest.objects.select_related("plan").filter(invoice=facture).first()
    )
    profil = SalonProfile.objects.filter(tenant_id=tenant.id).first()
    proprietaire = (
        Membership.objects.filter(
            tenant_id=tenant.id, role=Membership.Role.OWNER, status=Membership.Status.ACTIVE
        )
        .select_related("user")
        .first()
    )
    montant = lambda v: argent(v, facture.currency, langue)  # noqa: E731
    date = lambda d: date_longue(d, fuseau, langue) if d else "—"  # noqa: E731
    p = Page()
    D = LARGEUR - MARGE

    # Filigrane : la marque B, tres claire, puis le statut en diagonale.
    p.image(
        "Filigrane",
        DOSSIER / "logo-b.png",
        LARGEUR / 2 - 150,
        HAUTEUR / 2 - 175,
        300,
        336,
        opacite=0.045,
    )
    teinte = {"paid": VERT, "void": DOUX}.get(facture.status, FRAMBOISE)
    p.tampon(t["statuts"].get(facture.status, facture.status.upper()), teinte, 0.07, 92)

    # En-tete : bandeau framboise, ruban rose, logo, titre et numero.
    p.rect(0, 0, LARGEUR, 8, FRAMBOISE)
    p.rect(0, 8, LARGEUR, 3, ROSE)
    p.image("Logo", DOSSIER / "logo-complet.png", MARGE, 44, 176, 36)
    p.texte(D, 60, t["facture"], 22, gras=True, rgb=FRAMBOISE, aligne="d", espacement=2.2)
    p.texte(D, 78, f"{t['numero']} {facture.number}", 10.5, gras=True, aligne="d")
    statut = t["statuts"].get(facture.status, facture.status)
    lp = largeur(statut, "F2", 8.5) + 22
    fond, encre = ({"paid": ((0.890, 0.961, 0.925), VERT)}).get(
        facture.status, (ROSE_PALE, FRAMBOISE)
    )
    p.rect(D - lp, 88, lp, 18, fond, rayon=9)
    p.texte(D - lp / 2, 100.5, statut, 8.5, gras=True, rgb=encre, aligne="c")

    # Emetteur et salon facture
    y = 150
    p.texte(MARGE, y, t["emise_par"], 7.5, gras=True, rgb=FRAMBOISE, espacement=1.2)
    p.texte(LARGEUR / 2 + 10, y, t["facturee_a"], 7.5, gras=True, rgb=FRAMBOISE, espacement=1.2)
    emetteur = [
        settings.INVOICE_ISSUER_NAME,
        *[x for x in settings.INVOICE_ISSUER_DETAILS if x],
        settings.PLATFORM_DOMAIN,
    ]
    for i, ligne in enumerate(emetteur):
        p.texte(
            MARGE,
            y + 17 + i * 14,
            ligne,
            10.5 if i == 0 else 9.5,
            gras=i == 0,
            rgb=ENCRE if i == 0 else DOUX,
        )
    adresse = ", ".join(
        x for x in [getattr(profil, "address", ""), getattr(profil, "city", "")] if x
    )
    client = [tenant.name, adresse, f"{tenant.slug}.{settings.PLATFORM_DOMAIN}"]
    if proprietaire:
        nom = proprietaire.user.display_name or ""
        client.append(
            f"{t['proprietaire']} : {nom} · {proprietaire.user.email}"
            if langue != "en"
            else f"{t['proprietaire']}: {nom} · {proprietaire.user.email}"
        )
    for i, ligne in enumerate(x for x in client if x):
        p.texte(
            LARGEUR / 2 + 10,
            y + 17 + i * 14,
            ligne[:70],
            10.5 if i == 0 else 9.5,
            gras=i == 0,
            rgb=ENCRE if i == 0 else DOUX,
        )

    # Dates, en trois cases
    y = 250
    cases = [(t["emission"], date(facture.issued_at)), (t["echeance"], date(facture.due_at))]
    if facture.paid_at:
        cases.append((t["payee_le"], date(facture.paid_at)))
    lc = (D - MARGE - 2 * 12) / 3
    for i, (titre, valeur) in enumerate(cases):
        x = MARGE + i * (lc + 12)
        p.rect(x, y, lc, 46, ROSE_PALE, rayon=8)
        p.texte(x + 12, y + 17, titre, 8, rgb=DOUX)
        p.texte(x + 12, y + 34, valeur, 10.5, gras=True)

    # Detail
    y = 330
    p.rect(MARGE, y, D - MARGE, 26, (0.984, 0.957, 0.969), rayon=6)
    p.texte(MARGE + 12, y + 17, t["designation"], 7.5, gras=True, rgb=DOUX, espacement=1)
    p.texte(MARGE + 300, y + 17, t["periode"], 7.5, gras=True, rgb=DOUX, espacement=1)
    p.texte(D - 12, y + 17, t["montant"], 7.5, gras=True, rgb=DOUX, aligne="d", espacement=1)
    y += 48
    offre = nom_offre(demande.plan, langue) if demande else ""
    p.texte(MARGE + 12, y, t["abonnement"], 10.5, gras=True)
    sous = " · ".join(
        x
        for x in [
            t["offre"].format(offre=offre) if offre else (facture.label or ""),
            t["mois"].format(n=demande.billing_months) if demande else "",
        ]
        if x
    )
    if sous:
        p.texte(MARGE + 12, y + 15, sous, 9, rgb=DOUX)
    p.texte(MARGE + 300, y, f"{date(facture.period_start)} –", 9.5)
    p.texte(MARGE + 300, y + 15, date(facture.period_end), 9.5)
    remise = demande and demande.remise_montant and demande.montant_catalogue
    p.texte(
        D - 12,
        y,
        montant(demande.montant_catalogue if remise else facture.amount),
        10.5,
        gras=True,
        aligne="d",
    )
    y += 34
    p.ligne(MARGE, y, D, y)
    if remise:
        y += 24
        pct = (
            str(Decimal(demande.remise_pourcentage).normalize())
            if demande.remise_pourcentage is not None
            else ""
        )
        p.texte(MARGE + 12, y, t["remise"].format(pct=pct), 9.5, rgb=VERT)
        p.texte(
            D - 12, y, "−" + montant(demande.remise_montant), 10, gras=True, rgb=VERT, aligne="d"
        )
        y += 14
        p.ligne(MARGE, y, D, y)

    # Totaux, dans un encart a droite
    y += 22
    xg = D - 230
    p.rect(xg, y, 230, 30, FRAMBOISE, rayon=8)
    p.texte(xg + 14, y + 19.5, t["total"], 9, gras=True, rgb=(1, 1, 1), espacement=1.2)
    p.texte(D - 14, y + 20, montant(facture.amount), 13, gras=True, rgb=(1, 1, 1), aligne="d")
    paye = facture.status == "paid"
    p.texte(xg + 14, y + 50, t["regle"], 9, rgb=DOUX)
    p.texte(D - 14, y + 50, montant(facture.amount if paye else 0), 9.5, gras=True, aligne="d")
    p.texte(xg + 14, y + 66, t["reste"], 9, rgb=DOUX)
    p.texte(
        D - 14,
        y + 66,
        montant(0 if paye or facture.status == "void" else facture.amount),
        9.5,
        gras=True,
        aligne="d",
    )

    # Reglement
    if facture.payment_method or facture.payment_reference:
        yr = y
        p.texte(MARGE, yr + 6, t["reglement"], 7.5, gras=True, rgb=FRAMBOISE, espacement=1.2)
        moyen = (
            MOYENS_EN.get(facture.payment_method, facture.payment_method)
            if langue == "en"
            else facture.get_payment_method_display()
        )
        lignes = [(t["moyen"], moyen or "—"), (t["reference"], facture.payment_reference or "—")]
        if facture.paid_at:
            lignes.append((t["payee_le"], date(facture.paid_at)))
        for i, (k, v) in enumerate(lignes):
            p.texte(MARGE, yr + 24 + i * 15, f"{k}", 9, rgb=DOUX)
            p.texte(MARGE + 70, yr + 24 + i * 15, v[:48], 9.5, gras=True)

    # Merci, puis pied de page
    p.texte(MARGE, HAUTEUR - 96, t["merci"], 11, gras=True, rgb=FRAMBOISE)
    p.ligne(MARGE, HAUTEUR - 70, D, HAUTEUR - 70)
    p.texte(
        MARGE,
        HAUTEUR - 52,
        f"{settings.INVOICE_ISSUER_NAME} · {settings.PLATFORM_DOMAIN}",
        8.5,
        gras=True,
        rgb=ENCRE,
    )
    p.texte(
        D,
        HAUTEUR - 52,
        t["pied"].format(date=date(timezone.now()), site=facture.number),
        8,
        rgb=DOUX,
        aligne="d",
    )
    p.rect(0, HAUTEUR - 11, LARGEUR, 3, ROSE)
    p.rect(0, HAUTEUR - 8, LARGEUR, 8, FRAMBOISE)

    return _assembler(p, f"{t['facture'].capitalize()} {facture.number}")
