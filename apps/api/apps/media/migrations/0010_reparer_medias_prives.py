"""Repare ce que `0008` n'a pas fait.

---------------------------------------------------------------------------
Ce qui s'est passe
---------------------------------------------------------------------------

`0008` devait sortir les fichiers prives - les preuves de versement - de la
racine servie publiquement, pour qu'ils ne sortent plus que par la route
authentifiee. Elle s'est appliquee sans erreur et n'a rien deplace.

La cause tient en une ligne : ses querysets ne portaient pas `.using()`. Un
`RunPython` recoit `schema_editor.connection`, ouverte sur l'alias des
migrations, mais un queryset de modele passe par le routeur et retombe sur
`default`. Le `set_config('app.tenant_id', ...)` vivait donc sur une autre
connexion que la lecture : sous RLS, `default` ne voyait aucun salon, la
boucle parcourait zero ligne, et Django inscrivait la migration comme
appliquee.

Resultat mesure avant cette reparation : deux preuves de versement - des
captures d'ecran de paiement portant le nom d'une cliente - repondaient 200
a une requete anonyme sur `/media/tenants/.../*.png`. La protection existait
dans le code et pas dans les donnees.

---------------------------------------------------------------------------
Ce que fait celle-ci
---------------------------------------------------------------------------

Exactement le travail de `0008`, avec l'alias corrige. Elle est ecrite pour
etre sans effet sur une base saine : un fichier deja sous `prive/` est
ignore, un fichier absent du stockage est signale et laisse en place.

`0008` est corrigee de son cote : une installation neuve n'a donc rien a
reparer, et cette migration n'y trouvera rien a faire.

Pas de retour en arriere : le defaire republierait les preuves.
"""

import logging

from django.db import migrations

logger = logging.getLogger(__name__)

PREFIXE = "prive"


def reparer(apps, schema_editor):
    MediaAsset = apps.get_model("media", "MediaAsset")
    Tenant = apps.get_model("tenants", "Tenant")
    connection = schema_editor.connection
    alias = connection.alias

    deplaces = 0

    for tenant_id in Tenant.objects.using(alias).values_list("id", flat=True):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT set_config('app.tenant_id', %s, true)", [str(tenant_id)]
            )

        prives = MediaAsset.objects.using(alias).filter(
            tenant_id=tenant_id, visibility="private"
        )
        for asset in prives:
            ancien = asset.file.name
            if not ancien or ancien.startswith(f"{PREFIXE}/"):
                continue

            nouveau = f"{PREFIXE}/{ancien}"
            stockage = asset.file.storage

            if not stockage.exists(ancien):
                logger.warning(
                    "Media %s : fichier absent du stockage, laisse en l'etat.", asset.id
                )
                continue

            # Copie d'abord. Une coupure entre les deux laisse deux copies,
            # jamais zero - et la copie en trop est sous `prive/`, donc hors
            # de portee.
            with stockage.open(ancien, "rb") as source:
                ecrit = stockage.save(nouveau, source)

            asset.file.name = ecrit
            asset.save(update_fields=["file"], using=alias)
            stockage.delete(ancien)
            deplaces += 1

    if deplaces:
        logger.warning(
            "%s fichier(s) prive(s) etaient restes a la racine publique et "
            "viennent d'etre deplaces sous %s/.",
            deplaces,
            PREFIXE,
        )


def ne_rien_defaire(apps, schema_editor):
    """Republier des preuves de versement ne se fait pas par megarde."""


class Migration(migrations.Migration):
    dependencies = [
        ("media", "0009_genre_qr_wechat"),
        ("tenants", "0001_initial"),
    ]

    operations = [migrations.RunPython(reparer, ne_rien_defaire)]
