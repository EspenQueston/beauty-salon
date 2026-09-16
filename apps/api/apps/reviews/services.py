"""Jetons d'invitation a laisser un avis.

Une cliente n'a pas de compte. Pour prouver qu'elle a bien eu le rendez-vous
qu'elle s'apprete a noter, on lui envoie un lien porteur d'un jeton signe.

Pourquoi une signature plutot qu'un identifiant en base :

  - rien de plus a stocker, et rien a nettoyer quand les jetons expirent ;
  - l'identifiant du rendez-vous n'est pas devinable a partir du lien d'une
    autre cliente, parce qu'il est signe avec la cle du serveur ;
  - la peremption est portee par le jeton lui-meme.

Le jeton est *une preuve de reception d'e-mail*, pas une authentification :
il ne donne acces a rien d'autre qu'a la notation de ce rendez-vous precis.
"""

from datetime import timedelta

from django.core import signing
from django.utils import timezone

SALT = "beauty-salon.review"

# Fenetre pour laisser un avis. Au-dela, le souvenir de la prestation est
# trop flou pour que la note dise encore quelque chose d'utile.
TOKEN_MAX_AGE = timedelta(days=30)


class InvalidReviewToken(Exception):
    """Jeton absent, alteré ou périmé."""


def make_token(booking_id) -> str:
    return signing.dumps(str(booking_id), salt=SALT)


def read_token(token: str) -> str:
    """Renvoie l'identifiant du rendez-vous, ou leve InvalidReviewToken."""
    try:
        return signing.loads(
            token, salt=SALT, max_age=int(TOKEN_MAX_AGE.total_seconds())
        )
    except signing.SignatureExpired as exc:
        raise InvalidReviewToken(
            "Ce lien a expiré. Les avis se laissent dans les 30 jours."
        ) from exc
    except signing.BadSignature as exc:
        raise InvalidReviewToken("Ce lien n'est pas valide.") from exc


def review_url(booking, base_url: str) -> str:
    """Lien complet, a placer dans l'e-mail de demande d'avis."""
    return f"{base_url}/avis?token={make_token(booking.id)}"


def is_eligible(booking) -> tuple[bool, str]:
    """Le rendez-vous peut-il encore etre note ?

    Renvoie (True, "") ou (False, raison lisible). La raison est affichee
    telle quelle : une cliente qui clique sur un vieux lien doit comprendre
    pourquoi elle ne peut pas ecrire, pas voir une page vide.
    """
    from apps.scheduling.models import Booking

    if booking.status != Booking.Status.COMPLETED:
        return False, "Cet avis ne peut être laissé qu'après la prestation."
    if hasattr(booking, "review"):
        return False, "Un avis a déjà été laissé pour ce rendez-vous."
    if booking.starts_at < timezone.now() - TOKEN_MAX_AGE:
        return False, "Ce rendez-vous est trop ancien pour être noté."
    return True, ""
