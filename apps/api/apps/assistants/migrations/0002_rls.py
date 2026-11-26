"""Isolation RLS des reglages d'assistants : chaque salon ne voit que les siens."""

from django.db import migrations

from apps.common.rls import enable_rls


class Migration(migrations.Migration):
    dependencies = [("assistants", "0001_initial")]

    operations = enable_rls("assistants_assistantreglages")
