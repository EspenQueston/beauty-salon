"""Retire les offres Solo et Salon des debuts.

Il ne reste que l'essai, Standard (mensuel, annuel) et Pro (mensuel,
annuel). Les lignes Solo et Salon sont effacees si rien ne les reference ;
une offre encore citee par un abonnement, une demande de paiement ou un
historique est gardee (PROTECT) — un historique ne se reecrit pas, et la
migration ne doit jamais echouer pour autant.
"""

from django.db import migrations, models
from django.db.models.deletion import ProtectedError

ANCIENNES = ("solo", "salon")


def retirer(apps, schema_editor):
    alias = schema_editor.connection.alias
    Plan = apps.get_model("billing", "Plan")
    for plan in Plan.objects.using(alias).filter(code__in=ANCIENNES):
        try:
            plan.delete()
        except ProtectedError:
            # Reference par un historique : on la garde, desactivee.
            Plan.objects.using(alias).filter(pk=plan.pk).update(active=False)


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0010_offres_pro_et_fonctions"),
    ]

    operations = [
        migrations.RunPython(retirer, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="plan",
            name="code",
            field=models.CharField(
                choices=[
                    ("trial", "Essai"),
                    ("pro", "Pro (ancienne offre)"),
                    ("monthly", "Mensuel"),
                    ("yearly", "Annuel"),
                    ("pro_monthly", "Pro mensuel"),
                    ("pro_yearly", "Pro annuel"),
                ],
                max_length=20,
                unique=True,
            ),
        ),
    ]
