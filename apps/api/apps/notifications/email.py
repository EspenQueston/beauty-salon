"""Un seul chemin de sortie pour tout ce que le produit envoie.

---------------------------------------------------------------------------
Pourquoi ce module existe
---------------------------------------------------------------------------

Il y avait deux fonctions d'envoi : celle des notifications de rendez-vous,
qui joignait la version HTML, et celle des comptes - bienvenue, invitation,
mot de passe - qui ne la joignait pas. Personne ne l'avait decide : la
seconde avait ete ecrite en premier et n'avait jamais suivi.

Le resultat etait invisible et pourtant bien reel : trois messages partaient
en texte brut pendant que les neuf autres etaient soignes, et le premier
e-mail qu'un salon recevait de nous - la bienvenue - etait justement l'un
des trois.

Deux fonctions d'envoi divergent toujours. Il n'y en a plus qu'une.
"""

import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template import TemplateDoesNotExist
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


def send_email(subject: str, template: str, context: dict, to: list[str]) -> bool:
    """Envoie un message en deux parties : texte, puis HTML.

    -----------------------------------------------------------------------
    Pourquoi les deux, et le texte en premier
    -----------------------------------------------------------------------

    Le corps texte n'est pas un vestige. Il sert de repli quand le client
    n'affiche pas le HTML, il est ce que lisent les lecteurs d'ecran quand
    on le leur demande, et surtout il compte pour la delivrabilite : un
    message qui n'a qu'une partie HTML est un signal de courrier
    indesirable pour la plupart des filtres.

    Le HTML est optionnel a dessein. Un gabarit manquant ne fait pas echouer
    l'envoi - le message part en texte seul, ce qui vaut infiniment mieux
    qu'une notification perdue parce qu'un fichier n'existait pas encore.

    Renvoie False quand il n'y avait personne a qui ecrire : une cliente
    peut reserver par telephone, sans adresse, et ce n'est pas une erreur.
    """
    recipients = [address for address in to if address]
    if not recipients:
        return False

    context = {**context, "subject": subject}

    text = render_to_string(f"emails/{template}.txt", context)
    message = EmailMultiAlternatives(
        subject=subject,
        body=text,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=recipients,
    )

    try:
        message.attach_alternative(
            render_to_string(f"emails/{template}.html", context), "text/html"
        )
    except TemplateDoesNotExist:
        logger.info("Pas de version HTML pour %s : envoi en texte seul.", template)

    message.send(fail_silently=False)
    return True
