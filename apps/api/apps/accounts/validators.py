"""Refus des mots de passe deja publies dans des fuites de donnees.

---------------------------------------------------------------------------
Comment, sans rien divulguer
---------------------------------------------------------------------------

Le service « Have I Been Pwned » (api.pwnedpasswords.com) recense des
centaines de millions de mots de passe sortis de fuites. On l'interroge par
**k-anonymat** : seuls les 5 premiers caracteres de l'empreinte SHA-1 du mot
de passe quittent le serveur ; la reponse liste toutes les fins d'empreintes
qui commencent ainsi (avec un rembourrage aleatoire, `Add-Padding`), et la
comparaison se fait ici. Ni le mot de passe, ni son empreinte complete ne
sont transmis.

---------------------------------------------------------------------------
Quand le service ne repond pas
---------------------------------------------------------------------------

On laisse passer (le mot de passe reste soumis aux autres regles : longueur,
mots courants, chiffres seuls...) et on le journalise. Bloquer toutes les
inscriptions parce qu'un service tiers est lent serait pire que le risque.
Les reponses sont gardees 24 h en cache : elles ne disent rien de personne.
"""

from __future__ import annotations

import hashlib
import logging
from urllib.error import URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)

API = "https://api.pwnedpasswords.com/range/{prefixe}"
TIMEOUT = 3


def _suffixes(prefixe: str) -> dict[str, int] | None:
    cle = f"hibp:{prefixe}"
    en_cache = cache.get(cle)
    if en_cache is not None:
        return en_cache
    try:
        requete = Request(
            API.format(prefixe=prefixe),
            headers={"Add-Padding": "true", "User-Agent": "BeautySalon-PasswordCheck"},
        )
        with urlopen(requete, timeout=TIMEOUT) as reponse:  # noqa: S310 - adresse fixe
            texte = reponse.read().decode("utf-8")
    except (URLError, OSError, ValueError) as exc:
        logger.warning("Verification des fuites indisponible : %s", type(exc).__name__)
        return None
    table = {}
    for ligne in texte.splitlines():
        suffixe, _, nombre = ligne.strip().partition(":")
        if suffixe and nombre.isdigit() and int(nombre) > 0:
            table[suffixe.upper()] = int(nombre)
    cache.set(cle, table, 24 * 60 * 60)
    return table


def occurrences(mot_de_passe: str) -> int | None:
    """Combien de fois ce mot de passe apparait dans les fuites (None : inconnu)."""
    empreinte = hashlib.sha1(mot_de_passe.encode("utf-8")).hexdigest().upper()  # noqa: S324
    table = _suffixes(empreinte[:5])
    if table is None:
        return None
    return table.get(empreinte[5:], 0)


class PwnedPasswordValidator:
    """Validateur Django : refuse un mot de passe connu des fuites."""

    def validate(self, password, user=None):
        if not getattr(settings, "PWNED_PASSWORDS_CHECK", True):
            return
        vu = occurrences(password)
        if vu:
            from .journal import consigner

            consigner("AUTH_PASSWORD_BREACHED", user=user, vues=vu)
            raise ValidationError(
                "Ce mot de passe figure dans des fuites de données connues : il est déjà "
                "essayé par les pirates. Choisissez-en un autre.",
                code="password_breached",
            )

    def get_help_text(self):
        return "Votre mot de passe ne doit pas figurer dans une fuite de données connue."
