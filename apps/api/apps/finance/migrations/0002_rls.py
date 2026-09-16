"""Isolation RLS des mouvements financiers.

C'est la table la plus sensible du produit apres les fiches clientes : elle
porte le chiffre d'affaires, les charges et la marge d'un salon.
"""

from django.db import migrations

from apps.common.rls import enable_rls


class Migration(migrations.Migration):
    dependencies = [("finance", "0001_mouvements")]

    operations = enable_rls("finance_transaction")
