"""Personnalisation avancee du mini-site (offre Pro).

---------------------------------------------------------------------------
Des choix, pas du code
---------------------------------------------------------------------------

Le salon choisit parmi des options fermees : une police dans une liste,
l'ordre et la visibilite de rubriques connues, deux textes courts. Aucun
champ n'accepte de HTML, de CSS ni de script — ce qui n'est pas dans ces
listes est refuse, pas nettoye. Les textes sont du texte brut, affiches
echappes par React comme tout contenu de salon.

C'est ce qui permet d'ouvrir la personnalisation sans ouvrir de faille :
un mini-site partage son domaine parent avec l'espace professionnel.
"""

from __future__ import annotations

from rest_framework import serializers

POLICES = {
    "geist": "Geist (par défaut)",
    "playfair": "Playfair Display",
    "cormorant": "Cormorant Garamond",
    "dm-serif": "DM Serif Display",
    "lora": "Lora",
    "montserrat": "Montserrat",
    "poppins": "Poppins",
    "josefin": "Josefin Sans",
    "nunito": "Nunito",
}

# Les rubriques du menu, dans l'ordre par defaut.
MENU = ("prestations", "realisations", "equipe", "a-propos", "infos")

# Les sections de l'accueil entre l'en-tete et l'appel final, qui restent
# a leur place : l'une presente le salon, l'autre invite a reserver.
SECTIONS = ("prestations", "etapes", "realisations", "equipe", "avis", "infos")

LONGUEUR_ACCROCHE = 160
LONGUEUR_BOUTON = 28


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


def _texte(valeur, longueur: int, nom: str) -> str:
    if valeur in (None, ""):
        return ""
    if not isinstance(valeur, str):
        raise serializers.ValidationError({nom: "Texte attendu."})
    texte = " ".join(valeur.split())
    if len(texte) > longueur:
        raise serializers.ValidationError({nom: f"{longueur} caractères au plus."})
    if "<" in texte or ">" in texte:
        raise serializers.ValidationError({nom: "Les chevrons < et > ne sont pas acceptés."})
    return texte


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
    }
    if inconnues:
        raise serializers.ValidationError(f"Réglages inconnus : {', '.join(sorted(inconnues))}.")

    config = par_defaut()
    for cle in ("police_titres", "police_texte"):
        if cle in donnees:
            if donnees[cle] not in POLICES:
                raise serializers.ValidationError({cle: "Police non proposée."})
            config[cle] = donnees[cle]
    if "menu" in donnees:
        config["menu"] = _ordre(donnees["menu"], MENU, "menu")
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
    }


def complete(config: dict | None) -> dict:
    """Une configuration enregistree, completee des valeurs par defaut."""
    try:
        return valider(config or {})
    except serializers.ValidationError:
        return par_defaut()


def options() -> dict:
    return {
        "polices": [{"cle": cle, "nom": nom} for cle, nom in POLICES.items()],
        "menu": list(MENU),
        "sections": list(SECTIONS),
        "longueurs": {"accroche": LONGUEUR_ACCROCHE, "bouton_reserver": LONGUEUR_BOUTON},
    }
