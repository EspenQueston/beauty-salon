"""Generation des politiques Row-Level Security.

Chaque module metier ajoute une migration qui appelle `enable_rls()` sur ses
tables. La politique produite compare `tenant_id` a la variable de session
`app.tenant_id`, posee par apps/common/db.py au debut de chaque requete.

Deux details comptent :

- `FORCE ROW LEVEL SECURITY` : sans lui, le proprietaire de la table est
  exempte des politiques. Comme le proprietaire varie (salon_admin en
  developpement, salon_app dans la base de test), l'exemption serait une
  faille invisible.
- `NULLIF(..., '')` : hors contexte tenant la variable vaut la chaine vide.
  Sans NULLIF, le cast en uuid leverait une erreur SQL ; avec lui la
  comparaison vaut NULL et aucune ligne ne passe. Echec ferme.

Les tables de routage et d'identite (tenants, domains, users, memberships)
ne recoivent volontairement pas de politique : elles doivent etre lisibles
*avant* qu'un tenant soit resolu. Leur controle d'acces est applicatif, via
apps/common/permissions.py.
"""

from django.db import migrations

from .db import TENANT_GUC

POLICY_NAME = "tenant_isolation"

_TENANT_EXPR = f"NULLIF(current_setting('{TENANT_GUC}', true), '')::uuid"


def enable_rls(*tables: str) -> list[migrations.RunSQL]:
    """Operations de migration activant l'isolation sur les tables donnees."""
    operations = []
    for table in tables:
        forward = f"""
            ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY;
            ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY;
            DROP POLICY IF EXISTS {POLICY_NAME} ON "{table}";
            CREATE POLICY {POLICY_NAME} ON "{table}"
                USING (tenant_id = {_TENANT_EXPR})
                WITH CHECK (tenant_id = {_TENANT_EXPR});
        """
        reverse = f"""
            DROP POLICY IF EXISTS {POLICY_NAME} ON "{table}";
            ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY;
            ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY;
        """
        operations.append(migrations.RunSQL(sql=forward, reverse_sql=reverse))
    return operations
