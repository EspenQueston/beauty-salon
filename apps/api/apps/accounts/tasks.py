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

from . import securite

logger = logging.getLogger(__name__)


@shared_task(ignore_result=True)
def reinitialisation(email: str, langue: str = "") -> None:
    """« Mot de passe oublie » de l'espace professionnel, dans la langue de
    la page ou il a ete demande."""
    from .services import request_password_reset

    if not securite.envoi_autorise("reinitialisation", email):
        logger.info("Reinitialisation : envoi freine pour cette adresse.")
        return
    request_password_reset(email, langue or None)


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
def verification(user_id: str, base: str = "", langue: str = "") -> None:
    """Le lien de verification d'adresse, a l'adresse actuelle du compte.

    Sans langue precisee — a l'inscription, apres un changement d'adresse —
    c'est celle retenue sur le compte.
    """
    from apps.translations.langue import du_compte

    from . import verification as verif
    from .models import User

    user = User.objects.filter(pk=user_id, is_active=True).first()
    if user is None or user.email_verified_at is not None:
        return
    verif.envoyer(user, base=base, langue=langue or du_compte(user))


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
    email: str, genre: str, *, nom: str = "", nouvelle_adresse: str = "", langue: str = "fr"
) -> None:
    """Prevenir le titulaire d'un changement sensible sur son compte.

    Jamais le mot de passe lui-meme, jamais un lien de connexion : seulement
    ce qui a change, quand, et quoi faire si ce n'etait pas lui.

    `langue` : celle retenue sur le compte, passee par l'appelant — pour un
    changement d'adresse, le message part a l'ancienne, qu'aucun compte ne
    porte plus.
    """
    from apps.notifications.email import send_email
    from apps.notifications.textes import textes
    from apps.translations.langue import adresse_app, normaliser

    langue = normaliser(langue)
    t = textes(langue)
    if genre not in ("mot_de_passe", "mfa_active", "mfa_desactive", "adresse"):
        raise KeyError(genre)
    send_email(
        subject=t[f"secu_{genre}_objet"],
        template="security_alert",
        context={
            "t": t,
            "langue": langue,
            "nom": nom,
            "salutation": t.dire("bonjour", prenom=nom) if nom else t["pro_bonjour"],
            "intro": t.dire(f"secu_{genre}", adresse=nouvelle_adresse),
            "aide": t["secu_aide"],
            "reset_url": adresse_app("/mot-de-passe-oublie", langue),
        },
        to=[email],
    )


@shared_task(ignore_result=True)
def alerte_encaissement(
    tenant_id: str, operation: str, moyen: str, ancien: str, nouveau: str, auteur: str
) -> None:
    """Prevenir les proprietaires qu'un moyen d'encaissement a change (C-04).

    A chaque proprietaire active, dans la langue de son compte — y compris
    quand c'est elle qui a fait le changement : un acces vole agit sous son
    nom, et c'est sa boite qui le revelera.
    """
    from apps.notifications.email import send_email
    from apps.notifications.textes import textes
    from apps.translations.langue import adresse_app, du_compte

    from .models import Membership

    proprietaires = (
        Membership.objects.using("admin")
        .filter(tenant_id=tenant_id, role=Membership.Role.OWNER, status=Membership.Status.ACTIVE)
        .select_related("user", "tenant")
    )
    for m in proprietaires:
        langue = du_compte(m.user)
        t = textes(langue)
        valeurs = {
            "salon": m.tenant.name,
            "moyen": moyen,
            "auteur": auteur,
            "ancien": ancien or "—",
            "nouveau": nouveau or "—",
        }
        send_email(
            subject=t.dire("secu_encaissement_objet", **valeurs),
            template="security_alert",
            context={
                "t": t,
                "langue": langue,
                "nom": m.user.display_name,
                "salutation": t.dire("bonjour", prenom=m.user.display_name)
                if m.user.display_name
                else t["pro_bonjour"],
                "intro": t.dire(f"secu_encaissement_{operation}", **valeurs),
                "aide": t["secu_aide"],
                "reset_url": adresse_app("/mot-de-passe-oublie", langue),
            },
            to=[m.user.email],
        )
