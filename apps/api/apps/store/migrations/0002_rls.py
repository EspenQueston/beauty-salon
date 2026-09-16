"""Isolation RLS de la boutique.

Le catalogue d'un salon, ses prix et son stock ne regardent que lui.
"""

from django.db import migrations

from apps.common.rls import enable_rls


class Migration(migrations.Migration):
    dependencies = [("store", "0001_boutique")]

    operations = [
        *enable_rls("store_product"),
        *enable_rls("store_requirement"),
        *enable_rls("store_requirementproduct"),
    ]
