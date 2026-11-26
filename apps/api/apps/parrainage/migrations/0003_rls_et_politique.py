from django.db import migrations
from apps.common.rls import enable_rls


def configurer(apps, schema_editor):
    alias = schema_editor.connection.alias
    apps.get_model("parrainage", "PolitiquePlateforme").objects.using(alias).get_or_create(
        pk=1,
        defaults={
            "active": True,
            "cooling_mode": "demi_periode",
            "validite_jours": 90,
            "validite_depuis_disponibilite": True,
            "recompenses_max_par_parrain": 100,
            "remises_max_par_echeance": 1,
            "reservation_heures": 24,
            "apres_remboursement": "maintenir",
        },
    )


class Migration(migrations.Migration):
    dependencies = [("parrainage", "0002_politiqueplateforme_parrainage_essai_debut_and_more")]
    operations = [
        *enable_rls("parrainage_politiquesalon"),
        *enable_rls("parrainage_codeclientsalon"),
        *enable_rls("parrainage_recompenseclient"),
        migrations.RunPython(configurer, migrations.RunPython.noop),
    ]
