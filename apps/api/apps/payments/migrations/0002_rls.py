"""Isolation RLS de l'encaissement.

Le QR code d'un salon est son compte bancaire ; les preuves de versement
portent les captures d'ecran de ses clientes. Ni l'un ni l'autre ne regarde
un autre salon.
"""

from django.db import migrations

from apps.common.rls import enable_rls


class Migration(migrations.Migration):
    dependencies = [("payments", "0001_encaissement")]

    operations = [
        *enable_rls("payments_paymentchannel"),
        *enable_rls("payments_depositproof"),
    ]
