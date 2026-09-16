"""Isolation vue depuis l'API.

test_rls.py prouve que PostgreSQL tient. Ici on verifie la couche du dessus :
qu'aucune route ne laisse un salon atteindre les donnees d'un autre, meme en
forgeant les en-tetes que le frontend est cense poser.
"""

import pytest

from apps.accounts.models import Membership
from apps.scheduling.models import Booking
from conftest import as_tenant, salon_host
from tests.factories import BookingFactory

PASSWORD = "motdepasse-solide"


def login(client, user):
    assert client.login(email=user.email, password=PASSWORD)
    return client


def make_booking(salon):
    from datetime import timedelta

    from django.utils import timezone

    starts_at = timezone.now() + timedelta(days=10)
    with as_tenant(salon.tenant):
        return BookingFactory(
            tenant=salon.tenant,
            customer=salon.customer,
            staff_member=salon.staff,
            service=salon.service,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=120),
        )


@pytest.mark.django_db
def test_owner_sees_only_their_own_bookings(api_client, salon_a, salon_b):
    make_booking(salon_a)
    make_booking(salon_b)

    login(api_client, salon_a.owner)
    response = api_client.get("/api/v1/bookings/")

    assert response.status_code == 200
    assert response.data["count"] == 1


@pytest.mark.django_db
def test_reading_another_salons_booking_returns_404(api_client, salon_a, salon_b):
    """Un 404, pas un 403 : l'existence meme de la ressource ne doit pas
    fuiter vers un salon concurrent."""
    foreign = make_booking(salon_b)

    login(api_client, salon_a.owner)
    response = api_client.get(f"/api/v1/bookings/{foreign.id}/")

    assert response.status_code == 404


@pytest.mark.django_db
def test_forged_tenant_id_header_is_refused(api_client, salon_a, salon_b):
    """L'en-tete X-Tenant-Id est valide contre les memberships reels."""
    login(api_client, salon_a.owner)
    response = api_client.get(
        "/api/v1/bookings/", headers={"X-Tenant-Id": str(salon_b.tenant.id)}
    )

    assert response.status_code == 403
    assert response.json()["code"] == "tenant_forbidden"


@pytest.mark.django_db
def test_forged_tenant_host_header_has_no_effect_on_dashboard(
    api_client, salon_a, salon_b
):
    """Sur les routes authentifiees, le hostname n'est pas une source de
    verite : seul le membership compte."""
    make_booking(salon_b)

    login(api_client, salon_a.owner)
    response = api_client.get(
        "/api/v1/bookings/", headers={"X-Tenant-Host": salon_host("beautybyanna")}
    )

    assert response.status_code == 200
    assert response.data["count"] == 0


@pytest.mark.django_db
def test_cannot_create_a_booking_pointing_at_another_salon(
    api_client, salon_a, salon_b
):
    """Le tenant vient du contexte, jamais du corps de la requete."""
    login(api_client, salon_a.owner)

    from datetime import timedelta

    from django.utils import timezone

    response = api_client.post(
        "/api/v1/bookings/manual/",
        {
            "tenant": str(salon_b.tenant.id),  # ignore
            "service": str(salon_b.service.id),  # invisible depuis le salon A
            "staff_member": str(salon_b.staff.id),
            "full_name": "Intruse",
            "phone": "+242777777",
            "starts_at": (timezone.now() + timedelta(days=3)).isoformat(),
        },
        format="json",
    )

    assert response.status_code == 400
    with as_tenant(salon_b.tenant):
        assert Booking.objects.count() == 0


@pytest.mark.django_db
def test_anonymous_access_to_the_dashboard_is_refused(api_client, salon_a):
    response = api_client.get("/api/v1/bookings/")
    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_staff_role_sees_only_their_own_agenda(api_client, salon_a):
    """Une prestataire ne consulte pas l'agenda de ses collegues."""
    from tests.factories import (
        MembershipFactory,
        StaffMemberFactory,
        UserFactory,
    )

    make_booking(salon_a)  # attribue a salon_a.staff

    employee = UserFactory()
    membership = MembershipFactory(
        tenant=salon_a.tenant, user=employee, role=Membership.Role.STAFF
    )
    with as_tenant(salon_a.tenant):
        StaffMemberFactory(
            tenant=salon_a.tenant, name="Employee", membership=membership
        )

    login(api_client, employee)
    response = api_client.get("/api/v1/bookings/")

    assert response.status_code == 200
    assert response.data["count"] == 0


@pytest.mark.django_db
def test_staff_role_cannot_read_private_customer_notes(api_client, salon_a):
    from tests.factories import MembershipFactory, UserFactory

    with as_tenant(salon_a.tenant):
        salon_a.customer.private_notes = "Allergie a l'ammoniaque"
        salon_a.customer.save()

    employee = UserFactory()
    MembershipFactory(
        tenant=salon_a.tenant, user=employee, role=Membership.Role.STAFF
    )

    login(api_client, employee)
    listing = api_client.get("/api/v1/customers/")
    detail = api_client.get(f"/api/v1/customers/{salon_a.customer.id}/notes/")

    assert listing.status_code == 200
    assert "private_notes" not in listing.data["results"][0]
    assert detail.status_code == 403


@pytest.mark.django_db
def test_owner_can_read_private_customer_notes(api_client, salon_a):
    with as_tenant(salon_a.tenant):
        salon_a.customer.private_notes = "Allergie a l'ammoniaque"
        salon_a.customer.save()

    login(api_client, salon_a.owner)
    response = api_client.get(f"/api/v1/customers/{salon_a.customer.id}/notes/")

    assert response.status_code == 200
    assert response.data["private_notes"] == "Allergie a l'ammoniaque"


# ---------------------------------------------------------------------------
# Mini-sites publics
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_public_site_serves_the_salon_matching_the_hostname(api_client, salon_a, salon_b):
    first = api_client.get("/api/v1/public/salon", headers={"Host": salon_host("blondrose")})
    second = api_client.get(
        "/api/v1/public/salon", headers={"Host": salon_host("beautybyanna")}
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.data["slug"] == "blondrose"
    assert second.data["slug"] == "beautybyanna"


@pytest.mark.django_db
def test_public_site_only_lists_its_own_services(api_client, salon_a, salon_b):
    with as_tenant(salon_b.tenant):
        salon_b.service.name = "Prestation confidentielle"
        salon_b.service.save()

    response = api_client.get(
        "/api/v1/public/salon", headers={"Host": salon_host("blondrose")}
    )

    names = [
        service["name"]
        for category in response.data["categories"]
        for service in category["services"]
    ]
    assert names == ["Tresses"]


@pytest.mark.django_db
def test_unknown_subdomain_returns_404(api_client, salon_a):
    response = api_client.get(
        "/api/v1/public/salon", headers={"Host": salon_host("inconnu")}
    )

    assert response.status_code == 404
    assert response.json()["code"] == "tenant_not_found"
