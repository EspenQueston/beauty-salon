"""Isolation RLS de la table des traductions.

Une traduction porte le texte d un salon : elle doit obeir a la meme regle
que la ligne dont elle derive. Sans politique ici, le contenu traduit d un
salon serait lisible depuis le contexte d un autre — et la suite de tests le
refuse, ce qui est precisement le role de test_rls.py.
"""

from django.db import migrations

from apps.common.rls import enable_rls


class Migration(migrations.Migration):
    dependencies = [("translations", "0001_initial")]

    operations = [*enable_rls("translations_translation")]
