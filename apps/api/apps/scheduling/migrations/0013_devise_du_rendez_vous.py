"""Chaque rendez-vous porte la devise dans laquelle il a ete vendu.

Elle etait lue sur le salon. Tant qu'un salon ne change jamais de devise,
c'est equivalent - et le jour ou il en change, tout son historique se
reetiquette : les 25 000 francs d'une pose de l'an dernier s'affichent comme
25 000 yuans, quatre-vingt-cinq fois leur valeur. Le montant, lui, ne bouge
pas ; c'est l'etiquette qui ment, ce qui est la pire des deux erreurs.

Le rattrapage recopie la devise actuelle de chaque salon sur ses
rendez-vous. C'est exact par construction : aucun salon n'a encore pu en
changer, puisque rien ne le permettait.

SQL brut sur le curseur du `schema_editor`, comme les autres migrations de
ce depot : un queryset de modele partirait sur l'alias `default` par le
routeur, pendant que le `set_config` vit sur cette connexion-ci - deux
connexions, donc zero ligne vue et une migration qui s'applique sans rien
faire.
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
                "UPDATE scheduling_booking SET currency = %s "
                "WHERE tenant_id = %s AND (currency = '' OR currency IS NULL)",
                [devise, str(tenant_id)],
            )

        curseur.execute("SELECT set_config(%s, '', true)", [TENANT_GUC])


def vider(apps, schema_editor):
    """Le retour en arriere efface la colonne, il ne la reinterprete pas."""
    with schema_editor.connection.cursor() as curseur:
        curseur.execute("SELECT id FROM tenants_tenant")
        for (tenant_id,) in curseur.fetchall():
            curseur.execute(
                "SELECT set_config(%s, %s, true)", [TENANT_GUC, str(tenant_id)]
            )
            curseur.execute(
                "UPDATE scheduling_booking SET currency = '' WHERE tenant_id = %s",
                [str(tenant_id)],
            )
        curseur.execute("SELECT set_config(%s, '', true)", [TENANT_GUC])


class Migration(migrations.Migration):
    dependencies = [
        ("scheduling", "0012_articles_achetes"),
        ("tenants", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="booking",
            name="currency",
            field=models.CharField(blank=True, max_length=3, verbose_name="devise"),
        ),
        migrations.RunPython(recopier, vider),
    ]
