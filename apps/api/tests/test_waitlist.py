"""Liste d'attente.

Elle ne reserve rien : c'est une demande de rappel. Ces tests verrouillent
surtout ce qu'elle ne doit *pas* faire - bloquer un creneau, fuir d'un salon
a l'autre, ou accepter un statut choisi par la cliente.
"""

from datetime import date, timedelta

import pytest

from apps.accounts.models import Membership
from apps.scheduling.models import WaitlistEntry
from conftest import as_tenant, salon_host
from tests.factories import MembershipFactory, UserFactory

PASSWORD = "motdepasse-solide"
HOST = {"Host": salon_host("blondrose")}


def login(client, user):
    assert client.login(email=user.email, password=PASSWORD)
    return client


def signup_payload(salon, **overrides):
    today = date.today()
    payload = {
        "service": str(salon.service.id),
        "full_name": "Awa Diallo",
        "phone": "+242066112233",
        "preferred_from": today.isoformat(),
        "preferred_to": (today + timedelta(days=14)).isoformat(),
    }
    payload.update(overrides)
    return payload


@pytest.mark.django_db
def test_a_client_can_ask_to_be_called_back(api_client, salon_a):
    response = api_client.post(
        "/api/v1/public/waitlist", signup_payload(salon_a), format="json", headers=HOST
    )

    assert response.status_code == 201
    with as_tenant(salon_a.tenant):
        entry = WaitlistEntry.objects.get(id=response.data["id"])
    assert entry.status == WaitlistEntry.Status.WAITING
    assert entry.full_name == "Awa Diallo"


@pytest.mark.django_db
def test_joining_the_waitlist_books_nothing(api_client, salon_a):
    """Le point qui compte : une inscription n'occupe aucun creneau."""
    from apps.scheduling.models import Booking

    api_client.post(
        "/api/v1/public/waitlist", signup_payload(salon_a), format="json", headers=HOST
    )

    with as_tenant(salon_a.tenant):
        assert Booking.objects.count() == 0


@pytest.mark.django_db
def test_a_client_cannot_choose_her_own_status(api_client, salon_a):
    """Sinon on s'inscrirait directement en « rendez-vous pris »."""
    response = api_client.post(
        "/api/v1/public/waitlist",
        signup_payload(salon_a, status="booked"),
        format="json",
        headers=HOST,
    )

    assert response.status_code == 201
    with as_tenant(salon_a.tenant):
        assert (
            WaitlistEntry.objects.get(id=response.data["id"]).status
            == WaitlistEntry.Status.WAITING
        )


@pytest.mark.django_db
def test_a_backwards_window_is_refused(api_client, salon_a):
    today = date.today()
    response = api_client.post(
        "/api/v1/public/waitlist",
        signup_payload(
            salon_a,
            preferred_from=(today + timedelta(days=10)).isoformat(),
            preferred_to=today.isoformat(),
        ),
        format="json",
        headers=HOST,
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_another_salons_service_cannot_be_used(api_client, salon_a, salon_b):
    response = api_client.post(
        "/api/v1/public/waitlist",
        signup_payload(salon_a, service=str(salon_b.service.id)),
        format="json",
        headers=HOST,
    )

    assert response.status_code in (400, 404)


@pytest.mark.django_db
def test_the_salon_sees_only_what_is_left_to_handle(api_client, salon_a):
    api_client.post(
        "/api/v1/public/waitlist", signup_payload(salon_a), format="json", headers=HOST
    )
    api_client.post(
        "/api/v1/public/waitlist",
        signup_payload(salon_a, full_name="Deja classee"),
        format="json",
        headers=HOST,
    )
    with as_tenant(salon_a.tenant):
        closed = WaitlistEntry.objects.get(full_name="Deja classee")
        closed.status = WaitlistEntry.Status.CLOSED
        closed.save()

    login(api_client, salon_a.owner)
    open_only = api_client.get("/api/v1/waitlist/")
    everything = api_client.get("/api/v1/waitlist/?status=all")

    names = {row["full_name"] for row in open_only.data["results"]}
    assert names == {"Awa Diallo"}
    assert len(everything.data["results"]) == 2


@pytest.mark.django_db
def test_marking_someone_as_contacted_records_when(api_client, salon_a):
    created = api_client.post(
        "/api/v1/public/waitlist", signup_payload(salon_a), format="json", headers=HOST
    )
    login(api_client, salon_a.owner)

    response = api_client.post(f"/api/v1/waitlist/{created.data['id']}/contacted/")

    assert response.status_code == 200
    assert response.data["status"] == "contacted"
    assert response.data["contacted_at"] is not None


@pytest.mark.django_db
def test_one_salon_never_sees_another_salons_waitlist(api_client, salon_a, salon_b):
    """Cette table porte des coordonnees de clientes."""
    api_client.post(
        "/api/v1/public/waitlist", signup_payload(salon_a), format="json", headers=HOST
    )

    intruder = UserFactory()
    MembershipFactory(tenant=salon_b.tenant, user=intruder, role=Membership.Role.OWNER)
    login(api_client, intruder)

    response = api_client.get(
        "/api/v1/waitlist/", headers={"Host": salon_host(salon_b.tenant.slug)}
    )

    assert response.status_code == 200
    assert response.data["results"] == []


@pytest.mark.django_db
def test_a_stylist_may_read_the_waitlist_but_not_change_it(api_client, salon_a):
    created = api_client.post(
        "/api/v1/public/waitlist", signup_payload(salon_a), format="json", headers=HOST
    )
    stylist = UserFactory()
    MembershipFactory(tenant=salon_a.tenant, user=stylist, role=Membership.Role.STAFF)
    login(api_client, stylist)

    assert api_client.get("/api/v1/waitlist/").status_code == 200
    assert (
        api_client.post(f"/api/v1/waitlist/{created.data['id']}/contacted/").status_code
        == 403
    )
