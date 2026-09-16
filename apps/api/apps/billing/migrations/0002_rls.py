"""Active l isolation Row-Level Security sur les tables de facturation.

Un salon ne doit voir que son propre abonnement et ses propres factures.
`Plan` n'en porte pas : c'est un catalogue commun, sans donnee de salon.
"""

from django.db import migrations

from apps.common.rls import enable_rls


class Migration(migrations.Migration):
    dependencies = [("billing", "0001_initial")]

    operations = enable_rls("billing_subscription", "billing_invoice")
