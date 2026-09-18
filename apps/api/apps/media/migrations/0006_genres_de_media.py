"""Chaque image reprend le genre de son emploi reel.

---------------------------------------------------------------------------
Ce qui etait casse
---------------------------------------------------------------------------

Tout televersement arrivait etiquete « galerie », quel que soit l'ecran
d'origine : le selecteur de medias est partage, et aucun ecran ne disait au
serveur ce que l'image allait devenir.

Tant qu'une image finissait rattachee a son emploi, l'exclusion par cle
etrangere la retirait des realisations. Mais un televersement qu'on ne
rattache pas - on se trompe de fichier, on en essaie deux, on en change plus
tard - restait « galerie » pour toujours. C'est ainsi que des QR codes de
paiement se sont retrouves sur la page des realisations d'un salon, entre
deux coiffures.

---------------------------------------------------------------------------
Ce que cette migration fait, et ce qu'elle ne fait pas
---------------------------------------------------------------------------

Elle etiquette ce dont l'emploi est **certain** : toute image atteinte par
une cle etrangere - logo, banniere, photo « A propos », QR de paiement,
photo d'article, de prestation, de prestataire - prend le genre de cet
emploi.

Elle ne devine rien pour le reste. Une image televersee puis jamais
rattachee est indiscernable d'une realisation : la reclasser reviendrait a
retirer de la vitrine une photo que le salon y avait peut-etre mise. Ces
images restent « galerie », et c'est la deduplication a la lecture qui
ecarte celles qui ne sont qu'une seconde copie d'un fichier deja employe.

---------------------------------------------------------------------------
Pourquoi le SQL passe par la variable de session
---------------------------------------------------------------------------

Les tables metier portent `FORCE ROW LEVEL SECURITY` : hors contexte tenant,
**aucune ligne n'est visible**. Une migration de donnees ecrite naivement ne
leverait aucune erreur - elle ne verrait rien, ne modifierait rien, et
laisserait la base a moitie convertie sans que personne ne s'en apercoive.
On parcourt donc les salons un par un, comme le fait l'application.
"""

from django.db import migrations, models

# Meme nom que dans apps/common/db.py. Recopie plutot qu'importe : une
# migration doit rester executable meme si le code applicatif evolue.
TENANT_GUC = "app.tenant_id"

# Chaque emploi, et le genre qui lui correspond. La table est ecrite ici -
# et non deduite comme a la lecture - parce qu'une migration doit produire
# le meme resultat dans dix ans, quels que soient les modeles d'alors.
EMPLOIS = [
    ("salons_salonprofile", "logo_id", "logo"),
    ("salons_salonprofile", "banner_id", "banner"),
    ("salons_salonprofile", "about_image_id", "about"),
    ("payments_paymentchannel", "qr_image_id", "payment"),
    ("store_product", "image_id", "product"),
    ("catalog_service", "image_id", "service"),
    ("staff_staffmember", "photo_id", "staff"),
]


def reprendre(apps_registry, schema_editor):
    connection = schema_editor.connection

    with connection.cursor() as cursor:
        cursor.execute("SELECT id FROM tenants_tenant")
        tenants = [row[0] for row in cursor.fetchall()]

        for tenant_id in tenants:
            cursor.execute("SELECT set_config(%s, %s, true)", [TENANT_GUC, str(tenant_id)])

            for table, colonne, genre in EMPLOIS:
                cursor.execute(
                    f"""
                    UPDATE media_mediaasset
                       SET kind = %s
                     WHERE id IN (
                           SELECT {colonne} FROM {table}
                            WHERE {colonne} IS NOT NULL
                           )
                       AND kind = 'gallery'
                    """,
                    [genre],
                )

        # On repart du contexte vide : laisser la variable posee ferait
        # travailler la suite de la transaction dans le dernier salon vu.
        cursor.execute("SELECT set_config(%s, '', true)", [TENANT_GUC])


def revenir(apps_registry, schema_editor):
    """Tout ce qui n'est ni logo ni banniere redevient « galerie ».

    Les deux plus anciens genres existaient avant cette migration et
    survivent donc ; les quatre nouveaux n'ont plus de colonne ou vivre.
    """
    connection = schema_editor.connection

    with connection.cursor() as cursor:
        cursor.execute("SELECT id FROM tenants_tenant")
        tenants = [row[0] for row in cursor.fetchall()]

        for tenant_id in tenants:
            cursor.execute("SELECT set_config(%s, %s, true)", [TENANT_GUC, str(tenant_id)])
            cursor.execute(
                "UPDATE media_mediaasset SET kind = 'gallery' "
                "WHERE kind IN ('payment', 'about', 'product')"
            )

        cursor.execute("SELECT set_config(%s, '', true)", [TENANT_GUC])


class Migration(migrations.Migration):

    dependencies = [
        ("media", "0005_mediaasset_featured_alter_mediaasset_position"),
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
                ],
                default="gallery",
                max_length=20,
            ),
        ),
        migrations.RunPython(reprendre, revenir),
    ]
