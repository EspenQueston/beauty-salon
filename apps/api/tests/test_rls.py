"""La couche PostgreSQL de l'isolation.

Ces tests ne passent pas par Django : ils interrogent la base directement.
C'est volontaire. Le but est de verifier ce qui reste vrai *si* la couche
applicative est contournee.
"""

import pytest
from django.apps import apps as django_apps
from django.db import connection, transaction
from django.db.utils import ProgrammingError

from apps.common.db import TENANT_GUC, tenant_context
from apps.common.models import TenantOwnedModel
from apps.common.rls import POLICY_NAME
from apps.customers.models import Customer
from tests.factories import CustomerFactory


def tenant_owned_models():
    return [
        model
        for model in django_apps.get_models()
        if issubclass(model, TenantOwnedModel) and not model._meta.abstract
    ]


def test_at_least_one_model_is_discovered():
    # Garde-fou : si la decouverte cassait, les tests suivants passeraient
    # a vide et donneraient une fausse assurance.
    assert len(tenant_owned_models()) >= 8


@pytest.mark.django_db
@pytest.mark.parametrize("model", tenant_owned_models(), ids=lambda m: m._meta.db_table)
def test_every_tenant_model_has_forced_rls(model):
    """Ajouter un modele tenant sans sa migration RLS doit casser ici.

    C'est le filet qui empeche qu'un module ajoute plus tard - paiements,
    avis, marketplace - passe a travers l'isolation sans qu'on s'en apercoive.
    """
    table = model._meta.db_table
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
            "WHERE relname = %s AND relkind = 'r'",
            [table],
        )
        row = cursor.fetchone()

    assert row is not None, f"Table {table} introuvable."
    enabled, forced = row
    assert enabled, f"RLS non activee sur {table}."
    assert forced, f"FORCE ROW LEVEL SECURITY manquant sur {table}."


@pytest.mark.django_db
@pytest.mark.parametrize("model", tenant_owned_models(), ids=lambda m: m._meta.db_table)
def test_every_tenant_model_has_isolation_policy(model):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT policyname FROM pg_policies WHERE tablename = %s AND policyname = %s",
            [model._meta.db_table, POLICY_NAME],
        )
        assert cursor.fetchone() is not None


@pytest.mark.django_db
def test_raw_sql_without_tenant_context_returns_nothing(tenant_a):
    """Une requete SQL brute hors contexte ne voit rien : echec ferme."""
    with tenant_context(tenant_a.id):
        CustomerFactory(tenant=tenant_a, full_name="Cliente A")

        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM customers_customer")
            assert cursor.fetchone()[0] == 1

    # Hors du bloc, la variable de session est restauree a vide.
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting(%s, true)", [TENANT_GUC])
        assert (cursor.fetchone()[0] or "") == ""

        cursor.execute("SELECT count(*) FROM customers_customer")
        assert cursor.fetchone()[0] == 0


@pytest.mark.django_db
def test_insert_without_tenant_context_is_rejected(tenant_a):
    """La clause WITH CHECK bloque aussi les ecritures hors contexte."""
    with pytest.raises(ProgrammingError), transaction.atomic():
        Customer.all_tenants.create(
            tenant=tenant_a, full_name="Fantome", phone="+242999999"
        )


@pytest.mark.django_db
def test_cannot_write_a_row_for_another_tenant(tenant_a, tenant_b):
    """Meme dans un contexte valide, on ne peut pas ecrire chez le voisin."""
    with tenant_context(tenant_a.id), pytest.raises(ProgrammingError), transaction.atomic():
        Customer.all_tenants.create(
            tenant=tenant_b, full_name="Injection", phone="+242888888"
        )
