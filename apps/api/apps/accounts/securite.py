"""Freins contre la force brute et l'envoi d'e-mails en rafale.

---------------------------------------------------------------------------
Ce que le frein par adresse IP ne couvrait pas
---------------------------------------------------------------------------

Les limites DRF (`throttle_scope`) comptent par adresse IP. Un essai de mots
de passe distribue — dix adresses IP, cent essais chacune, sur un meme
compte — passait dessous sans bruit. On compte donc aussi **par adresse
e-mail visee**, que le compte existe ou non : la reponse est identique dans
les deux cas, et le frein ne revele donc rien de l'annuaire.

Meme raisonnement pour « mot de passe oublie » : borne par IP, on pouvait
quand meme bombarder la boite d'une victime depuis plusieurs adresses. Un
delai par adresse e-mail l'empeche, en silence (la reponse publique reste
la meme).

Tout vit dans le cache (Redis) : des compteurs qui expirent seuls, rien en
base, aucune donnee personnelle en clair (les cles sont des empreintes).
"""

from __future__ import annotations

import hashlib
import hmac

from django.conf import settings
from django.core.cache import cache

# Connexion : 5 echecs en 15 minutes sur une meme adresse, ou 30 depuis une
# meme IP, suspendent les essais pour le reste de la fenetre.
ECHECS_PAR_ADRESSE = 5
ECHECS_PAR_IP = 30
FENETRE_CONNEXION = 15 * 60

# E-mails declenches par un formulaire public : un toutes les deux minutes,
# six par jour au plus, par adresse.
DELAI_ENVOI = 2 * 60
ENVOIS_PAR_JOUR = 6


def _empreinte(valeur: str) -> str:
    return hmac.new(
        settings.SECRET_KEY.encode(), valeur.strip().lower().encode(), hashlib.sha256
    ).hexdigest()[:32]


def _incrementer(cle: str, duree: int) -> int:
    # `add` pose la cle avec son expiration seulement si elle n'existe pas :
    # la fenetre part du premier echec, et `incr` ne la prolonge pas.
    cache.add(cle, 0, duree)
    try:
        return cache.incr(cle)
    except ValueError:  # expiree entre les deux appels
        cache.set(cle, 1, duree)
        return 1


# ---------------------------------------------------------------------------
# Connexion
# ---------------------------------------------------------------------------


def connexion_bloquee(email: str, ip: str) -> bool:
    """Vrai si les essais sur cette adresse, ou depuis cette IP, sont suspendus."""
    par_adresse = cache.get(f"auth:echecs:mail:{_empreinte(email)}", 0)
    par_ip = cache.get(f"auth:echecs:ip:{_empreinte(ip)}", 0) if ip else 0
    return par_adresse >= ECHECS_PAR_ADRESSE or par_ip >= ECHECS_PAR_IP


def noter_echec(email: str, ip: str) -> bool:
    """Compte l'echec ; vrai si c'est celui qui declenche le blocage de l'adresse.

    L'appelant journalise alors le blocage et previent l'equipe — une fois
    par fenetre, pas a chaque essai qui suit.
    """
    par_adresse = _incrementer(f"auth:echecs:mail:{_empreinte(email)}", FENETRE_CONNEXION)
    if ip:
        _incrementer(f"auth:echecs:ip:{_empreinte(ip)}", FENETRE_CONNEXION)
    return par_adresse == ECHECS_PAR_ADRESSE


def noter_succes(email: str) -> None:
    """Une connexion reussie remet le compteur de l'adresse a zero (pas celui de l'IP)."""
    cache.delete(f"auth:echecs:mail:{_empreinte(email)}")


# ---------------------------------------------------------------------------
# E-mails declenches depuis un formulaire public
# ---------------------------------------------------------------------------


def envoi_autorise(genre: str, email: str) -> bool:
    """Peut-on envoyer encore un e-mail de ce genre a cette adresse ?

    A appeler avant chaque envoi. Un refus est silencieux pour l'appelant :
    la reponse publique ne change pas, seul l'e-mail ne part pas.
    """
    cle = _empreinte(email)
    if not cache.add(f"envoi:{genre}:recent:{cle}", 1, DELAI_ENVOI):
        return False
    return _incrementer(f"envoi:{genre}:jour:{cle}", 24 * 60 * 60) <= ENVOIS_PAR_JOUR
