"""Isolation Row-Level Security des options de prestation.

Sans cette migration, tests/test_rls.py echoue : il verifie que toute table
heritant de TenantOwnedModel porte bien une politique. La grille d'options
d'un salon - et donc ses supplements - ne regarde que lui.
"""

from django.db import migrations

from apps.common.rls import enable_rls


class Migration(migrations.Migration):
    dependencies = [("catalog", "0005_options_de_prestation")]

    operations = enable_rls("catalog_serviceoption")
