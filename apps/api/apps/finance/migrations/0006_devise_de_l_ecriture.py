"""Chaque ecriture porte sa devise, figee le jour ou elle est passee.

Un livre de comptes ne se reetiquette pas. La devise etait lue sur le salon,
ce qui revient a dire que changer de devise reecrit retroactivement toute la
comptabilite : 25 000 francs encaisses en mars deviendraient 25 000 yuans en
avril, et le total de l'annee ne voudrait plus rien dire.

Le rattrapage recopie la devise actuelle de chaque salon sur ses mouvements.
Exact par construction : rien ne permettait encore d'en changer.

SQL brut sur le curseur du `schema_editor` — un queryset de modele partirait
sur `default` par le routeur, pendant que le `set_config` vit ici.
"""

from django.db import migrations, models

TENANT_GUC = "app.tenant_id"


def recopier(apps, schema_editor):
    with schema_editor.connection.cursor() as curseur:
        curseur.execute("SELECT id, currency FROM tenants_tenant")
        salons = curseur.fetchall()

        for tenant_id, devise in salons:
            curseur.execute(
                "SELECT set_config(%s, %s, true)", [TENANT_GUC, str(tenant_id)]
            )
            curseur.execute(
                "UPDATE finance_transaction SET currency = %s "
                "WHERE tenant_id = %s AND (currency = '' OR currency IS NULL)",
                [devise, str(tenant_id)],
            )

        curseur.execute("SELECT set_config(%s, '', true)", [TENANT_GUC])


def vider(apps, schema_editor):
    with schema_editor.connection.cursor() as curseur:
        curseur.execute("SELECT id FROM tenants_tenant")
        for (tenant_id,) in curseur.fetchall():
            curseur.execute(
                "SELECT set_config(%s, %s, true)", [TENANT_GUC, str(tenant_id)]
            )
            curseur.execute(
                "UPDATE finance_transaction SET currency = '' WHERE tenant_id = %s",
                [str(tenant_id)],
            )
        curseur.execute("SELECT set_config(%s, '', true)", [TENANT_GUC])


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0005_origine_forfait_deplacement"),
        ("tenants", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="transaction",
            name="currency",
            field=models.CharField(blank=True, max_length=3, verbose_name="devise"),
        ),
        migrations.RunPython(recopier, vider),
    ]
