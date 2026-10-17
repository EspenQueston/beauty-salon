"""Isolation des notifications de salon.

Seule `notifications_notification` recoit une politique : c'est la seule des
trois tables qui appartienne a un salon.

`notifications_platformnotification` parle des salons a la plateforme, et
son unique lecteur travaille hors contexte tenant — une politique la rendrait
invisible a la seule personne censee la lire.

`notifications_pushsubscription` est rattachee a une personne, pas a un
salon : la meme gerante peut tenir deux salons depuis le meme telephone.

Les deux sont protegees applicativement, comme les autres tables d'identite
(voir apps/common/rls.py).
"""

from django.db import migrations

from apps.common.rls import enable_rls


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0001_initial"),
    ]

    operations = enable_rls("notifications_notification")
