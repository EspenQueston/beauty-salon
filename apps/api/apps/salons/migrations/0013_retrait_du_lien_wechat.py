"""Retire la cle « wechat » de `social_links`.

Elle tenait une adresse Web, et WeChat n'en a pas : on ne rejoint personne
par un lien, on scanne un QR ou l'on tape un identifiant. Le bouton qu'elle
alimentait menait donc, au mieux, a l'accueil de WeChat.

Le QR et l'identifiant vivent depuis la migration precedente dans leurs
propres colonnes, et le mini-site ne lit plus que celles-la. La cle est
maintenant morte : la laisser en base laisserait une adresse qui n'est
affichee nulle part et que plus aucun ecran ne permet de corriger.

Elle n'est pas convertible - une URL ne se transforme ni en identifiant ni
en image -, donc on l'efface. L'operation inverse est volontairement un
no-op : rejouer la migration a l'envers ne peut pas inventer les adresses
supprimees, et pretendre le contraire serait pire que ne rien faire.

Le contexte de salon est pose tenant par tenant : `SalonProfile` porte une
politique RLS, et une mise a jour globale ne verrait aucune ligne.

Et chaque requete porte `.using(alias)`. Sans lui, elle partirait sur
`default` par le routeur, pendant que le `set_config` vit sur la connexion
du `schema_editor` : deux connexions, donc zero ligne vue et une migration
qui s'applique sans rien faire. C'est exactement le piege dans lequel
`media.0008` est tombee, et il est silencieux.
"""

from django.db import migrations

CLE = "wechat"


def retirer(apps, schema_editor):
    Tenant = apps.get_model("tenants", "Tenant")
    SalonProfile = apps.get_model("salons", "SalonProfile")
    connexion = schema_editor.connection
    alias = connexion.alias

    for tenant_id in Tenant.objects.using(alias).values_list("id", flat=True):
        with connexion.cursor() as curseur:
            curseur.execute(
                "SELECT set_config('app.tenant_id', %s, true)", [str(tenant_id)]
            )

        for profil in SalonProfile.objects.using(alias).filter(tenant_id=tenant_id):
            liens = profil.social_links or {}
            if CLE not in liens:
                continue
            liens.pop(CLE)
            profil.social_links = liens
            profil.save(update_fields=["social_links"], using=alias)


def ne_rien_defaire(apps, schema_editor):
    """Rien a rejouer : les adresses effacees n'existent plus nulle part."""


class Migration(migrations.Migration):
    dependencies = [
        ("salons", "0012_wechat_du_salon"),
        ("tenants", "0001_initial"),
    ]

    operations = [migrations.RunPython(retirer, ne_rien_defaire)]
