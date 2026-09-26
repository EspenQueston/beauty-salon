"""Personnalisation avancee du mini-site (offre Pro).

---------------------------------------------------------------------------
Des choix, pas du code
---------------------------------------------------------------------------

Le salon choisit parmi des options fermees : une police dans une liste,
l'ordre et la visibilite de rubriques connues, deux textes courts, et au
plus trois pages a lui. Aucun champ n'accepte de HTML, de CSS ni de script —
ce qui n'est pas dans ces listes est refuse, pas nettoye. Les textes sont du
texte brut, affiches echappes par React comme tout contenu de salon.

C'est ce qui permet d'ouvrir la personnalisation sans ouvrir de faille :
un mini-site partage son domaine parent avec l'espace professionnel.

---------------------------------------------------------------------------
Les pages du salon
---------------------------------------------------------------------------

Trois au plus (« Tarifs », « Formations », « Événements »…). Chacune a un
identifiant stable (8 caracteres hexadecimaux) qui la relie au menu, et une
adresse `/p/<slug>` tiree de son titre. Son image est un media du salon,
verifie par la vue (`views_dashboard.SitePersonnaliseView`) : ce module ne
lit pas la base.
"""

from __future__ import annotations

import re
import secrets
import unicodedata

from rest_framework import serializers

# Cle : (nom affiche, famille, utilisable pour le texte courant).
# Les polices manuscrites sont belles en titre et illisibles en paragraphe :
# elles ne sont proposees que pour les titres.
POLICES: dict[str, tuple[str, str, bool]] = {
    "geist": ("Geist", "moderne", True),
    "montserrat": ("Montserrat", "moderne", True),
    "poppins": ("Poppins", "moderne", True),
    "nunito": ("Nunito", "moderne", True),
    "josefin": ("Josefin Sans", "moderne", True),
    "raleway": ("Raleway", "moderne", True),
    "manrope": ("Manrope", "moderne", True),
    "outfit": ("Outfit", "moderne", True),
    "quicksand": ("Quicksand", "moderne", True),
    "playfair": ("Playfair Display", "elegante", True),
    "cormorant": ("Cormorant Garamond", "elegante", True),
    "lora": ("Lora", "elegante", True),
    "libre-baskerville": ("Libre Baskerville", "elegante", True),
    "fraunces": ("Fraunces", "elegante", True),
    "dm-serif": ("DM Serif Display", "affiche", False),
    "bodoni": ("Bodoni Moda", "affiche", False),
    "cinzel": ("Cinzel", "affiche", False),
    "italiana": ("Italiana", "affiche", False),
    "marcellus": ("Marcellus", "affiche", False),
    "great-vibes": ("Great Vibes", "manuscrite", False),
    "dancing-script": ("Dancing Script", "manuscrite", False),
    "parisienne": ("Parisienne", "manuscrite", False),
}

# Les rubriques du menu, dans l'ordre par defaut.
MENU = ("prestations", "realisations", "equipe", "a-propos", "infos")

# Les sections de l'accueil entre l'en-tete et l'appel final, qui restent
# a leur place : l'une presente le salon, l'autre invite a reserver.
SECTIONS = ("prestations", "etapes", "realisations", "equipe", "avis", "infos")

PAGES_MAX = 3
LONGUEUR_ACCROCHE = 160
LONGUEUR_BOUTON = 28
LONGUEUR_TITRE_PAGE = 28
LONGUEUR_CONTENU_PAGE = 4000
PREFIXE_PAGE = "page:"
ID_PAGE = re.compile(r"^[0-9a-f]{8}$")
UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def _ordre(valeurs, connues: tuple[str, ...], nom: str) -> list[dict]:
    """Une liste `[{"cle", "visible"}]` complete, sans doublon ni inconnue."""
    if not isinstance(valeurs, list):
        raise serializers.ValidationError({nom: "Liste attendue."})
    vues: list[dict] = []
    for entree in valeurs:
        if not isinstance(entree, dict) or entree.get("cle") not in connues:
            raise serializers.ValidationError({nom: "Rubrique inconnue."})
        if any(v["cle"] == entree["cle"] for v in vues):
            raise serializers.ValidationError({nom: "Rubrique en double."})
        vues.append({"cle": entree["cle"], "visible": bool(entree.get("visible", True))})
    # Les rubriques oubliees reviennent a la fin, visibles : une ancienne
    # configuration ne fait jamais disparaitre une rubrique ajoutee depuis.
    for cle in connues:
        if not any(v["cle"] == cle for v in vues):
            vues.append({"cle": cle, "visible": True})
    return vues


def _texte(valeur, longueur: int, nom: str, *, lignes: bool = False) -> str:
    """Du texte brut. `lignes` garde les retours a la ligne (paragraphes)."""
    if valeur in (None, ""):
        return ""
    if not isinstance(valeur, str):
        raise serializers.ValidationError({nom: "Texte attendu."})
    if lignes:
        # Espaces resserres dans chaque ligne, trois lignes vides au plus
        # ramenees a une : les paragraphes restent, le vide non.
        brut = "\n".join(" ".join(ligne.split()) for ligne in valeur.replace("\r", "").split("\n"))
        texte = re.sub(r"\n{3,}", "\n\n", brut).strip()
    else:
        texte = " ".join(valeur.split())
    if len(texte) > longueur:
        raise serializers.ValidationError({nom: f"{longueur} caractères au plus."})
    if "<" in texte or ">" in texte:
        raise serializers.ValidationError({nom: "Les chevrons < et > ne sont pas acceptés."})
    return texte


