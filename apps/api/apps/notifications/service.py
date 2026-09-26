"""Prevenir quelqu'un : le seul point d'entree.

---------------------------------------------------------------------------
Une porte, pas dix
---------------------------------------------------------------------------

Le reste du code appelle `prevenir_salon()` ou `prevenir_plateforme()` et
n'a rien d'autre a savoir : ni qui sont les destinataires, ni si le push est
configure, ni ce qu'il faut faire quand Redis est eteint. Toute cette
plomberie vit ici, et elle ne vit qu'ici.

C'est ce qui permet de changer la regle de destination — aujourd'hui « la
proprietaire et la gerante » — en modifiant une seule constante, au lieu de
la rechercher dans huit taches Celery.

---------------------------------------------------------------------------
Prevenir ne doit jamais casser ce qui declenche
---------------------------------------------------------------------------

Ces fonctions sont appelees depuis la creation d'une reservation, le depot
d'un acompte, la publication d'un avis. Si l'une d'elles levait une
exception parce que le courtier Celery est arrete, elle ferait echouer la
reservation elle-meme — une cliente perdrait son creneau parce qu'une
notification n'a pas pu partir.

Tout ce qui peut echouer est donc rattrape et journalise. La ligne en base,
elle, est ecrite dans la transaction appelante : si celle-ci est annulee, la
notification disparait avec elle, ce qui est exactement ce qu'on veut.
"""

from __future__ import annotations

import logging

from django.db import transaction

from apps.accounts.models import Membership, User
from apps.common.db import tenant_context

from . import habillage
from .models import Notification, PlatformNotification, PushSubscription

logger = logging.getLogger(__name__)

# Qui est prevenu dans un salon.
#
# La proprietaire et la gerante, et personne d'autre. Ce sont les deux roles
# qui peuvent *agir* sur ce qu'annoncent ces messages — accepter une demande,
# verifier un acompte, rembourser. Prevenir une prestataire d'un acompte
# qu'elle ne peut pas valider la conduirait a couper ses notifications, et
# elle manquerait ensuite celles qui la concernent.
ROLES_PREVENUS = (Membership.Role.OWNER, Membership.Role.MANAGER)


def prevenir_salon(
    tenant_id,
    *,
    genre: str,
    titre: str,
    corps: str = "",
    lien: str = "",
    image: str = "",
) -> int:
    """Depose une notification pour l'encadrement d'un salon.

    Rend le nombre de personnes prevenues. Zero n'est pas une erreur : un
    salon dont la gerante a ete desactivee n'a personne a prevenir, et ce
    n'est pas a cette fonction de s'en emouvoir.

    `image` est la photo propre a l'evenement — celle de la prestation
    reservee. Elle ne sert qu'au push : la cloche n'affiche pas d'image.
    """
    with tenant_context(tenant_id):
        comptes = list(
            Membership.objects.filter(
                tenant_id=tenant_id,
                role__in=ROLES_PREVENUS,
                status=Membership.Status.ACTIVE,
            )
            .values_list("user_id", flat=True)
            .distinct()
        )

        if not comptes:
            return 0

        Notification.objects.bulk_create(
            [
                Notification(
                    tenant_id=tenant_id,
                    recipient_id=compte,
                    genre=genre,
                    titre=titre,
                    corps=corps,
                    lien=lien,
                )
                for compte in comptes
            ]
        )

        salon = _apparence(tenant_id)

    _pousser_apres_commit(
        comptes,
        PushSubscription.Portee.SALON,
        habillage.habiller(
            {"genre": genre, "titre": titre, "corps": corps, "lien": lien},
            genre=genre,
            lien=lien,
            image=image,
            salon=salon,
        ),
    )
    return len(comptes)


def prevenir_plateforme(
    *,
    genre: str,
    titre: str,
    corps: str = "",
    lien: str = "",
    tenant_id=None,
) -> int:
    """Depose une notification pour l'equipe de la plateforme.

    Hors contexte tenant, volontairement : cette table n'appartient a aucun
    salon, et l'appelant est souvent une tache qui parcourt tous les salons.
    """
    comptes = list(
        User.objects.filter(is_platform_admin=True, is_active=True)
        .values_list("id", flat=True)
        .distinct()
    )

    if not comptes:
        return 0

    PlatformNotification.objects.bulk_create(
        [
            PlatformNotification(
                recipient_id=compte,
                tenant_id=tenant_id,
                genre=genre,
                titre=titre,
                corps=corps,
                lien=lien,
            )
            for compte in comptes
        ]
    )

    # Le salon dont il est question, s'il y en a un : son logo et ses
    # couleurs disent d'un coup d'oeil de qui l'on parle. Son profil est
    # protege par RLS, d'ou le contexte a poser.
    salon = _apparence(tenant_id, poser_le_contexte=True) if tenant_id else None

    _pousser_apres_commit(
        comptes,
        PushSubscription.Portee.PLATEFORME,
        habillage.habiller(
            {"genre": genre, "titre": titre, "corps": corps, "lien": lien},
            genre=genre,
            lien=lien,
            salon=salon,
        ),
    )
    return len(comptes)


def _apparence(tenant_id, *, poser_le_contexte: bool = False) -> dict | None:
    """L'apparence d'un salon, sans jamais faire echouer la notification.

    Le logo et la couleur habillent le push ; ils ne sont pas le message. Une
    lecture qui echoue ici laisse partir une notification plus sobre plutot
    que pas de notification du tout.

    Le point de sauvegarde n'est pas une precaution de style. L'appelant est
    souvent dans une transaction — celle qui enregistre la reservation — et
    sous PostgreSQL une requete en echec y bloque toutes les suivantes :
    rattraper l'exception sans lui ferait echouer la reservation plus loin.

    Le contexte du salon est pose ici, a l'interieur du filet, et non par
    l'appelant : `tenant_context` refuse d'imbriquer deux salons differents,
    et ce refus doit donner une notification sans logo, pas pas de
    notification du tout.
    """
    try:
        with transaction.atomic():
            if poser_le_contexte:
                with tenant_context(tenant_id):
                    return habillage.apparence(tenant_id)
            return habillage.apparence(tenant_id)
    except Exception:
        logger.exception("Apparence du salon %s illisible pour le push.", tenant_id)
        return None


def _pousser_apres_commit(comptes: list, portee: str, charge: dict) -> None:
    """Met l'envoi en file, une fois la transaction validee.

    `on_commit` et non un appel direct : une tache lancee avant la
    validation peut etre prise par un worker qui lira une base ou la
    notification n'existe pas encore — et, si la transaction est finalement
    annulee, elle aura pousse l'annonce d'un evenement qui n'a pas eu lieu.
    """

    def envoyer():
        # Importe ici et non en tete de module : tasks.py importe ce
        # fichier pour ses propres besoins, et l'import croise au chargement
        # ferait echouer le demarrage de Django.
        from .tasks import pousser_notification

        try:
            pousser_notification.delay(
                [str(compte) for compte in comptes], portee, charge
            )
        except Exception:
            # Courtier injoignable, file saturee : la notification reste
            # lisible dans la cloche, seul le rappel sur l'appareil est
            # perdu. Ne jamais faire remonter : l'appelant est en train de
            # creer une reservation.
            logger.exception(
                "Mise en file du push impossible (%s destinataires).", len(comptes)
            )

    transaction.on_commit(envoyer)
