"""Isolation RLS de la liste d'attente.

Elle porte des coordonnees de clientes : c'est exactement le genre de table
dont une fuite inter-salons serait grave.
"""

from django.db import migrations

from apps.common.rls import enable_rls


class Migration(migrations.Migration):
    dependencies = [("scheduling", "0010_liste_attente")]

    operations = enable_rls("scheduling_waitlistentry")
