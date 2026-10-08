"""Un salon enregistre son texte : la traduction se met en file.

C'est ce qui couvre les salons a venir sans rien demander a personne. Le
declencheur n'est pas « quelqu'un a visite la page » mais « le texte a
change » : le travail se fait une fois, et non a chaque visite.

Le recepteur ne traduit rien lui-meme. Un `post_save` qui appellerait le reseau
tiendrait la transaction ouverte le temps d'un aller-retour, et ferait echouer
un enregistrement parfaitement valable a la premiere panne de l'API.
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from .registry import TRADUISIBLES

logger = logging.getLogger(__name__)

#: Les langues vers lesquelles on traduit. Le francais est la langue source.
CIBLES = ("en",)


def _mettre_en_file(instance) -> None:
    from .tasks import traduire_objet

    for langue in CIBLES:
        try:
            traduire_objet.delay(
                instance._meta.label_lower,
                str(instance.pk),
                str(instance.tenant_id),
                langue,
            )
        except Exception:  # noqa: BLE001 - sans courtier, l'enregistrement reste valable
            logger.warning(
                "traduction non mise en file pour %s (%s)",
                instance._meta.label_lower,
                instance.pk,
                exc_info=True,
            )


@receiver(post_save)
def au_changement(sender, instance, **kwargs) -> None:
    """Met en file la traduction d'un objet traduisible qu'on vient d'ecrire."""
    if sender._meta.label_lower not in TRADUISIBLES:
        return

    # `on_commit` : la tache ne part qu'une fois la transaction validee. Sans
    # cela, le travailleur pourrait lire la ligne avant qu'elle existe — ou
    # traduire une version qu'un rollback vient d'annuler.
    transaction.on_commit(lambda: _mettre_en_file(instance))
