"""Compteur de numeros de facture.

Une sequence PostgreSQL plutot qu'un `SELECT max(number)` :

- elle est atomique, donc deux emissions simultanees ne peuvent pas tomber
  sur le meme numero ;
- elle ne depend d'aucune lecture de table, donc ni les politiques RLS ni
  une transaction ouverte ne la faussent - c'est exactement ce qui produisait
  des doublons quand plusieurs salons etaient factures dans la meme passe.

La contrepartie est connue : un `ROLLBACK` consomme un numero et laisse un
trou. C'est le comportement standard des sequences, et il vaut mieux qu'un
doublon.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("billing", "0002_rls")]

    operations = [
        migrations.RunSQL(
            sql="CREATE SEQUENCE IF NOT EXISTS billing_invoice_number_seq START 1;",
            reverse_sql="DROP SEQUENCE IF EXISTS billing_invoice_number_seq;",
        ),
        migrations.RunSQL(
            sql="GRANT USAGE, SELECT ON SEQUENCE billing_invoice_number_seq TO salon_app;",
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
