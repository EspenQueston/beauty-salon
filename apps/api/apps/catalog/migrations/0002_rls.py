"""Active l isolation Row-Level Security sur les tables de ce module."""

from django.db import migrations

from apps.common.rls import enable_rls


class Migration(migrations.Migration):
    dependencies = [("catalog", "0001_initial")]

    operations = enable_rls( "catalog_servicecategory", "catalog_service",)
