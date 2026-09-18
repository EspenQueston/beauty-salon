"""Ouvre le domicile aux prestations des salons qui se deplacent.

---------------------------------------------------------------------------
Ce qu'on repare
---------------------------------------------------------------------------

Deux reglages parlent du meme sujet dans deux ecrans. Le salon dit s'il se
deplace (`SalonProfile.service_mode`), chaque prestation dit ou elle se fait
(`Service.location_mode`). Rien ne les reliait, et le second valait « au
salon » par defaut.

Consequence : une gerante reglait son profil sur « au salon ou a domicile »,
declarait trois quartiers avec leurs forfaits, et son parcours de
reservation continuait de n'offrir que le salon. Ses zones ne servaient a
rien, ses forfaits n'etaient jamais factures, et le symptome ne designait
pas sa cause - le champ fautif vit dans le formulaire de chaque prestation,
qu'elle n'a aucune raison d'ouvrir quinze fois.

---------------------------------------------------------------------------
Ce que cette migration change, et ce qu'elle ne touche pas
---------------------------------------------------------------------------

Elle aligne les prestations **restees sur « au salon »** dans les salons qui
se declarent « a domicile » ou « les deux ». C'est le seul cas ou l'on peut
affirmer que la valeur n'a pas ete choisie : elle contredit ce que le salon
dit de lui-meme au meme moment.

Elle ne touche pas les salons en mode « au salon » - il n'y a rien a ouvrir -
ni les prestations deja reglees sur « a domicile » ou « les deux », qui ont
ete decidees.

Elle ne cree aucune obligation : une prestation devenue « les deux » se
reserve toujours au salon, la cliente a simplement le choix.

Le sens inverse n'existe pas. Fermer le domicile sur des prestations est une
decision commerciale, pas la consequence mecanique d'un reglage - c'est
pourquoi l'operation inverse ne fait rien.

Les querysets portent `.using(alias)` et le contexte est pose par salon : un
`RunPython` dont la lecture part sur une autre connexion que le
`set_config` voit zero ligne et s'applique sans rien faire, en silence.
"""

import logging

from django.db import migrations

logger = logging.getLogger(__name__)

SALON = "salon"


def aligner(apps, schema_editor):
    SalonProfile = apps.get_model("salons", "SalonProfile")
    Service = apps.get_model("catalog", "Service")
    Tenant = apps.get_model("tenants", "Tenant")
    connection = schema_editor.connection
    alias = connection.alias

    total = 0

    for tenant_id in Tenant.objects.using(alias).values_list("id", flat=True):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT set_config('app.tenant_id', %s, true)", [str(tenant_id)]
            )

        profil = SalonProfile.objects.using(alias).filter(tenant_id=tenant_id).first()
        if profil is None or profil.service_mode == SALON:
            continue

        total += (
            Service.objects.using(alias)
            .filter(tenant_id=tenant_id, location_mode=SALON)
            .update(location_mode=profil.service_mode)
        )

    if total:
        logger.warning(
            "%s prestation(s) de salons se deplacant etaient restees « au "
            "salon » : elles suivent desormais le mode de leur salon.",
            total,
        )


def ne_rien_defaire(apps, schema_editor):
    """Refermer le domicile est une decision, pas un retour en arriere."""


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0010_acompte_regle_unique"),
        ("salons", "0013_retrait_du_lien_wechat"),
        ("tenants", "0001_initial"),
    ]

    operations = [migrations.RunPython(aligner, ne_rien_defaire)]
