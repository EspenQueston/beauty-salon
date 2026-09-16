"""Active l isolation Row-Level Security sur les tables de ce module."""

from django.db import migrations

from apps.common.rls import enable_rls


class Migration(migrations.Migration):
    dependencies = [("salons", "0001_initial")]

    operations = enable_rls( "salons_salonprofile",)
