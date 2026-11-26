"""Reauthentification recente, pour les gestes qui detournent de l'argent.

Une session volee — un poste reste ouvert au comptoir, un telephone perdu —
suffisait a remplacer le numero Mobile Money du salon par un autre : les
clientes envoyaient alors leurs acomptes ailleurs, sans que rien ne le dise
(audit du 16/10/2026, C-04).

Ces gestes exigent donc une preuve d'identite de moins de dix minutes : une
connexion, ou le mot de passe (ou un code de double authentification)
ressaisi a la demande. La preuve vit dans la session, cote serveur ; le
navigateur ne peut pas la fabriquer.
"""

from __future__ import annotations

import time

from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

CLE = "reauth_le"
DUREE = 10 * 60


def marquer(request) -> None:
    request.session[CLE] = int(time.time())


def recente(request) -> bool:
    session = getattr(request, "session", None)
    if session is None:
        return False
    try:
        return int(time.time()) - int(session.get(CLE, 0)) <= DUREE
    except (TypeError, ValueError):
        return False


@receiver(user_logged_in, dispatch_uid="reauth_a_la_connexion")
def _a_la_connexion(sender, request, user, **kwargs):
    # Se connecter, c'est s'etre identifie a l'instant.
    if request is not None and hasattr(request, "session"):
        marquer(request)
