"""Verification des adresses e-mail.

---------------------------------------------------------------------------
Le jeton
---------------------------------------------------------------------------

Signe (HMAC de la `SECRET_KEY`), horodate, et lie a l'etat du compte :

  - il porte l'identifiant du compte et une **empreinte** de l'adresse
    (jamais l'adresse en clair : le lien passe par des URL, des journaux de
    proxy, l'historique du navigateur) ;
  - il expire apres `EMAIL_VERIFICATION_TIMEOUT` secondes ;
  - il ne vaut qu'**une fois** : l'empreinte inclut l'etat « verifie ou
    non » ; une fois l'adresse verifiee, le meme lien ne correspond plus ;
  - il meurt avec l'adresse : changer d'e-mail invalide les liens envoyes
    a l'ancienne.

Rien n'est stocke en base : il n'y a pas de table de jetons a fuiter.

---------------------------------------------------------------------------
Ce que la verification ouvre
---------------------------------------------------------------------------

Decide avec le produit (2026-10-02) : un proprietaire de salon non verifie
peut se connecter et preparer son salon, mais ne peut ni declarer un
paiement d'abonnement, ni voir son mini-site publie. Une cliente non
verifiee garde l'usage de son espace, avec un rappel. Les comptes anterieurs
a la verification sont consideres comme verifies (migration 0006).
"""

from __future__ import annotations

import hashlib
import hmac
import logging

from django.conf import settings
from django.core import signing
from django.utils import timezone

logger = logging.getLogger(__name__)

SALT = "beauty-salon.verification-email"


def _duree() -> int:
    return int(getattr(settings, "EMAIL_VERIFICATION_TIMEOUT", 3 * 24 * 60 * 60))


def _empreinte(user) -> str:
    etat = f"{user.pk}|{user.email.lower()}|{'oui' if user.email_verified_at else 'non'}"
    return hmac.new(settings.SECRET_KEY.encode(), etat.encode(), hashlib.sha256).hexdigest()[:24]


def jeton(user) -> str:
    return signing.dumps({"u": str(user.pk), "h": _empreinte(user)}, salt=SALT, compress=True)


class JetonInvalide(Exception):
    """Lien expire, deja utilise, falsifie, ou pour une autre adresse."""


def verifier(valeur: str):
    """Marque l'adresse comme verifiee et renvoie le compte."""
    from .models import User

    try:
        contenu = signing.loads(valeur or "", salt=SALT, max_age=_duree())
    except signing.SignatureExpired as exc:
        raise JetonInvalide("Ce lien a expiré. Demandez-en un nouveau.") from exc
    except signing.BadSignature as exc:
        raise JetonInvalide("Ce lien n'est pas valide.") from exc

    user = User.objects.filter(pk=contenu.get("u"), is_active=True).first()
    if user is None:
        raise JetonInvalide("Ce lien n'est pas valide.")
    if user.email_verified_at is not None:
        # Deja verifiee (double clic, second onglet) : rien a refaire, et
        # rien a reprocher. Le jeton, lui, ne correspond plus a rien.
        return user
    if not hmac.compare_digest(contenu.get("h", ""), _empreinte(user)):
        raise JetonInvalide("Ce lien ne correspond plus à l'adresse de ce compte.")

    user.email_verified_at = timezone.now()
    user.save(update_fields=["email_verified_at", "updated_at"])
    return user


def lien(user, base: str = "") -> str:
    """L'adresse du lien. `base` : un mini-site (cliente), sinon l'espace pro."""
    if base:
        return f"{base}/verifier-email?token={jeton(user)}"
    return f"{settings.APP_BASE_URL}/verifier-email?token={jeton(user)}"


def envoyer(user, *, base: str = "", langue: str = "fr") -> None:
    """Envoie le lien a l'adresse du compte. A appeler hors de la requete (tache)."""
    from apps.notifications.email import send_email

    if user.email_verified_at is not None:
        return
    heures = _duree() // 3600
    anglais = langue == "en"
    send_email(
        subject=(
            "Confirm your email address — Beauty Salon"
            if anglais
            else "Confirmez votre adresse e-mail — Beauty Salon"
        ),
        template="email_verification",
        context={
            "anglais": anglais,
            "nom": user.display_name,
            "verify_url": lien(user, base),
            "heures": heures,
        },
        to=[user.email],
    )
