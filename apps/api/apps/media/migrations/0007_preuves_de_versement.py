"""Les preuves de versement prennent leur propre genre.

---------------------------------------------------------------------------
Pourquoi « private » ne suffisait pas
---------------------------------------------------------------------------

Une capture d'ecran de paiement porte le nom de la cliente et parfois son
solde bancaire. C'est la piece la plus sensible de toute la reserve de
medias.

Elle etait rangee en `private`, ce qui la tenait hors de la vitrine publique.
Mais sous le genre « galerie » - celui que prenait alors tout televersement -
elle s'affichait dans la mediatheque du salon, entre ses photos de coiffures.
Et la protection ne tenait qu'a un seul drapeau : le jour ou quelqu'un
bascule la visibilite, la capture d'une cliente se retrouve en ligne.

Le genre est la seconde barriere, independante de la premiere.

---------------------------------------------------------------------------
La reprise ne devine rien
---------------------------------------------------------------------------

Les preuves deja enregistrees sont reconnaissables sans la moindre ambiguite :
une cle etrangere de `DepositProof` pointe sur chacune. Aucune heuristique,
aucun risque de reclasser une vraie realisation.

---------------------------------------------------------------------------
Le contexte tenant
---------------------------------------------------------------------------

Les tables metier portent `FORCE ROW LEVEL SECURITY` : hors contexte, aucune
ligne n'est visible. Une migration de donnees ecrite sans poser
`app.tenant_id` ne leverait aucune erreur - elle ne verrait rien, ne
modifierait rien, et laisserait la base a moitie convertie.
"""

from django.db import migrations, models

# Meme nom que dans apps/common/db.py. Recopie plutot qu'importe : une
# migration doit rester executable meme si le code applicatif evolue.
TENANT_GUC = "app.tenant_id"


def reprendre(apps_registry, schema_editor):
    connection = schema_editor.connection

    with connection.cursor() as cursor:
        cursor.execute("SELECT id FROM tenants_tenant")
        tenants = [row[0] for row in cursor.fetchall()]

        for tenant_id in tenants:
            cursor.execute(
                "SELECT set_config(%s, %s, true)", [TENANT_GUC, str(tenant_id)]
            )
            cursor.execute(
                """
                UPDATE media_mediaasset
                   SET kind = 'proof'
                 WHERE id IN (
                       SELECT image_id FROM payments_depositproof
                        WHERE image_id IS NOT NULL
                       )
                """
            )

        # On repart du contexte vide : laisser la variable posee ferait
        # travailler la suite de la transaction dans le dernier salon vu.
        cursor.execute("SELECT set_config(%s, '', true)", [TENANT_GUC])


def revenir(apps_registry, schema_editor):
    connection = schema_editor.connection

    with connection.cursor() as cursor:
        cursor.execute("SELECT id FROM tenants_tenant")
        tenants = [row[0] for row in cursor.fetchall()]

        for tenant_id in tenants:
            cursor.execute(
                "SELECT set_config(%s, %s, true)", [TENANT_GUC, str(tenant_id)]
            )
            cursor.execute(
                "UPDATE media_mediaasset SET kind = 'gallery' WHERE kind = 'proof'"
            )

        cursor.execute("SELECT set_config(%s, '', true)", [TENANT_GUC])


class Migration(migrations.Migration):

    dependencies = [
        ("media", "0006_genres_de_media"),
    ]

    operations = [
        migrations.AlterField(
            model_name="mediaasset",
            name="kind",
            field=models.CharField(
                choices=[
                    ("gallery", "Galerie"),
                    ("logo", "Logo"),
                    ("banner", "Bannière"),
                    ("service", "Prestation"),
                    ("staff", "Prestataire"),
                    ("payment", "QR de paiement"),
                    ("about", "Page À propos"),
                    ("product", "Article de boutique"),
                    ("proof", "Preuve de versement"),
                ],
                default="gallery",
                max_length=20,
            ),
        ),
        migrations.RunPython(reprendre, revenir),
    ]
