"""L'espace professionnel ne repond qu'a l'espace professionnel.

Le cookie de session vaut pour tout `.{PLATFORM_DOMAIN}` : l'espace pro
(`app.`), l'API (`api.`) et chaque mini-site (`{salon}.`). C'est voulu — une
cliente garde sa session d'un salon a l'autre — mais une gerante ou un
administrateur qui visite un mini-site y porte aussi la sienne. Un script
injecte dans un mini-site pourrait alors appeler l'API de l'espace pro en son
nom (audit du 16/10/2026, C-09).

Ce middleware ferme cette porte : une requete **d'un navigateur** (elle porte
un en-tete `Origin`) vers une route de l'espace pro n'est acceptee que depuis
l'espace pro lui-meme. Les mini-sites gardent ce dont ils ont besoin, et
seulement cela :

  - `/api/v1/public/` : le salon, la reservation, l'acompte, l'espace cliente ;
  - `/api/v1/account/`, `/api/v1/auth/`, `/api/v1/csrf` : compte et connexion ;
  - `/api/v1/push` : les notifications de la cliente.

Une requete sans `Origin` (meme origine, serveur Next, webhook d'un
prestataire) n'est pas concernee : un script d'une autre origine, lui,
l'envoie toujours.
"""

from __future__ import annotations

import logging
from urllib.parse import urlsplit

from django.conf import settings
from django.http import JsonResponse

logger = logging.getLogger(__name__)

API = "/api/v1/"
OUVERTES_AUX_MINI_SITES = (
    "/api/v1/public/",
    "/api/v1/account/",
    "/api/v1/auth/",
    "/api/v1/csrf",
    "/api/v1/push",
    # Serveur a serveur, sans navigateur : jamais d'Origin legitime, et deja
    # authentifies autrement (signature, secret partage).
    "/api/v1/webhooks/",
)


def hotes_espace_pro() -> set[str]:
    domaine = settings.PLATFORM_DOMAIN
    return {f"app.{domaine}", f"api.{domaine}"} | set(
        getattr(settings, "ESPACE_PRO_HOTES_SUPPLEMENTAIRES", ())
    )


class OrigineEspaceProMiddleware:
    """Refuse a un mini-site les routes de l'espace pro (403 `origine_refusee`)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        chemin = request.path
        origine = request.headers.get("Origin")
        if (
            origine
            and chemin.startswith(API)
            and not chemin.startswith(OUVERTES_AUX_MINI_SITES)
        ):
            hote = (urlsplit(origine).hostname or "").lower()
            if hote not in hotes_espace_pro():
                logger.warning("Origine refusee pour l'espace pro : %s -> %s", hote, chemin)
                return JsonResponse(
                    {
                        "detail": "Cette action n'est possible que depuis l'espace professionnel.",
                        "code": "origine_refusee",
                    },
                    status=403,
                )
        return self.get_response(request)
