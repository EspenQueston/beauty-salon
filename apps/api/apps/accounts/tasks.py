"""E-mails de compte, envoyes en arriere-plan.

---------------------------------------------------------------------------
Pourquoi en arriere-plan
---------------------------------------------------------------------------

Envoyes pendant la requete, ces e-mails ne partaient que pour les comptes
existants : la reponse mettait alors le temps d'un echange SMTP (une demi-
seconde a plusieurs secondes), et l'adresse inconnue repondait tout de
suite. Le chronometre disait ce que le texte de la reponse taisait. Les vues
deposent maintenant une tache **dans tous les cas** ; c'est ici qu'on
cherche le compte, hors de la requete.
"""

from __future__ import annotations

import logging

from celery import shared_task
from django.conf import settings

from . import securite

logger = logging.getLogger(__name__)


@shared_task(ignore_result=True)
def reinitialisation(email: str) -> None:
    """« Mot de passe oublie » de l'espace professionnel."""
    from .services import request_password_reset

    if not securite.envoi_autorise("reinitialisation", email):
        logger.info("Reinitialisation : envoi freine pour cette adresse.")
        return
    request_password_reset(email)


@shared_task(ignore_result=True)
def reinitialisation_cliente(email: str, tenant_id: str, langue: str = "fr") -> None:
    """« Mot de passe oublie » depuis un mini-site."""
    from apps.clients.services import demander_nouveau_mot_de_passe
    from apps.tenants.models import Tenant

    tenant = Tenant.objects.filter(pk=tenant_id).first()
    if tenant is None:
        return
    if not securite.envoi_autorise("reinitialisation", email):
        logger.info("Reinitialisation cliente : envoi freine pour cette adresse.")
        return
    demander_nouveau_mot_de_passe(email, tenant, langue=langue)


@shared_task(ignore_result=True)
def verification(user_id: str, base: str = "", langue: str = "fr") -> None:
    """Le lien de verification d'adresse, a l'adresse actuelle du compte."""
    from . import verification as verif
    from .models import User

    user = User.objects.filter(pk=user_id, is_active=True).first()
    if user is None or user.email_verified_at is not None:
        return
    verif.envoyer(user, base=base, langue=langue)


def base_cliente(user, langue: str = "fr") -> str:
    """Le mini-site ou renvoyer une cliente : son salon favori, s'il en a un."""
    from apps.notifications.tasks import _salon_base_url

    profil = getattr(user, "client_profile", None)
    salon = getattr(profil, "preferred_salon", None) if profil else None
    if salon is None:
        return ""
    return f"{_salon_base_url(salon)}/{langue if langue in ('fr', 'en') else 'fr'}/compte"


@shared_task(ignore_result=True)
def alerte_securite(
    email: str, genre: str, *, nom: str = "", nouvelle_adresse: str = ""
) -> None:
    """Prevenir le titulaire d'un changement sensible sur son compte.

    Jamais le mot de passe lui-meme, jamais un lien de connexion : seulement
    ce qui a change, quand, et quoi faire si ce n'etait pas lui.
    """
    from apps.notifications.email import send_email

    contenus = {
        "mot_de_passe": (
            "Votre mot de passe Beauty Salon a été modifié",
            "Le mot de passe de votre compte vient d'être modifié. Toutes les autres "
            "sessions ouvertes ont été fermées.",
        ),
        "mfa_active": (
            "Double authentification activée sur votre compte Beauty Salon",
            "La double authentification vient d'être activée : un code de votre application "
            "sera demandé à chaque connexion. Gardez vos codes de secours en lieu sûr.",
        ),
        "mfa_desactive": (
            "Double authentification désactivée sur votre compte Beauty Salon",
            "La double authentification vient d'être désactivée : votre mot de passe suffit "
            "de nouveau pour vous connecter.",
        ),
        "adresse": (
            "L'adresse e-mail de votre compte Beauty Salon a changé",
            f"L'adresse de connexion de votre compte a été remplacée par "
            f"{nouvelle_adresse}. Ce message est envoyé à l'ancienne adresse.",
        ),
    }
    sujet, texte = contenus[genre]
    send_email(
        subject=sujet,
        template="security_alert",
        context={
            "nom": nom,
            "intro": texte,
            "aide": (
                "Ce n'était pas vous ? Choisissez tout de suite un nouveau mot de passe "
                "depuis « Mot de passe oublié », puis écrivez-nous en répondant à ce message."
            ),
            "reset_url": f"{settings.APP_BASE_URL}/mot-de-passe-oublie",
        },
        to=[email],
    )
