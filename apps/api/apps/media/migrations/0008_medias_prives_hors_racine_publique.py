"""Deplace les fichiers prives sous `prive/`.

Les preuves de versement deja envoyees vivent au meme endroit que les photos
de coiffure. Tant qu'elles y restent, elles continuent d'etre servies par le
serveur de fichiers statiques : la route authentifiee ne protege que ce qui
est range au bon endroit.

Cette migration touche le disque, pas seulement la base. Elle est donc ecrite
pour etre rejouable et pour ne jamais perdre un fichier :

  - un fichier deja deplace est ignore ;
  - un fichier introuvable laisse la ligne intacte, avec un avertissement.
    Mieux vaut une reference cassee qu'on voit qu'une ligne effacee ;
  - la copie precede la suppression, jamais l'inverse.

Elle boucle sur les salons en posant `app.tenant_id` : les politiques RLS
s'appliquent aussi aux migrations de donnees, et une boucle qui l'oublie ne
voit aucune ligne - sans erreur, ce qui est le pire des cas.
"""

import logging

from django.db import migrations

logger = logging.getLogger(__name__)

PREFIXE = "prive"


def deplacer(apps, schema_editor):
    """Deplace les fichiers prives sous `prive/`.

    -----------------------------------------------------------------------
    Pourquoi chaque requete porte `.using(alias)`
    -----------------------------------------------------------------------

    Sans lui, cette migration ne faisait rien - et le disait en s'appliquant
    normalement.

    Un `RunPython` recoit `schema_editor.connection`, ouverte sur l'alias des
    migrations. Mais un queryset de modele n'en sait rien : il passe par le
    routeur, dont `db_for_read` renvoie `None`, donc par `default`. Le
    `set_config('app.tenant_id', ...)` pose juste au-dessus vit alors sur une
    *autre* connexion que la requete : la politique RLS de `default` ne voit
    aucun salon, la boucle parcourt zero ligne, et la migration est inscrite
    comme appliquee.

    Le symptome est muet et durable. Deux preuves de versement sont restees a
    la racine publique, servies en 200 sans authentification, pendant que
    `django_migrations` affirmait le contraire. C'est `0010` qui les repare
    sur les bases deja migrees ; ici, la correction sert les installations
    neuves.
    """
    MediaAsset = apps.get_model("media", "MediaAsset")
    Tenant = apps.get_model("tenants", "Tenant")
    connection = schema_editor.connection

    alias = connection.alias

    for tenant_id in Tenant.objects.using(alias).values_list("id", flat=True):
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.tenant_id', %s, true)", [str(tenant_id)])

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
            # jamais zero.
            with stockage.open(ancien, "rb") as source:
                ecrit = stockage.save(nouveau, source)

            asset.file.name = ecrit
            asset.save(update_fields=["file"], using=alias)
            stockage.delete(ancien)


def revenir(apps, schema_editor):
    """Retour en arriere : les fichiers remontent a la racine publique.

    On le fournit pour que la migration soit reversible, mais l'appeler
    republie des preuves de versement. A n'utiliser que pour rejouer une
    migration en developpement.
    """
    MediaAsset = apps.get_model("media", "MediaAsset")
    Tenant = apps.get_model("tenants", "Tenant")
    connection = schema_editor.connection

    alias = connection.alias

    for tenant_id in Tenant.objects.using(alias).values_list("id", flat=True):
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.tenant_id', %s, true)", [str(tenant_id)])

        for asset in MediaAsset.objects.using(alias).filter(
            tenant_id=tenant_id, visibility="private"
        ):
            ancien = asset.file.name
            if not ancien or not ancien.startswith(f"{PREFIXE}/"):
                continue

            nouveau = ancien[len(PREFIXE) + 1 :]
            stockage = asset.file.storage
            if not stockage.exists(ancien):
                continue

            with stockage.open(ancien, "rb") as source:
                ecrit = stockage.save(nouveau, source)

            asset.file.name = ecrit
            asset.save(update_fields=["file"], using=alias)
            stockage.delete(ancien)


class Migration(migrations.Migration):
    dependencies = [
        ("media", "0007_preuves_de_versement"),
        ("tenants", "0001_initial"),
    ]

    operations = [migrations.RunPython(deplacer, revenir)]
