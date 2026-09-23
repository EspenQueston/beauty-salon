"""La remise d'une notification a un appareil.

---------------------------------------------------------------------------
Ce qui se passe reellement
---------------------------------------------------------------------------

On ne joint jamais le telephone directement. Le navigateur nous a donne
l'adresse d'une boite aux lettres tenue par son propre editeur — Google pour
Chrome, Mozilla pour Firefox, Apple pour Safari — et c'est la qu'on depose.
Le message est chiffre avec les cles que ce navigateur nous a confiees :
l'editeur transporte, il ne lit pas.

Consequence pratique : aucun compte a ouvrir, aucun quota facture, et rien a
signer avec qui que ce soit. Mais aussi aucune garantie de delai, et aucun
accuse de reception. Un push est un rappel, jamais une preuve.

---------------------------------------------------------------------------
Ce qu'on fait des echecs
---------------------------------------------------------------------------

Une boite disparait quand la personne desinstalle l'application, vide les
donnees du site ou change de telephone. Le service repond alors 404 ou 410,
et la seule bonne reaction est de supprimer la ligne : la reessayer
eternellement remplirait les journaux d'un echec qui ne cessera jamais.

Le reste — 429, 500, un reseau coupe — est passager. On compte l'echec sans
rien jeter : c'est la tache Celery qui decidera de reessayer.
"""

from __future__ import annotations

import json
import logging

from django.conf import settings
from pywebpush import WebPushException, webpush

logger = logging.getLogger(__name__)

# Duree de conservation chez le service de push quand l'appareil est hors
# ligne. Douze heures : au-dela, « une cliente a demande un rendez-vous » est
# une nouvelle perimee, et la lire le surlendemain fait plus de mal que de
# bien. La ligne en base, elle, reste.
TTL = 12 * 3600

# Codes qui disent « cette boite n'existe plus ». Tout le reste est traite
# comme passager.
DISPARUS = frozenset({404, 410})


class NonConfigure(RuntimeError):
    """Les cles VAPID manquent : aucun envoi n'est possible."""


def configure() -> bool:
    """Le serveur peut-il pousser quoi que ce soit ?

    Verifie ailleurs avant de proposer l'abonnement : inviter quelqu'un a
    autoriser les notifications sur une installation qui ne peut pas en
    envoyer serait lui faire accorder une permission pour rien.
    """
    return bool(settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY)


def cle_publique() -> str:
    """La cle que le navigateur doit connaitre pour s'abonner.

    Servie par l'API plutot que figee dans le frontend : recopiee la-bas,
    elle divergerait le jour ou la paire change, et les abonnements crees
    apres ce jour-la ne recevraient plus rien — sans la moindre erreur
    visible.
    """
    if not configure():
        raise NonConfigure("VAPID_PUBLIC_KEY et VAPID_PRIVATE_KEY sont requis.")
    return settings.VAPID_PUBLIC_KEY


def envoyer(abonnement, charge: dict) -> bool:
    """Depose une notification pour un appareil.

    Rend True si le service l'a acceptee. Rend False si l'appareil a disparu
    — l'appelant doit alors supprimer l'abonnement. Toute autre erreur est
    relevee : elle est passagere, et c'est a la tache de decider.
    """
    if not configure():
        raise NonConfigure("VAPID_PUBLIC_KEY et VAPID_PRIVATE_KEY sont requis.")

    try:
        webpush(
            subscription_info={
                "endpoint": abonnement.endpoint,
                "keys": {
                    "p256dh": abonnement.cle_p256dh,
                    "auth": abonnement.cle_auth,
                },
            },
            data=json.dumps(charge, ensure_ascii=False),
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            # `aud` est deduit de l'endpoint par pywebpush ; `sub` est le seul
            # element que la norme nous demande de fournir.
            vapid_claims={"sub": settings.VAPID_SUBJECT},
            ttl=TTL,
        )
        return True

    except WebPushException as erreur:
        code = getattr(erreur.response, "status_code", None)

        if code in DISPARUS:
            logger.info(
                "Abonnement push %s abandonne par le service (%s).",
                abonnement.pk,
                code,
            )
            return False

        if code in (400, 401, 403):
            # Ce n'est pas l'appareil qui est en cause, c'est notre
            # configuration : cles depareillees, ou `sub` refuse. Le dire
            # fort, sinon on cherchera du cote du telephone pendant des
            # heures.
            logger.error(
                "Push refuse (%s) : verifiez VAPID_PRIVATE_KEY, VAPID_PUBLIC_KEY "
                "et VAPID_SUBJECT. Detail : %s",
                code,
                erreur,
            )

        raise
