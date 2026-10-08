"""Journal des evenements de securite des comptes.

Chaque geste qui touche a l'acces d'un compte laisse une ligne dans
`AuditLog` : connexions (reussies, echouees, bloquees), double
authentification, mots de passe, adresse e-mail. L'equipe plateforme les
consulte dans l'administration (filtre « Securite des comptes »), et un
blocage de compte la previent dans sa cloche.

Ce qui n'y est jamais : un mot de passe, un code, un jeton. Seulement qui,
quand, d'ou (IP et navigateur), et quoi.

Le journal ne doit jamais empecher une connexion : une ecriture qui echoue
part dans les journaux du serveur, la requete continue.
"""

from __future__ import annotations

import logging

from django.db import transaction
from rest_framework.throttling import BaseThrottle

logger = logging.getLogger(__name__)

# Les actions de ce journal, pour le filtre de l'administration.
ACTIONS_SECURITE = (
    "auth.login_succeeded",
    "auth.login_failed",
    "auth.account_locked",
    "auth.mfa_failed",
    "auth.mfa_enabled",
    "auth.mfa_disabled",
    "auth.recovery_codes_regenerated",
    "auth.password_reset",
    "auth.password_changed",
    "auth.email_changed",
    "auth.email_verified",
    "auth.password_breached",
)


def _origine(request) -> dict:
    if request is None:
        return {}
    return {
        "ip": BaseThrottle().get_ident(request) or "",
        "navigateur": (request.META.get("HTTP_USER_AGENT") or "")[:160],
    }


def consigner(action: str, *, request=None, user=None, email: str = "", **extra) -> None:
    """Ecrit l'evenement. `action` : le nom d'un membre de `AuditLog.Action`."""
    from apps.audit.models import AuditLog

    acteur = user if getattr(user, "pk", None) else None
    try:
        with transaction.atomic():
            AuditLog.objects.create(
                actor_user=acteur,
                action=getattr(AuditLog.Action, action),
                resource_type="compte",
                resource_id=str(acteur.pk) if acteur else "",
                metadata={
                    "email": (email or getattr(acteur, "email", ""))[:254],
                    **_origine(request),
                    **extra,
                },
            )
    except Exception:  # noqa: BLE001 - le journal ne bloque jamais l'acces
        logger.exception("Evenement de securite non consigne (%s).", action)


def alerter_plateforme(titre: str, corps: str = "") -> None:
    """Une alerte dans la cloche de l'equipe plateforme (genre « Incident »)."""
    from apps.notifications.models import Genre
    from apps.notifications.service import prevenir_plateforme

    try:
        with transaction.atomic():
            prevenir_plateforme(genre=Genre.INCIDENT, titre=titre[:120], corps=corps[:280])
    except Exception:  # noqa: BLE001
        logger.exception("Alerte de securite non deposee.")
