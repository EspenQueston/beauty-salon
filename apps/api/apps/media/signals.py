"""Le fichier suit la ligne.

---------------------------------------------------------------------------
Ce qui ne marchait pas
---------------------------------------------------------------------------

Supprimer un media effacait la ligne en base et laissait le fichier sur le
disque. Verifie : la ligne disparait, `file.path` existe toujours. Pour un
media public, cela veut dire qu'il reste servi a son adresse — une photo
« supprimee » de la galerie reste visible pour quiconque a garde le lien.

Cette table porte aussi les **preuves de versement** : la capture d'ecran
bancaire qu'une cliente envoie, avec son nom et parfois son solde. C'est la
piece la plus sensible de toute la reserve, et « supprimer » ne la
supprimait pas.

---------------------------------------------------------------------------
Pourquoi un signal, et pas `Model.delete()`
---------------------------------------------------------------------------

`delete()` n'est pas appele pour une suppression en masse : `queryset
.delete()` passe par le collecteur, qui emet les signaux mais ne touche pas
la methode du modele. Or c'est exactement ce que fait l'administration quand
on coche plusieurs lignes, et ce que font les suppressions en cascade.

Le signal, lui, part dans les trois cas.

---------------------------------------------------------------------------
Pourquoi il n'echoue jamais
---------------------------------------------------------------------------

Un fichier deja disparu — nettoyage manuel, restauration partielle, disque
remplace — ne doit pas empecher la suppression de la ligne. Sinon la base
garde une reference vers un fichier qui n'existe pas, et personne ne peut
plus s'en debarrasser. On journalise, et on laisse passer.
"""

import logging

from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import MediaAsset

logger = logging.getLogger(__name__)


@receiver(post_delete, sender=MediaAsset, dispatch_uid="media.supprimer_le_fichier")
def supprimer_le_fichier(sender, instance, **kwargs):
    """Efface du stockage le fichier porte par ce media."""
    fichier = getattr(instance, "file", None)
    if not fichier or not fichier.name:
        return

    try:
        fichier.storage.delete(fichier.name)
    except Exception:  # noqa: BLE001 - la ligne part quoi qu'il arrive
        logger.exception(
            "Fichier %s non supprime apres l'effacement du media %s.",
            fichier.name,
            instance.pk,
        )
