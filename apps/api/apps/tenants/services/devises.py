"""Taux de change, et ce qu'on fait quand on ne les a pas.

---------------------------------------------------------------------------
A quoi ca sert
---------------------------------------------------------------------------

Deux usages, deux exigences :

  - **convertir un catalogue** (le salon change de devise) : un prix ecrit
    pour des mois. Le taux doit etre frais, sinon on refuse ;
  - **aider a lire** (la visiteuse du mini-site choisit d'afficher les prix
    dans sa monnaie) : un « ≈ » a titre indicatif. Un taux de la veille
    vaut mieux qu'un bouton qui ne fait rien.

---------------------------------------------------------------------------
D'ou viennent les taux
---------------------------------------------------------------------------

De currencyapi.com quand une cle est configuree, sinon (ou s'il echoue) de
open.er-api.com, gratuit et sans cle. Chaque appel ramene **toutes** les
devises proposees pour une devise de depart, mises en cache douze heures :
trois devises de salon, deux appels par jour chacune au plus. L'ancienne
facon — une paire par appel — epuisait le quota mensuel de currencyapi
(300 appels) des que les visiteuses essayaient plusieurs monnaies.

Le dernier taux obtenu est garde sept jours a part. Il ne sert qu'a l'aide a
la lecture (`perime_accepte=True`), jamais a la conversion d'un catalogue.

---------------------------------------------------------------------------
Pourquoi l'echec est un refus, jamais une valeur par defaut
---------------------------------------------------------------------------

La tentation, quand aucun service ne repond, est de convertir quand meme
avec un taux approximatif « en attendant ». Ce serait la pire des issues :
le salon verrait son catalogue converti, ne saurait pas que le taux est
faux, et facturerait a ce prix-la pendant des mois.

`TauxIndisponible` remonte donc jusqu'a l'ecran, qui dit de reessayer plus
tard. Les prix restent dans leur devise d'origine, ce qui est au moins exact.
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal, InvalidOperation
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

CURRENCYAPI = "https://api.currencyapi.com/v3/latest"
OPEN_ER_API = "https://open.er-api.com/v6/latest/{source}"
TIMEOUT = 8

# Toutes les devises que la plateforme sait afficher : demandees d'un coup.
DEVISES = ("XAF", "CNY", "CDF", "EUR", "USD")

# Douze heures. Assez court pour qu'un taux ne devienne jamais absurde,
# assez long pour qu'une journee de travail ne consomme qu'un appel.
CACHE_SECONDS = 12 * 60 * 60
# Le filet de l'aide a la lecture quand tous les services sont muets.
SECOURS_SECONDS = 7 * 24 * 60 * 60


class TauxIndisponible(Exception):
    """Message destine a l'utilisatrice, en francais."""


def taux(source: str, cible: str, *, perime_accepte: bool = False) -> Decimal:
    """Combien vaut une unite de `source` en `cible`.

    Renvoie un `Decimal` : la suite du calcul touche a des prix, et un
    flottant y introduirait des centimes fantomes.

    `perime_accepte` : a defaut de taux frais, accepter le dernier connu
    (sept jours au plus). Pour l'affichage indicatif seulement.
    """
    source = source.upper()
    cible = cible.upper()
    if source == cible:
        return Decimal("1")

    table = cache.get(f"fx:{source}")
    if table is None:
        try:
            table = _interroger(source)
        except TauxIndisponible:
            secours = cache.get(f"fx:secours:{source}") if perime_accepte else None
            if secours and cible in secours:
                return Decimal(secours[cible])
            raise
        # Des chaines, pas des Decimal : le cache serialise, et un Decimal
        # qui transite par pickle revient parfois en float selon le backend.
        cache.set(f"fx:{source}", table, CACHE_SECONDS)
        cache.set(f"fx:secours:{source}", table, SECOURS_SECONDS)

    if cible not in table:
        raise TauxIndisponible(f"Le service de taux de change ne connaît pas la devise {cible}.")
    return Decimal(table[cible])


def _interroger(source: str) -> dict[str, str]:
    """Les taux de `source` vers chaque devise proposee, du premier service qui repond."""
    erreurs = []
    for fournisseur in (_currencyapi, _open_er_api):
        try:
            table = fournisseur(source)
        except _Echec as exc:
            erreurs.append(f"{fournisseur.__name__}: {exc}")
            continue
        if table:
            return table
        erreurs.append(f"{fournisseur.__name__}: reponse vide")
    # L'exception d'origine part dans les journaux, pas a l'ecran : elle
    # peut contenir l'adresse, donc la cle d'API.
    logger.warning("Taux de change indisponible depuis %s : %s", source, " ; ".join(erreurs))
    raise TauxIndisponible("Le service de taux de change ne répond pas. Réessayez dans un moment.")


class _Echec(Exception):
    pass


def _lire(adresse: str) -> dict:
    try:
        requete = Request(adresse, headers={"Accept": "application/json"})
        with urlopen(requete, timeout=TIMEOUT) as reponse:  # noqa: S310 - adresses fixes
            return json.loads(reponse.read().decode("utf-8"))
    except (URLError, OSError, ValueError) as exc:
        # Sans l'adresse : elle porte la cle d'API.
        raise _Echec(type(exc).__name__ + " " + str(getattr(exc, "code", "") or "")) from None


def _garder(brut: dict) -> dict[str, str]:
    """Les devises proposees, en chaines, et seulement des taux strictement positifs."""
    table = {}
    for code in DEVISES:
        valeur = brut.get(code)
        if valeur is None:
            continue
        try:
            # Par la chaine : `Decimal(0.0117)` traine les approximations du
            # flottant, `Decimal("0.0117")` non.
            decimal = Decimal(str(valeur))
        except InvalidOperation:
            continue
        if decimal > 0:
            table[code] = str(decimal)
    return table


def _currencyapi(source: str) -> dict[str, str]:
    cle_api = getattr(settings, "CURRENCY_API_KEY", "")
    if not cle_api:
        raise _Echec("pas de cle")
    adresse = f"{CURRENCYAPI}?" + urlencode(
        {"apikey": cle_api, "base_currency": source, "currencies": ",".join(DEVISES)}
    )
    charge = _lire(adresse)
    lignes = charge.get("data") or {}
    return _garder({code: (ligne or {}).get("value") for code, ligne in lignes.items()})


def _open_er_api(source: str) -> dict[str, str]:
    charge = _lire(OPEN_ER_API.format(source=source))
    if charge.get("result") != "success":
        raise _Echec(str(charge.get("error-type") or "echec"))
    return _garder(charge.get("rates") or {})
