"""Limites de debit, et le seul appelant qu'elles ne comptent pas.

---------------------------------------------------------------------------
Le probleme, qui n'existe qu'en production
---------------------------------------------------------------------------

Les limites sont tenues par adresse IP. Derriere le proxy, celle d'un
visiteur arrive dans `X-Forwarded-For`, que le proxy ecrase a chaque
requete : chaque navigateur a bien son propre compteur.

Mais une partie des lectures publiques ne vient d'aucun navigateur. Pour
rendre la page d'un mini-site, le serveur Next demande lui-meme la vitrine
et les avis du salon, directement sur le reseau interne, sans passer par le
proxy — donc sans `X-Forwarded-For`, depuis sa propre adresse. Toutes ces
lectures, pour tous les salons et tous les visiteurs, tombaient dans **un
seul** compteur `public_read` de 120 requetes par minute. Au-dela, les
pages des mini-sites echouaient en 429 — un robot d'indexation suffisait.

En developpement le defaut est invisible : un seul visiteur, un seul salon.

---------------------------------------------------------------------------
La reponse
---------------------------------------------------------------------------

Le serveur de rendu se presente avec un jeton partage, `INTERNAL_API_TOKEN`,
et n'est alors pas compte. Ses propres appels restent bornes par le cache
de Next — quinze secondes par salon et par langue — et non par ce compteur.

Sans jeton configure, personne n'est exempte : l'absence de reglage retombe
sur le comportement d'origine, jamais sur une porte ouverte. La comparaison
se fait a temps constant, pour qu'on ne puisse pas deviner le jeton
caractere par caractere en mesurant les temps de reponse.
"""

from __future__ import annotations

import hmac

from django.conf import settings
from rest_framework import throttling

ENTETE = "X-Internal-Token"


def appel_du_serveur_de_rendu(request) -> bool:
    """La requete vient-elle du serveur Next, jeton a l'appui ?"""
    attendu = getattr(settings, "INTERNAL_API_TOKEN", "")
    if not attendu:
        return False
    recu = request.headers.get(ENTETE, "")
    return hmac.compare_digest(recu.encode(), attendu.encode())


class ScopedRateThrottle(throttling.ScopedRateThrottle):
    """La limite par portee de DRF, moins les appels du serveur de rendu."""

    def allow_request(self, request, view) -> bool:
        if appel_du_serveur_de_rendu(request):
            return True
        return super().allow_request(request, view)
