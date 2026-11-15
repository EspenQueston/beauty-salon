"""Quelle langue la requete demande-t-elle ?

Deux sources, dans cet ordre :

1. `?lang=en` — ce que passe le mini-site. Le serveur Next connait deja la
   langue de la page : c'est son segment `[locale]`, deduit de l'URL publique.
   Il vaut mieux qu'il la dise que la faire redeviner ici.
2. `Accept-Language` — pour un appel direct a l'API, ou pour un client qui ne
   passe rien.

Une langue inconnue vaut le francais. Ce n'est pas une erreur a signaler : une
langue non servie ne casse rien, elle renvoie simplement la version source.
"""

from __future__ import annotations

#: Les langues que le contenu peut prendre. Le francais est la source.
LANGUES = ("fr", "en")
LANGUE_SOURCE = "fr"


def demandee(request) -> str:
    """La langue a servir pour cette requete."""
    explicite = (request.GET.get("lang") or "").strip().lower()
    if explicite in LANGUES:
        return explicite

    entete = request.headers.get("Accept-Language", "")
    for morceau in entete.split(","):
        racine = morceau.split(";")[0].strip().lower().split("-")[0]
        if racine in LANGUES:
            return racine

    return LANGUE_SOURCE


def table_pour(request, tenant_id) -> dict[tuple[str, str, str], str]:
    """Les traductions a poser dans le contexte du serialiseur.

    Vide quand la langue demandee est la langue source : il n'y a alors rien a
    remplacer, et la requete SQL serait perdue.
    """
    langue = demandee(request)
    if langue == LANGUE_SOURCE:
        return {}

    from .services import table_du_salon

    return table_du_salon(tenant_id, langue)


def du_compte(user) -> str:
    """La langue dans laquelle ecrire a ce compte, hors de toute requete.

    Les notifications, les e-mails au salon, les rappels d'abonnement partent
    d'une tache : il n'y a plus d'en-tete a lire. C'est la langue que la
    personne a choisie dans son espace, retenue sur son compte
    (`User.locale`), qui decide. Une valeur inconnue — un compte cree avant,
    une saisie d'administration — vaut le francais.
    """
    return normaliser(getattr(user, "locale", ""))


def normaliser(valeur) -> str:
    """« en-GB », « EN », None : une langue servie, ou le francais."""
    racine = (valeur or "").strip().lower()[:2]
    return racine if racine in LANGUES else LANGUE_SOURCE


def prefixe(langue) -> str:
    """Le debut de chemin d'une langue sur le site : rien pour le francais,
    « /en » pour l'anglais — la meme regle que les adresses du site."""
    langue = normaliser(langue)
    return "" if langue == LANGUE_SOURCE else f"/{langue}"


def adresse_app(chemin: str, langue) -> str:
    """Un lien vers l'espace pro, qui s'ouvre dans la langue du destinataire.

    Sans le prefixe, la page s'ouvrirait selon le cookie ou le navigateur de
    l'appareil : un lien d'e-mail anglais ouvert sur un telephone regle en
    francais montrerait une page francaise.
    """
    from django.conf import settings

    return f"{settings.APP_BASE_URL.rstrip('/')}{prefixe(langue)}{chemin}"


def par_langue(lignes) -> dict[str, list]:
    """Regroupe des paires (valeur, langue du compte) par langue.

    Sert a ecrire une fois par langue a un groupe de destinataires : la
    proprietaire en francais, la gerante en anglais. Les valeurs vides (un
    compte sans adresse) sont ecartees, les doublons aussi.
    """
    groupes: dict[str, list] = {}
    for valeur, locale in lignes:
        if not valeur:
            continue
        groupe = groupes.setdefault(normaliser(locale), [])
        if valeur not in groupe:
            groupe.append(valeur)
    return groupes
