"""L'e-mail de contact des salons existants : l'adresse de leur proprietaire.

Le champ est ne vide (0014) ; le pied de page et la page Infos n'avaient
donc rien a montrer. Chaque salon sans adresse de contact recoit celle de son
proprietaire actif le plus ancien — la meme que les nouveaux salons recoivent
a l'inscription. Il la change ou l'efface depuis son profil.

Salon par salon, contexte pose et connexion de la migration : les profils
sont sous RLS (voir catalog/0011).
"""

from django.db import migrations

TENANT_GUC = "app.tenant_id"


def remplir(apps, schema_editor):
    SalonProfile = apps.get_model("salons", "SalonProfile")
    Membership = apps.get_model("accounts", "Membership")
    Tenant = apps.get_model("tenants", "Tenant")
    connexion = schema_editor.connection
    alias = connexion.alias

    for tenant_id in Tenant.objects.using(alias).values_list("id", flat=True):
        adresse = (
            Membership.objects.using(alias)
            .filter(tenant_id=tenant_id, role="owner", status="active", user__is_active=True)
            .order_by("created_at")
            .values_list("user__email", flat=True)
            .first()
        )
        if not adresse:
            continue
        with connexion.cursor() as curseur:
            curseur.execute("SELECT set_config(%s, %s, true)", [TENANT_GUC, str(tenant_id)])
        SalonProfile.objects.using(alias).filter(tenant_id=tenant_id, contact_email="").update(
            contact_email=adresse
        )

    with connexion.cursor() as curseur:
        curseur.execute("SELECT set_config(%s, '', true)", [TENANT_GUC])


class Migration(migrations.Migration):
    dependencies = [
        ("salons", "0014_email_de_contact"),
        ("accounts", "0001_initial"),
        ("tenants", "0001_initial"),
    ]

    # Rien a defaire : l'adresse reste modifiable par le salon.
    operations = [migrations.RunPython(remplir, migrations.RunPython.noop)]
