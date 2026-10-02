"""Expiration des sessions apres inactivite.

Le cookie de session vit 14 jours (`SESSION_COOKIE_AGE`) : une duree
absolue. Sans plus, un poste oublie ouvert dans un salon — ou un telephone
perdu — gardait l'acces pendant deux semaines. On ferme donc aussi la
session quand elle n'a servi a rien depuis :

  - `SESSION_IDLE_TIMEOUT` (3 jours par defaut) pour l'equipe des salons et
    les clientes ;
  - `SESSION_IDLE_TIMEOUT_ADMIN` (8 heures) pour l'administration
    plateforme, qui voit tous les salons.

L'heure d'activite n'est reecrite qu'une fois toutes les cinq minutes : une
ecriture en base a chaque requete couterait cher pour une precision inutile.
"""

from __future__ import annotations

import time

from django.conf import settings
from django.contrib.auth import logout

CLE = "derniere_activite"
RAFRAICHISSEMENT = 5 * 60


def delai_inactivite(user) -> int:
    if getattr(user, "is_staff", False):
        return int(getattr(settings, "SESSION_IDLE_TIMEOUT_ADMIN", 8 * 60 * 60))
    return int(getattr(settings, "SESSION_IDLE_TIMEOUT", 3 * 24 * 60 * 60))


class SessionInactiveMiddleware:
    """Ferme une session restee inactive trop longtemps. Apres l'authentification."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            maintenant = int(time.time())
            derniere = request.session.get(CLE)
            if derniere is not None and maintenant - int(derniere) > delai_inactivite(user):
                # `logout` vide la session et remplace l'utilisateur par un
                # anonyme : la suite de la requete est traitee comme telle.
                logout(request)
            elif derniere is None or maintenant - int(derniere) > RAFRAICHISSEMENT:
                request.session[CLE] = maintenant
        return self.get_response(request)
