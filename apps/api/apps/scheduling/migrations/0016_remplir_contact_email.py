"""Donne aux rendez-vous existants l'adresse e-mail de leur fiche.

Avant `contact_email`, l'adresse d'un rendez-vous etait celle de la fiche
cliente : c'est a elle que partaient les e-mails. On la recopie donc telle
quelle, en minuscules, pour que l'historique de chaque cliente reste visible
dans son espace et que les e-mails a venir partent au meme endroit.

Salon par salon, sous son contexte : `scheduling_booking` et
`customers_customer` sont sous RLS forcee, et une requete hors contexte ne
verrait aucune ligne — la migration passerait sans rien faire, en silence.
"""

from django.db import migrations


def remplir(apps, schema_editor):
    Tenant = apps.get_model("tenants", "Tenant")
    connection = schema_editor.connection
    alias = connection.alias

    for tenant_id in Tenant.objects.using(alias).values_list("id", flat=True):
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.tenant_id', %s, true)", [str(tenant_id)])
            cursor.execute(
                """
                UPDATE scheduling_booking AS b
                   SET contact_email = lower(trim(c.email))
                  FROM customers_customer AS c
                 WHERE b.customer_id = c.id
                   AND b.tenant_id = %s
                   AND b.contact_email = ''
                   AND c.email <> ''
                """,
                [str(tenant_id)],
            )


def ne_rien_defaire(apps, schema_editor):
    """La colonne disparait avec la migration precedente ; rien a remettre."""


class Migration(migrations.Migration):
    dependencies = [
        ("scheduling", "0015_contact_email_et_compte"),
        ("customers", "0001_initial"),
        ("tenants", "0001_initial"),
    ]

    operations = [migrations.RunPython(remplir, ne_rien_defaire)]
