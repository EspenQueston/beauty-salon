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
