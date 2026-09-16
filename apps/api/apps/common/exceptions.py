"""Erreurs API au format unique.

Chaque reponse d'erreur porte un `code` machine stable, que le frontend
utilise pour afficher un message adapte sans parser du texte francais.
"""

from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.views import exception_handler as drf_exception_handler


class Conflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Cette opération entre en conflit avec l'état actuel."
    default_code = "conflict"

    def __init__(self, detail=None, code=None, extra=None):
        super().__init__(detail, code)
        # Charge utile exploitable par le frontend : sur un creneau perdu,
        # proposer des alternatives vaut mieux qu'un simple refus.
        self.extra = extra or {}


class SlotUnavailable(Conflict):
    """Le creneau vient d'etre pris, ou n'a jamais ete disponible."""

    default_detail = "Ce créneau n'est plus disponible."
    default_code = "slot_unavailable"


def api_exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is None:
        return None

    code = getattr(exc, "default_code", None)
    detail = response.data

    if isinstance(detail, dict) and "detail" in detail:
        response.data = {"detail": str(detail["detail"]), "code": code or "error"}
    else:
        # Erreurs de validation : on conserve la structure champ -> messages.
        response.data = {"detail": detail, "code": code or "validation_error"}

    # Certaines exceptions transportent des informations exploitables par le
    # frontend (creneaux alternatifs apres un conflit, par exemple).
    extra = getattr(exc, "extra", None)
    if extra:
        response.data["extra"] = extra

    return response
