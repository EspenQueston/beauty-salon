"""Ce que le serveur a le droit d'aller joindre.

---------------------------------------------------------------------------
Le risque, en une phrase
---------------------------------------------------------------------------

Des qu'une adresse fournie par un utilisateur decide ou le serveur envoie
une requete, cet utilisateur emprunte notre place sur le reseau. Il peut
alors atteindre ce que nous atteignons et qu'il n'atteint pas : la base de
donnees, un service interne sans authentification, ou — le cas classique —
`169.254.169.254`, l'adresse ou les hebergeurs cloud servent les
identifiants de la machine.

C'est la faille dite SSRF, et elle se referme mal une fois ouverte.

---------------------------------------------------------------------------
Pourquoi une liste noire ne suffirait pas
---------------------------------------------------------------------------

Interdire « localhost » et « 127.0.0.1 » ne protege de rien : `0.0.0.0`,
`[::1]`, `2130706433` et un nom de domaine public pointant vers 127.0.0.1
mènent tous au meme endroit. La seule regle qui tienne est de **resoudre**
le nom et de juger l'adresse obtenue.

Ce module est commun a l'import de medias et aux abonnements push : deux
copies d'une regle de securite finissent toujours par diverger, et c'est
celle qu'on a oublie de corriger qui sert.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


class AdresseInterdite(ValueError):
    """L'adresse vise un reseau que le serveur ne doit pas atteindre."""


def verifier_adresse_publique(
    url: str, *, schemes: tuple[str, ...] = ("http", "https")
) -> None:
    """Leve `AdresseInterdite` si l'adresse ne doit pas etre jointe.

    Ne rend rien : elle passe, ou elle leve. Les messages sont rediges pour
    etre montres tels quels — ils sont lus par une gerante qui colle un lien,
    pas par un developpeur.
    """
    parts = urlparse(url)

    if parts.scheme not in schemes:
        attendus = " et ".join(schemes)
        raise AdresseInterdite(f"Seules les adresses {attendus} sont acceptées.")
    if not parts.hostname:
        raise AdresseInterdite("Cette adresse est incomplète.")

    try:
        infos = socket.getaddrinfo(parts.hostname, parts.port or 0)
    except socket.gaierror as exc:
        raise AdresseInterdite(
            "Ce nom de domaine est introuvable. Vérifiez le lien."
        ) from exc

    for *_, sockaddr in infos:
        address = ipaddress.ip_address(sockaddr[0])
        if not address.is_global or address.is_multicast:
            # `is_global` couvre d'un coup le bouclage, les plages privees,
            # le lien-local (dont 169.254.169.254, les metadonnees cloud) et
            # les plages reservees.
            raise AdresseInterdite(
                "Cette adresse pointe vers un réseau interne et ne peut pas "
                "être importée."
            )
