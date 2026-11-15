"""Expiration des sessions : apres inactivite, et au plus tard apres 14 jours.

Le cookie de session vit 14 jours (`SESSION_COOKIE_AGE`), mais Django le
repousse a chaque ecriture de la session : sans plus, une session servie
regulierement ne finissait jamais. On ferme donc la session :

  - apres `SESSION_IDLE_TIMEOUT` sans activite (3 jours) pour l'equipe des
    salons et les clientes, `SESSION_IDLE_TIMEOUT_ADMIN` (8 heures) pour
    l'administration plateforme, qui voit tous les salons ;
  - dans tous les cas `SESSION_ABSOLUTE_TIMEOUT` apres la connexion
    (14 jours), quelle que soit l'activite.

Une requete de fond — le rafraichissement automatique des notifications ou
de l'abonnement, marque `X-Activite: fond` — n'est pas une activite : un
onglet laisse ouvert sur le comptoir ne garde plus la session en vie
indefiniment (audit du 16/10/2026, C-05).

L'heure d'activite n'est reecrite qu'une fois toutes les cinq minutes : une
ecriture en base a chaque requete couterait cher pour une precision inutile.
"""

from __future__ import annotations

import time

from django.conf import settings
from django.contrib.auth import logout
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

CLE = "derniere_activite"
CLE_CONNEXION = "connecte_le"
RAFRAICHISSEMENT = 5 * 60
EN_TETE_FOND = "fond"


def delai_inactivite(user) -> int:
    if getattr(user, "is_staff", False):
        return int(getattr(settings, "SESSION_IDLE_TIMEOUT_ADMIN", 8 * 60 * 60))
    return int(getattr(settings, "SESSION_IDLE_TIMEOUT", 3 * 24 * 60 * 60))


def duree_absolue() -> int:
    return int(getattr(settings, "SESSION_ABSOLUTE_TIMEOUT", 14 * 24 * 60 * 60))


@receiver(user_logged_in, dispatch_uid="heure_de_connexion")
def _a_la_connexion(sender, request, user, **kwargs):
    if request is not None and hasattr(request, "session"):
        maintenant = int(time.time())
        request.session[CLE_CONNEXION] = maintenant
        request.session[CLE] = maintenant


class SessionInactiveMiddleware:
    """Ferme une session inactive ou trop ancienne. Apres l'authentification."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            maintenant = int(time.time())
            session = request.session
            connecte = session.get(CLE_CONNEXION)
            derniere = session.get(CLE)
            de_fond = request.headers.get("X-Activite", "").strip().lower() == EN_TETE_FOND
            if connecte is not None and maintenant - int(connecte) > duree_absolue():
                # `logout` vide la session et remplace l'utilisateur par un
                # anonyme : la suite de la requete est traitee comme telle.
                logout(request)
            elif derniere is not None and maintenant - int(derniere) > delai_inactivite(user):
                logout(request)
            else:
                if connecte is None:
                    # Session ouverte avant cette regle : sa duree court
                    # a partir d'aujourd'hui.
                    session[CLE_CONNEXION] = maintenant
                if derniere is None or (
                    not de_fond and maintenant - int(derniere) > RAFRAICHISSEMENT
                ):
                    session[CLE] = maintenant
        return self.get_response(request)
