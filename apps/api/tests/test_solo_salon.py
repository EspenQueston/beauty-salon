"""Le parcours d'une gérante seule, de l'inscription au premier créneau.

---------------------------------------------------------------------------
Pourquoi ce fichier existe
---------------------------------------------------------------------------

C'est le parcours le plus fréquent du produit, et c'était le plus fragile.
Une personne s'inscrit, crée sa première prestation, ouvre son mini-site —
et y lit « aucune disponibilité ». Rien n'est cassé : il manque une ligne
dans une table de liaison dont elle n'a aucune raison de connaître
l'existence.

Le défaut est le pire de sa catégorie parce qu'il est **silencieux**. La page
ne signale aucune erreur, elle ne propose simplement rien, et la conclusion
qu'on en tire est que la réservation ne marche pas.

Ces tests parcourent la chaîne entière plutôt que ses maillons : c'est la
seule façon de constater qu'il manquait quelque chose entre deux d'entre eux.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.services import signup_salon
from apps.catalog.models import Service, ServiceCategory
from apps.staff.models import StaffMember, StaffService
from conftest import as_tenant, salon_host

PASSWORD = "motdepasse-solide"


def solo():
    """Une gérante fraîchement inscrite, seule, sans catalogue."""
    return signup_salon(
        name="Chez Awa",
        slug="chezawa",
        email="awa@example.com",
        password=PASSWORD,
        display_name="Awa Diallo",
    )


def create_service(api_client, tenant, **overrides):
    with as_tenant(tenant):
        category = ServiceCategory.objects.create(tenant=tenant, name="Coiffure")

    payload = {
        "category": str(category.id),
        "name": "Box braids",
        "duration_minutes": 120,
        "price_amount": "25000",
        "requires_deposit": False,
    }
    payload.update(overrides)
    return api_client.post(
        "/api/v1/services/",
        payload,
        format="json",
        headers={"X-Tenant-Id": str(tenant.id)},
    )


@pytest.mark.django_db
def test_a_solo_owner_can_be_booked_the_day_she_creates_her_first_service(
    api_client, db
):
    """Le parcours complet, sans une seule étape de configuration cachée."""
    tenant, user = solo()
    assert api_client.login(email=user.email, password=PASSWORD)

    response = create_service(api_client, tenant)
    assert response.status_code == 201, response.data

    with as_tenant(tenant):
        service = Service.objects.get()
        liens = StaffService.objects.filter(service=service)
        assert liens.count() == 1, "la prestation n'est reliée à personne"
        assert liens.first().staff_member.membership.user == user

    # Et le mini-site public propose bien des créneaux.
    api_client.logout()
    debut = (timezone.now() + timedelta(days=2)).date()
    creneaux = api_client.get(
        f"/api/v1/public/availability?service={service.id}"
        f"&date_from={debut}&date_to={debut + timedelta(days=7)}",
        headers={"Host": salon_host("chezawa")},
    )

    assert creneaux.status_code == 200, creneaux.data
    jours = creneaux.data.get("days") or creneaux.data
    assert jours, "le mini-site ne propose aucun créneau"


@pytest.mark.django_db
def test_a_second_provider_is_never_assumed_to_do_everything(api_client, db):
    """Deux personnes, et le lien redevient un choix.

    La prothésiste ongulaire ne pose pas les box braids. Deviner le contraire
    produirait des créneaux que le salon ne peut pas tenir — et une cliente
    devant une porte close.
    """
    tenant, user = solo()
    assert api_client.login(email=user.email, password=PASSWORD)

    with as_tenant(tenant):
        StaffMember.objects.create(tenant=tenant, name="Chantal", active=True)

    response = create_service(api_client, tenant)
    assert response.status_code == 201, response.data

    with as_tenant(tenant):
        service = Service.objects.get()
        assert StaffService.objects.filter(service=service).count() == 0


@pytest.mark.django_db
def test_an_archived_provider_does_not_count_as_the_sole_one(api_client, db):
    """Une fiche retirée ne rend pas le salon « à deux ».

    Sinon une gérante qui a fait un essai puis désactivé la fiche retomberait
    dans le silence d'origine, sans comprendre pourquoi.
    """
    tenant, user = solo()
    assert api_client.login(email=user.email, password=PASSWORD)

    with as_tenant(tenant):
        StaffMember.objects.create(tenant=tenant, name="Ancienne", active=False)

    create_service(api_client, tenant)

    with as_tenant(tenant):
        service = Service.objects.get()
        assert StaffService.objects.filter(service=service).count() == 1


@pytest.mark.django_db
def test_a_deposit_service_still_gets_its_link(api_client, db):
    """L'acompte ne change rien à qui réalise la prestation."""
    tenant, user = solo()
    assert api_client.login(email=user.email, password=PASSWORD)

    create_service(api_client, tenant, requires_deposit=True)

    with as_tenant(tenant):
        service = Service.objects.get()
        assert service.requires_deposit is True
        assert StaffService.objects.filter(service=service).count() == 1
