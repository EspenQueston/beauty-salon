"""Le groupe Pro : deux offres, leurs prix en yuans, et ses fonctions.

Les offres mensuelle et annuelle existantes forment le groupe Standard (la
valeur par defaut du champ `group`, posee par 0009) : leurs prix, leurs
abonnes, leurs echeances et leur historique ne bougent pas.

Pro : 399 CNY par mois, 4 000 CNY par an — prix decides par le produit. Les
autres devises n'ont de prix que celui qu'un administrateur saisira.
"""

from decimal import Decimal

from django.db import migrations

OFFRES_PRO = [
    {
        "code": "pro_monthly",
        "name": "Pro mensuel",
        "description": "Tout Standard, plus domaine personnalisé, personnalisation avancée et assistants IA.",
        "billing_months": 1,
        "position": 20,
        "prix_cny": Decimal("399"),
    },
    {
        "code": "pro_yearly",
        "name": "Pro annuel",
        "description": "Tout Standard, plus domaine personnalisé, personnalisation avancée et assistants IA — pour douze mois.",
        "billing_months": 12,
        "position": 21,
        "prix_cny": Decimal("4000"),
    },
]

FONCTIONS = [
    ("custom_domain", "Relier au mini-site un nom de domaine que le salon possède déjà."),
    ("customization", "Polices, menu, disposition de l'accueil et textes d'accroche."),
    ("whatsapp_assistant", "Réponses automatiques aux messages WhatsApp du salon."),
    (
        "platform_assistant",
        "Un assistant dans l'espace professionnel, limité aux données du salon.",
    ),
    ("customer_assistant", "Un assistant automatique sur le mini-site, disponible à toute heure."),
]


def en_avant(apps, schema_editor):
    Plan = apps.get_model("billing", "Plan")
    PlanPrice = apps.get_model("billing", "PlanPrice")
    ProCapability = apps.get_model("billing", "ProCapability")
    alias = schema_editor.connection.alias

    for offre in OFFRES_PRO:
        champs = {k: v for k, v in offre.items() if k not in ("code", "prix_cny")}
        plan, _ = Plan.objects.using(alias).update_or_create(
            code=offre["code"], defaults={**champs, "group": "pro", "active": True}
        )
        PlanPrice.objects.using(alias).get_or_create(
            plan=plan, currency="CNY", defaults={"amount": offre["prix_cny"], "active": True}
        )

    for position, (code, description) in enumerate(FONCTIONS):
        ProCapability.objects.using(alias).get_or_create(
            code=code, defaults={"description": description, "position": position, "active": True}
        )


class Migration(migrations.Migration):
    dependencies = [("billing", "0009_offres_standard_pro")]

    operations = [migrations.RunPython(en_avant, migrations.RunPython.noop)]
