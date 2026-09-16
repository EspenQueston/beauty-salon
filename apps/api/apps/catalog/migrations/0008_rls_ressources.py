"""Isolation RLS des ressources et de leurs liaisons."""

from django.db import migrations

from apps.common.rls import enable_rls


class Migration(migrations.Migration):
    dependencies = [("catalog", "0007_ressources")]

    operations = [
        *enable_rls("catalog_resource"),
        *enable_rls("catalog_serviceresource"),
    ]
