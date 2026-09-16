"""Isolation Row-Level Security de la table des zones de deplacement.

Sans cette migration, tests/test_rls.py echoue : il verifie que toute table
heritant de TenantOwnedModel porte bien une politique. La grille tarifaire
d'un salon ne regarde que lui.
"""

from django.db import migrations

from apps.common.rls import enable_rls


class Migration(migrations.Migration):
    dependencies = [("salons", "0007_deplacement_a_domicile")]

    operations = enable_rls("salons_travelzone")
