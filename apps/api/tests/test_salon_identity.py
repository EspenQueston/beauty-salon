"""Le nom du salon et les coordonnées de qui le tient.

Ces cinq champs vivent dans trois tables et se changent au même moment. Ce
qui est testé ici n'est pas qu'ils s'enregistrent — ce serait tester Django —
mais **ce qui doit rester vrai après** : que la plateforme voie le nouveau
nom, que la fiche de prestataire suive, et que personne d'autre que la
gérante ne puisse renommer le salon.
"""

import pytest

from apps.accounts.models import Membership
from apps.staff.models import StaffMember
from apps.tenants.models import Tenant
from conftest import as_tenant
from tests.factories import MembershipFactory, UserFactory

PASSWORD = "motdepasse-solide"
ROUTE = "/api/v1/salon-identity"


def login(client, user):
    assert client.login(email=user.email, password=PASSWORD)
    return client


def head(salon):
    return {"X-Tenant-Id": str(salon.tenant.id)}


@pytest.mark.django_db
def test_the_owner_reads_her_salon_and_her_own_details(api_client, salon_a):
    login(api_client, salon_a.owner)

    response = api_client.get(ROUTE, headers=head(salon_a))

    assert response.status_code == 200, response.data
    assert response.data["salon_name"] == salon_a.tenant.name
    assert response.data["owner_email"] == salon_a.owner.email
    # Le sous-domaine s'affiche mais ne se change pas : il est imprimé sur
    # des flyers et collé en QR au mur du salon.
    assert response.data["slug"] == salon_a.tenant.slug


@pytest.mark.django_db
def test_renaming_the_salon_is_what_the_platform_sees(api_client, salon_a):
    """Pas de recopie, donc pas de divergence possible.

    L'administration plateforme lit la ligne `Tenant`. Si le nouveau nom n'y
    était pas, la supervision continuerait d'afficher celui de l'inscription
    — et personne ne s'en apercevrait avant un échange au téléphone.
    """
    login(api_client, salon_a.owner)

    response = api_client.patch(
        ROUTE, {"salon_name": "Chez Fatou"}, format="json", headers=head(salon_a)
    )

    assert response.status_code == 200, response.data
    assert Tenant.objects.get(pk=salon_a.tenant.pk).name == "Chez Fatou"


@pytest.mark.django_db
def test_renaming_herself_renames_her_provider_card(api_client, salon_a):
    """Sinon le mini-site montrerait deux personnes.

    La gérante est prestataire par défaut, et sa fiche porte son nom. La
    laisser à l'ancien après un changement de nom donne une équipe de deux
    où il n'y a qu'une personne.
    """
    login(api_client, salon_a.owner)
    with as_tenant(salon_a.tenant):
        fiche = StaffMember.objects.create(
            tenant=salon_a.tenant,
            membership=salon_a.membership,
            name="Ancien nom",
            active=True,
        )

    api_client.patch(
        ROUTE, {"owner_name": "Fatou Nkounkou"}, format="json", headers=head(salon_a)
    )

    with as_tenant(salon_a.tenant):
        fiche.refresh_from_db()
    assert fiche.name == "Fatou Nkounkou"


@pytest.mark.django_db
def test_an_email_already_taken_is_refused(api_client, salon_a):
    """L'e-mail est l'identifiant de connexion.

    En laisser deux identiques rendrait l'un des deux comptes inaccessible.
    Le message ne dit pas à qui elle appartient : ce serait apprendre qui est
    inscrit.
    """
    login(api_client, salon_a.owner)
    autre = UserFactory(email="deja.pris@example.com")

    response = api_client.patch(
        ROUTE, {"owner_email": autre.email}, format="json", headers=head(salon_a)
    )

    assert response.status_code == 400
    assert "déjà utilisée" in str(response.data)
    salon_a.owner.refresh_from_db()
    assert salon_a.owner.email != autre.email


@pytest.mark.django_db
def test_her_own_email_is_not_taken_by_someone_else(api_client, salon_a):
    """Réenregistrer le formulaire sans toucher à l'adresse doit passer."""
    login(api_client, salon_a.owner)

    response = api_client.patch(
        ROUTE,
        {"owner_email": salon_a.owner.email, "owner_phone": "+242066112233"},
        format="json",
        headers=head(salon_a),
    )

    assert response.status_code == 200, response.data
    salon_a.owner.refresh_from_db()
    assert salon_a.owner.phone == "+242066112233"


@pytest.mark.django_db
def test_the_reception_desk_cannot_rename_the_salon(api_client, salon_a):
    """Un renommage surprise est une surprise pour tout le monde."""
    receptionniste = UserFactory()
    MembershipFactory(
        tenant=salon_a.tenant,
        user=receptionniste,
        role=Membership.Role.RECEPTIONIST,
    )
    login(api_client, receptionniste)

    response = api_client.patch(
        ROUTE, {"salon_name": "Renommé sans prévenir"}, format="json", headers=head(salon_a)
    )

    assert response.status_code == 403
    assert Tenant.objects.get(pk=salon_a.tenant.pk).name == salon_a.tenant.name


@pytest.mark.django_db
def test_an_empty_salon_name_is_refused(api_client, salon_a):
    """Un salon sans nom s'afficherait vide en haut de son mini-site."""
    login(api_client, salon_a.owner)

    response = api_client.patch(
        ROUTE, {"salon_name": "   "}, format="json", headers=head(salon_a)
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_nothing_leaks_from_another_salon(api_client, salon_a, salon_b):
    """L'en-tête de salon n'est jamais une autorisation."""
    login(api_client, salon_a.owner)

    response = api_client.get(ROUTE, headers={"X-Tenant-Id": str(salon_b.tenant.id)})

    assert response.status_code == 403
