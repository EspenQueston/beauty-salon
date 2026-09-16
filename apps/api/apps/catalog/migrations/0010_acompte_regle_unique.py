"""L'acompte n'a plus qu'un seul endroit ou se regler.

---------------------------------------------------------------------------
Ce qui etait casse
---------------------------------------------------------------------------

Chaque prestation portait un montant d'acompte, qui servait a la fois
d'interrupteur (« cette prestation en demande un ») et de plancher. La fiche
du salon portait par ailleurs un pourcentage. Resultat visible par les
clientes : le mini-site annoncait « acompte de 5 000 » et la page de
reglement en reclamait 7 500, parce que 30 % de 25 000 l'emportait sur le
montant affiche. Le salon publiait un chiffre et en facturait un autre.

---------------------------------------------------------------------------
Ce que cette migration fait des donnees existantes
---------------------------------------------------------------------------

1. Toute prestation dont le montant etait superieur a zero garde son
   acompte : elle passe a `requires_deposit = True`. Aucune prestation ne se
   met a en demander un, aucune ne cesse d'en demander.

2. Le plancher remonte au niveau du salon, a la **plus petite** des valeurs
   declarees sur ses prestations. Le minimum et non la moyenne ni le
   maximum : un plancher commun tire des valeurs hautes ferait payer, sur
   une petite prestation, davantage qu'avant - et personne ne doit se voir
   reclamer plus a cause d'une migration.

   Consequence assumee : un salon qui n'avait **aucun** taux et s'appuyait
   uniquement sur des montants fixes differents verra ses plus grosses
   prestations demander moins qu'avant, jusqu'a ce qu'il regle son
   pourcentage. La direction est la bonne - jamais plus, parfois moins.

---------------------------------------------------------------------------
Pourquoi du SQL brut, et pourquoi cette variable de session
---------------------------------------------------------------------------

Les tables metier portent `FORCE ROW LEVEL SECURITY` : le proprietaire
lui-meme est soumis aux politiques, et hors contexte tenant **aucune ligne
n'est visible**. Une migration de donnees ecrite naivement ne leverait donc
aucune erreur : elle ne verrait rien, ne modifierait rien, et laisserait la
base a moitie convertie sans que personne ne s'en apercoive.

On parcourt donc les salons un par un en posant `app.tenant_id`, exactement
comme le fait l'application. Les modeles historiques ne conviendraient pas
davantage : leur gestionnaire par defaut filtre sur une ContextVar Python
qui, elle non plus, n'est pas posee ici.
"""

from django.db import migrations, models

# Meme nom que dans apps/common/db.py. Recopie plutot qu'importe : une
# migration doit rester lisible et executable meme si le code applicatif
# evolue autour d'elle.
TENANT_GUC = "app.tenant_id"


def reprendre(apps, schema_editor):
    connection = schema_editor.connection

    with connection.cursor() as cursor:
        cursor.execute("SELECT id FROM tenants_tenant")
        tenants = [row[0] for row in cursor.fetchall()]

        for tenant_id in tenants:
            cursor.execute("SELECT set_config(%s, %s, true)", [TENANT_GUC, str(tenant_id)])

            cursor.execute(
                "UPDATE catalog_service SET requires_deposit = TRUE "
                "WHERE deposit_amount > 0"
            )

            cursor.execute(
                "SELECT MIN(deposit_amount) FROM catalog_service "
                "WHERE deposit_amount > 0"
            )
            plancher = cursor.fetchone()[0]
            if plancher:
                cursor.execute(
                    "UPDATE salons_salonprofile SET deposit_minimum = %s",
                    [plancher],
                )

        # On repart du contexte vide : laisser la variable posee ferait
        # travailler la suite de la transaction dans le dernier salon vu.
        cursor.execute("SELECT set_config(%s, '', true)", [TENANT_GUC])


def revenir(apps, schema_editor):
    """Rend a chaque prestation un montant d'acompte.

    On ne peut pas restituer les montants d'origine - ils sont perdus par la
    suppression de la colonne. On repose le plancher du salon sur les
    prestations qui en demandaient un, ce qui retablit un etat coherent sans
    pretendre retrouver l'ancien.
    """
    connection = schema_editor.connection

    with connection.cursor() as cursor:
        cursor.execute("SELECT id FROM tenants_tenant")
        tenants = [row[0] for row in cursor.fetchall()]

        for tenant_id in tenants:
            cursor.execute("SELECT set_config(%s, %s, true)", [TENANT_GUC, str(tenant_id)])
            cursor.execute("SELECT deposit_minimum FROM salons_salonprofile LIMIT 1")
            row = cursor.fetchone()
            plancher = row[0] if row else 0
            cursor.execute(
                "UPDATE catalog_service SET deposit_amount = %s "
                "WHERE requires_deposit IS TRUE",
                [plancher or 0],
            )

        cursor.execute("SELECT set_config(%s, '', true)", [TENANT_GUC])


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0009_plafond_quantite_ressource"),
        # Le plancher du salon doit exister avant qu'on y verse les montants.
        ("salons", "0011_acompte_regle_unique"),
    ]

    operations = [
        migrations.AddField(
            model_name="service",
            name="requires_deposit",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Le montant vient de la règle de votre salon : un "
                    "pourcentage de la prestation, avec un minimum."
                ),
                verbose_name="demande un acompte",
            ),
        ),
        # La reprise se place entre l'ajout et la suppression : c'est le seul
        # moment ou les deux colonnes coexistent.
        migrations.RunPython(reprendre, revenir),
        migrations.RemoveField(
            model_name="service",
            name="deposit_amount",
        ),
    ]
