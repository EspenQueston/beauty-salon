"""Isolation RLS de l'historique des conversations : chaque salon ne lit que les siennes."""

from django.db import migrations

from apps.common.rls import enable_rls


class Migration(migrations.Migration):
    dependencies = [("assistants", "0003_assistantreglages_n8n_cle_and_more")]

    operations = [
        *enable_rls("assistants_conversationassistant"),
        *enable_rls("assistants_messageassistant"),
    ]
