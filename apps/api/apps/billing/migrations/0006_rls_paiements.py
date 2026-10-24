"""Isolation RLS des demandes de paiement et de l'historique d'abonnement.

Un salon ne doit voir que ses propres paiements et son propre historique.
`PlanPrice` et `PlatformPaymentMethod` n'en portent pas : ce sont des
catalogues de la plateforme, communs a tous les salons.
"""

from django.db import migrations

from apps.common.rls import enable_rls


class Migration(migrations.Migration):
    dependencies = [("billing", "0005_abonnements_payants")]

    operations = enable_rls(
        "billing_subscriptionpaymentrequest", "billing_subscriptionevent"
    )
