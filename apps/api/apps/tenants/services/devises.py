"""Taux de change, et ce qu'on fait quand on ne les a pas.

---------------------------------------------------------------------------
A quoi ca sert
---------------------------------------------------------------------------

Un salon change de devise deux fois dans sa vie : quand il s'est trompe a
l'inscription, et quand il demenage. Les deux fois, son catalogue entier
doit suivre - une pose a 25 000 francs CFA ne vaut pas 25 000 yuans, elle
en vaut environ 293.

Le taux vient de currencyapi.com. Il est mis en cache douze heures : les
parites XAF/CNY bougent de quelques dixiemes de pour cent par jour, et
personne ne bascule de devise assez souvent pour justifier un appel reseau
a chaque affichage d'ecran.

---------------------------------------------------------------------------
Pourquoi l'echec est un refus, jamais une valeur par defaut
---------------------------------------------------------------------------

La tentation, quand l'API ne repond pas, est de convertir quand meme avec
un taux approximatif « en attendant ». Ce serait la pire des issues : le
salon verrait son catalogue converti, ne saurait pas que le taux est faux,
et facturerait a ce prix-la pendant des mois. Une erreur de dix pour cent
sur toute une grille tarifaire ne se rattrape pas.

`TauxIndisponible` remonte donc jusqu'a l'ecran, qui dit au salon de
reessayer plus tard. Ses prix restent dans leur devise d'origine, ce qui est
au moins exact.
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

API = "https://api.currencyapi.com/v3/latest"
TIMEOUT = 8

# Douze heures. Assez court pour qu'un taux ne devienne jamais absurde,
# assez long pour qu'une journee de travail ne consomme qu'un appel.
CACHE_SECONDS = 12 * 60 * 60


class TauxIndisponible(Exception):
    """Message destine a l'utilisatrice, en francais."""


def taux(source: str, cible: str) -> Decimal:
    """Combien vaut une unite de `source` en `cible`.

    Renvoie un `Decimal` : la suite du calcul touche a des prix, et un
    flottant y introduirait des centimes fantomes.
    """
    source = source.upper()
    cible = cible.upper()
    if source == cible:
        return Decimal("1")

    cle = f"fx:{source}:{cible}"
    en_cache = cache.get(cle)
    if en_cache is not None:
        return Decimal(en_cache)

    valeur = _interroger(source, cible)
    # La chaine, pas le Decimal : le cache serialise, et un Decimal qui
    # transite par pickle revient parfois en float selon le backend.
    cache.set(cle, str(valeur), CACHE_SECONDS)
    return valeur


def _interroger(source: str, cible: str) -> Decimal:
    cle_api = getattr(settings, "CURRENCY_API_KEY", "")
    if not cle_api:
        raise TauxIndisponible(
            "Aucune clé de taux de change n'est configurée sur ce serveur."
        )

    adresse = f"{API}?" + urlencode(
        {"apikey": cle_api, "base_currency": source, "currencies": cible}
    )

    try:
        requete = Request(adresse, headers={"Accept": "application/json"})
        with urlopen(requete, timeout=TIMEOUT) as reponse:  # noqa: S310 - adresse fixe
            charge = json.loads(reponse.read().decode("utf-8"))
    except (URLError, OSError, ValueError, json.JSONDecodeError) as exc:
        # L'exception d'origine part dans les journaux, pas a l'ecran : elle
        # contient l'adresse, donc la cle d'API.
        logger.warning("Taux de change indisponible (%s -> %s) : %s", source, cible, exc)
        raise TauxIndisponible(
            "Le service de taux de change ne répond pas. Réessayez dans un moment."
        ) from None

    ligne = (charge.get("data") or {}).get(cible)
    valeur = (ligne or {}).get("value")
    if valeur is None:
        raise TauxIndisponible(
            f"Le service de taux de change ne connaît pas la devise {cible}."
        )

    # Par la chaine : `Decimal(0.0117)` traine les approximations du
    # flottant, `Decimal("0.0117")` non.
    taux_decimal = Decimal(str(valeur))
    if taux_decimal <= 0:
        raise TauxIndisponible("Le taux de change reçu est inexploitable.")
    return taux_decimal