def slug_de(titre: str) -> str:
    """« Tarifs & Forfaits » -> « tarifs-forfaits ». Jamais vide."""
    ascii_ = unicodedata.normalize("NFKD", titre).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_.lower()).strip("-")[:32].strip("-")
    return slug or "page"


def _pages(valeurs) -> list[dict]:
    if valeurs in (None, ""):
        return []
    if not isinstance(valeurs, list):
        raise serializers.ValidationError({"pages": "Liste attendue."})
    if len(valeurs) > PAGES_MAX:
        raise serializers.ValidationError({"pages": f"{PAGES_MAX} pages au plus."})
    pages, slugs = [], set()
    for entree in valeurs:
        if not isinstance(entree, dict):
            raise serializers.ValidationError({"pages": "Page invalide."})
        ident = entree.get("id") or secrets.token_hex(4)
        if not isinstance(ident, str) or not ID_PAGE.match(ident):
            raise serializers.ValidationError({"pages": "Identifiant de page invalide."})
        if any(p["id"] == ident for p in pages):
            raise serializers.ValidationError({"pages": "Page en double."})
        titre = _texte(entree.get("titre"), LONGUEUR_TITRE_PAGE, "pages")
        if len(titre) < 2:
            raise serializers.ValidationError({"pages": "Chaque page a besoin d'un titre."})
        image = entree.get("image") or None
        if image is not None and (not isinstance(image, str) or not UUID.match(image)):
            raise serializers.ValidationError({"pages": "Image invalide."})
        # Deux titres proches ne donnent jamais la meme adresse.
        base = slug = slug_de(titre)
        n = 2
        while slug in slugs:
            slug = f"{base}-{n}"
            n += 1
        slugs.add(slug)
        pages.append(
            {
                "id": ident,
                "titre": titre,
                "slug": slug,
                "accroche": _texte(entree.get("accroche"), LONGUEUR_ACCROCHE, "pages"),
                "contenu": _texte(
                    entree.get("contenu"), LONGUEUR_CONTENU_PAGE, "pages", lignes=True
                ),
                "image": image,
            }
        )
    return pages


def valider(donnees) -> dict:
    """La configuration propre, complete, ou ValidationError."""
    if not isinstance(donnees, dict):
        raise serializers.ValidationError("Configuration invalide.")
    inconnues = set(donnees) - {
        "police_titres",
        "police_texte",
        "menu",
        "sections",
        "accroche",
        "bouton_reserver",
        "pages",
    }
    if inconnues:
        raise serializers.ValidationError(f"Réglages inconnus : {', '.join(sorted(inconnues))}.")

    config = par_defaut()
    if "police_titres" in donnees:
        if donnees["police_titres"] not in POLICES:
            raise serializers.ValidationError({"police_titres": "Police non proposée."})
        config["police_titres"] = donnees["police_titres"]
    if "police_texte" in donnees:
        police = POLICES.get(donnees["police_texte"])
        if police is None or not police[2]:
            raise serializers.ValidationError(
                {"police_texte": "Police non proposée pour le texte courant."}
            )
        config["police_texte"] = donnees["police_texte"]

    config["pages"] = _pages(donnees.get("pages"))
    cles_menu = MENU + tuple(PREFIXE_PAGE + page["id"] for page in config["pages"])
    if "menu" in donnees:
        menu = donnees["menu"]
        if isinstance(menu, list):
            # Une page retiree emporte son entree de menu, sans erreur.
            menu = [
                entree
                for entree in menu
                if not (
                    isinstance(entree, dict)
                    and str(entree.get("cle", "")).startswith(PREFIXE_PAGE)
                    and entree["cle"] not in cles_menu
                )
            ]
        config["menu"] = _ordre(menu, cles_menu, "menu")
    else:
        config["menu"] = _ordre([], cles_menu, "menu")
    if "sections" in donnees:
        config["sections"] = _ordre(donnees["sections"], SECTIONS, "sections")
    config["accroche"] = _texte(donnees.get("accroche"), LONGUEUR_ACCROCHE, "accroche")
    config["bouton_reserver"] = _texte(
        donnees.get("bouton_reserver"), LONGUEUR_BOUTON, "bouton_reserver"
    )
    return config


def par_defaut() -> dict:
    return {
        "police_titres": "geist",
        "police_texte": "geist",
        "menu": [{"cle": cle, "visible": True} for cle in MENU],
        "sections": [{"cle": cle, "visible": True} for cle in SECTIONS],
        "accroche": "",
        "bouton_reserver": "",
        "pages": [],
    }


def complete(config: dict | None) -> dict:
    """Une configuration enregistree, completee des valeurs par defaut."""
    try:
        return valider(config or {})
    except serializers.ValidationError:
        return par_defaut()


def images_des_pages(config: dict) -> list[str]:
    return [page["image"] for page in config.get("pages", []) if page.get("image")]


def options() -> dict:
    return {
        "polices": [
            {"cle": cle, "nom": nom, "famille": famille, "texte": texte}
            for cle, (nom, famille, texte) in POLICES.items()
        ],
        "menu": list(MENU),
        "sections": list(SECTIONS),
        "pages_max": PAGES_MAX,
        "longueurs": {
            "accroche": LONGUEUR_ACCROCHE,
            "bouton_reserver": LONGUEUR_BOUTON,
            "titre_page": LONGUEUR_TITRE_PAGE,
            "contenu_page": LONGUEUR_CONTENU_PAGE,
        },
    }
