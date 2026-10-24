"""Verification des adresses e-mail.

Les comptes qui existent deja sont consideres comme verifies : ils recoivent
nos e-mails (reservations, rappels, abonnement) depuis leur creation, et les
bloquer du jour au lendemain punirait des salons et des clientes legitimes.
La verification s'applique aux comptes crees a partir d'ici, et a tout
changement d'adresse.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0005_alter_invitation_tenant")]

    operations = [
        migrations.AddField(
            model_name="user",
            name="email_verified_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="e-mail vérifié le"),
        ),
        migrations.RunSQL(
            sql="UPDATE accounts_user SET email_verified_at = created_at "
            "WHERE email_verified_at IS NULL;",
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
