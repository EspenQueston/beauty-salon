"""Les coordonnees d'une cliente, telles que le mini-site les accepte.

---------------------------------------------------------------------------
La regle, decidee avec le produit
---------------------------------------------------------------------------

  - **Telephone** : obligatoire, uniquement des chiffres — 6 au moins, 15 au
    plus (le maximum international). Un « + » est admis en tete, et
    seulement la : un numero WhatsApp s'ecrit avec son indicatif (+86,
    +242…). Les espaces d'un numero colle sont retires ; toute lettre ou
    autre signe est refuse, pas nettoye.
  - **E-mail** : obligatoire, avec un « @ » et un domaine (voir le
    serializer de reservation).

---------------------------------------------------------------------------
Retrouver une cliente
---------------------------------------------------------------------------

Le telephone fait office d'identite. Des fiches anciennes le gardent avec
ses espaces (« +86 136 1234 5678 ») : la comparaison se fait donc sur les
seuls chiffres, en base, pour ne pas creer une seconde fiche a la meme
personne.
"""

from __future__ import annotations

import re

from django.db.models import F, Func, QuerySet, Value

CHIFFRES_MIN = 6
CHIFFRES_MAX = 15
_FORME = re.compile(r"^\+?[0-9]+$")


class TelephoneInvalide(ValueError):
    pass


def normaliser_telephone(valeur: str) -> str:
    """Le numero tel qu'il sera enregistre : « +8613612345678 », ou TelephoneInvalide."""
    numero = re.sub(r"\s+", "", valeur or "")
    if not numero:
        raise TelephoneInvalide("Indiquez votre numéro de téléphone.")
    if not _FORME.match(numero):
        raise TelephoneInvalide(
            "Le numéro ne doit contenir que des chiffres (un « + » est accepté au début)."
        )
    chiffres = numero.lstrip("+")
    if len(chiffres) < CHIFFRES_MIN:
        raise TelephoneInvalide(f"Le numéro doit compter au moins {CHIFFRES_MIN} chiffres.")
    if len(chiffres) > CHIFFRES_MAX:
        raise TelephoneInvalide(f"Le numéro compte au plus {CHIFFRES_MAX} chiffres.")
    return numero


def chiffres(valeur: str) -> str:
    return re.sub(r"\D", "", valeur or "")


def memes_chiffres(clientes: QuerySet, telephone: str) -> QuerySet:
    """Les fiches dont le telephone a les memes chiffres, la plus ancienne d'abord."""
    cible = chiffres(telephone)
    if not cible:
        return clientes.none()
    return (
        clientes.annotate(
            _chiffres=Func(
                F("phone"), Value(r"\D"), Value(""), Value("g"), function="regexp_replace"
            )
        )
        .filter(_chiffres=cible)
        .order_by("created_at")
    )
