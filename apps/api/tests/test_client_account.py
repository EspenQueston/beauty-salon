"""Comptes clientes, et l'isolation qu'ils ne doivent pas casser.

Un compte cliente vit au-dessus des salons : c'est le seul endroit du
produit ou une meme session touche plusieurs tenants. C'est donc l'endroit
le plus dangereux, et ces tests portent surtout sur ce qui ne doit *pas*
arriver.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import Membership
from apps.clients.models import ClientProfile, ClientSalonLink
from apps.scheduling.models import Booking
from conftest import as_tenant, salon_host
from tests.factories import MembershipFactory, UserFactory

PASSWORD = "motdepasse-solide"
HOST_A = {"Host": salon_host("blondrose")}


def signup(client, host, **overrides):
    payload = {
        "full_name": "Awa Diallo",
        "email": "awa@example.com",
        "phone": "+242066112233",
        "password": "Tresses-2026-Brazza",
    }
    payload.update(overrides)
    return client.post("/api/v1/public/client/signup", payload, format="json", headers=host)


def make_booking(salon, customer, **overrides):
    starts_at = timezone.now() - timedelta(days=3)
    with as_tenant(salon.tenant):
        return Booking.objects.create(
            tenant=salon.tenant,
            customer=customer,
            staff_member=salon.staff,
            service=salon.service,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(hours=2),
            status=Booking.Status.COMPLETED,
            service_name=overrides.get("service_name", "Box braids"),
            total_amount=Decimal("450"),
        )


# ---------------------------------------------------------------------------
# Inscription et session
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_client_can_create_an_account_from_a_mini_site(api_client, salon_a):
    response = signup(api_client, HOST_A)

    assert response.status_code == 201, response.data
    # Le salon d'ou elle s'inscrit devient son favori : c'est le seul
    # qu'elle connaisse a cet instant.
    assert response.data["preferred_salon_slug"] == salon_a.tenant.slug
    assert ClientProfile.objects.filter(user__email="awa@example.com").exists()


@pytest.mark.django_db
def test_the_password_is_never_returned(api_client, salon_a):
    response = signup(api_client, HOST_A)

    assert "password" not in response.data


@pytest.mark.django_db
def test_a_weak_password_is_refused(api_client, salon_a):
    response = signup(api_client, HOST_A, password="123456789")

    assert response.status_code == 400
    assert "password" in str(response.data).lower()


@pytest.mark.django_db
def test_an_email_already_taken_is_refused(api_client, salon_a):
    signup(api_client, HOST_A)
    api_client.logout()

    response = signup(api_client, HOST_A, phone="+242066999999")

    assert response.status_code == 400


@pytest.mark.django_db
def test_signing_up_logs_her_in_straight_away(api_client, salon_a):
    signup(api_client, HOST_A)

    response = api_client.get("/api/v1/public/client/me", headers=HOST_A)

    assert response.status_code == 200
    assert response.data["email"] == "awa@example.com"


@pytest.mark.django_db
def test_whatsapp_and_wechat_are_optional_but_kept(api_client, salon_a):
    response = signup(api_client, HOST_A, whatsapp="+8613700001111", wechat="awa_bzv")

    assert response.status_code == 201
    assert response.data["whatsapp"] == "+8613700001111"
    assert response.data["wechat"] == "awa_bzv"


# ---------------------------------------------------------------------------
# Historique multi-salon
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_her_history_gathers_every_salon_she_visited(api_client, salon_a, salon_b):
    """Le coeur de la fonctionnalite : un compte, plusieurs salons."""
    signup(api_client, HOST_A)
    user = ClientProfile.objects.get(user__email="awa@example.com").user

    make_booking(salon_a, salon_a.customer, service_name="Box braids")
    make_booking(salon_b, salon_b.customer, service_name="Pose de gel")
    ClientSalonLink.objects.create(
        user=user, tenant=salon_a.tenant, customer_id=salon_a.customer.id
    )
    ClientSalonLink.objects.create(
        user=user, tenant=salon_b.tenant, customer_id=salon_b.customer.id
    )

    response = api_client.get("/api/v1/public/client/bookings", headers=HOST_A)

    assert response.status_code == 200
    names = {row["service_name"] for row in response.data["bookings"]}
    assert names == {"Box braids", "Pose de gel"}
    assert len(response.data["salons"]) == 2


@pytest.mark.django_db
def test_she_sees_nothing_from_a_salon_she_is_not_linked_to(api_client, salon_a, salon_b):
    """L'isolation, vue depuis le compte cliente.

    Meme connectee, meme avec un historique ailleurs, elle ne doit rien lire
    d'un salon auquel son compte n'est pas rattache.
    """
    signup(api_client, HOST_A)
    user = ClientProfile.objects.get(user__email="awa@example.com").user

    make_booking(salon_a, salon_a.customer, service_name="Box braids")
    make_booking(salon_b, salon_b.customer, service_name="Secret du salon B")
    # Rattachee au salon A uniquement.
    ClientSalonLink.objects.create(
        user=user, tenant=salon_a.tenant, customer_id=salon_a.customer.id
    )

    response = api_client.get("/api/v1/public/client/bookings", headers=HOST_A)

    names = {row["service_name"] for row in response.data["bookings"]}
    assert names == {"Box braids"}
    assert "Secret du salon B" not in str(response.data)


@pytest.mark.django_db
def test_a_link_pointing_at_another_salons_customer_leaks_nothing(
    api_client, salon_a, salon_b
):
    """Le pire cas : un rattachement incoherent.

    Si un lien designait la fiche d'un salon B tout en nommant le salon A,
    la lecture se fait dans le contexte du salon A - ou cette fiche n'existe
    pas. RLS renvoie donc vide, au lieu de reveler les rendez-vous du B.
    """
    signup(api_client, HOST_A)
    user = ClientProfile.objects.get(user__email="awa@example.com").user

    make_booking(salon_b, salon_b.customer, service_name="Secret du salon B")
    ClientSalonLink.objects.create(
        user=user,
        tenant=salon_a.tenant,  # salon A...
        customer_id=salon_b.customer.id,  # ...mais fiche du salon B
    )

    response = api_client.get("/api/v1/public/client/bookings", headers=HOST_A)

    assert response.status_code == 200
    assert response.data["bookings"] == []


@pytest.mark.django_db
def test_booking_while_logged_in_adds_the_salon_to_her_account(api_client, salon_a):
    """Sans ce rattachement, le rendez-vous existe mais reste invisible."""
    from datetime import date, datetime, time
    from zoneinfo import ZoneInfo

    signup(api_client, HOST_A)
    user = ClientProfile.objects.get(user__email="awa@example.com").user

    brazza = ZoneInfo("Africa/Brazzaville")
    today = datetime.now(brazza).date()
    ahead = (0 - today.weekday()) % 7 or 7
    day: date = today + timedelta(days=ahead + 7)
    starts_at = datetime.combine(day, time(10, 0), tzinfo=brazza)

    created = api_client.post(
        "/api/v1/public/bookings",
        {
            "service": str(salon_a.service.id),
            "starts_at": starts_at.isoformat(),
            "full_name": "Awa Diallo",
            "phone": "+242066112233",
            "accepts_policy": True,
        },
        format="json",
        headers=HOST_A,
    )
    assert created.status_code == 201, created.data

    assert ClientSalonLink.objects.filter(user=user, tenant=salon_a.tenant).exists()

    history = api_client.get("/api/v1/public/client/bookings", headers=HOST_A)
    assert len(history.data["bookings"]) == 1


# ---------------------------------------------------------------------------
# Frontieres entre les deux natures de compte
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_salon_owner_cannot_open_the_client_space(api_client, salon_a):
    """Il n'a pas de profil cliente : l'espace n'aurait aucun sens pour lui."""
    api_client.login(email=salon_a.owner.email, password=PASSWORD)

    response = api_client.get("/api/v1/public/client/bookings", headers=HOST_A)

    assert response.status_code == 403


@pytest.mark.django_db
def test_a_client_cannot_reach_the_salon_dashboard(api_client, salon_a):
    """Le pendant : un compte cliente n'ouvre aucune porte cote salon."""
    signup(api_client, HOST_A)

    for route in ("/api/v1/bookings/", "/api/v1/customers/", "/api/v1/services/"):
        response = api_client.get(route, headers=HOST_A)
        assert response.status_code == 403, f"{route} a repondu {response.status_code}"


@pytest.mark.django_db
def test_an_anonymous_visitor_gets_nothing(api_client, salon_a):
    response = api_client.get("/api/v1/public/client/bookings", headers=HOST_A)

    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_the_session_route_says_which_kind_of_account_is_connected(api_client, salon_a):
    """Le navigateur doit savoir ou envoyer la personne apres connexion."""
    signup(api_client, HOST_A)
    as_client = api_client.get("/api/v1/public/client/session", headers=HOST_A)

    api_client.logout()
    api_client.login(email=salon_a.owner.email, password=PASSWORD)
    as_owner = api_client.get("/api/v1/public/client/session", headers=HOST_A)

    assert as_client.data["is_client"] is True
    assert as_client.data["is_staff_member"] is False
    assert as_owner.data["is_client"] is False
    assert as_owner.data["is_staff_member"] is True


# ---------------------------------------------------------------------------
# Reglages du compte
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_she_can_change_her_preferred_salon(api_client, salon_a, salon_b):
    signup(api_client, HOST_A)

    response = api_client.patch(
        "/api/v1/public/client/me",
        {"preferred_salon": str(salon_b.tenant.id)},
        format="json",
        headers=HOST_A,
    )

    assert response.status_code == 200
    assert response.data["preferred_salon_slug"] == salon_b.tenant.slug


@pytest.mark.django_db
def test_she_can_correct_her_name_and_contact_details(api_client, salon_a):
    signup(api_client, HOST_A)

    response = api_client.patch(
        "/api/v1/public/client/me",
        {"full_name": "Awa D.", "whatsapp": "+242066000000"},
        format="json",
        headers=HOST_A,
    )

    assert response.status_code == 200
    assert response.data["full_name"] == "Awa D."
    assert response.data["whatsapp"] == "+242066000000"


@pytest.mark.django_db
def test_she_cannot_promote_herself_into_a_salon(api_client, salon_a):
    """Une mise a jour de profil ne doit pas pouvoir creer d'appartenance."""
    signup(api_client, HOST_A)
    user = ClientProfile.objects.get(user__email="awa@example.com").user

    api_client.patch(
        "/api/v1/public/client/me",
        {"is_staff": True, "is_platform_admin": True},
        format="json",
        headers=HOST_A,
    )

    user.refresh_from_db()
    assert user.is_staff is False
    assert user.is_platform_admin is False
    assert not Membership.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_a_team_member_who_is_also_a_client_keeps_both_hats(api_client, salon_a, salon_b):
    """Une gerante du salon A peut etre cliente du salon B.

    Les deux natures coexistent sur le meme compte : ce qui les distingue
    est ce que la personne possede, pas un type fige.
    """
    person = UserFactory()
    MembershipFactory(tenant=salon_a.tenant, user=person, role=Membership.Role.MANAGER)
    ClientProfile.objects.create(user=person, preferred_salon=salon_b.tenant)

    api_client.login(email=person.email, password=PASSWORD)
    session = api_client.get("/api/v1/public/client/session", headers=HOST_A)

    assert session.data["is_client"] is True
    assert session.data["is_staff_member"] is True


@pytest.mark.django_db
def test_a_logged_in_client_can_still_book(api_client, salon_a):
    """Regression : la session ne doit pas empecher de reserver.

    Envoyer le cookie de session avec les appels publics a une consequence
    qu'on decouvre a l'usage : Django n'exempte de CSRF que les requetes
    *anonymes*. Des qu'une session est presente, une ecriture sans jeton est
    rejetee - et la reservation, le geste central du produit, echouait pour
    les seules clientes connectees.
    """
    from datetime import date, datetime, time
    from zoneinfo import ZoneInfo

    signup(api_client, HOST_A)

    brazza = ZoneInfo("Africa/Brazzaville")
    today = datetime.now(brazza).date()
    ahead = (0 - today.weekday()) % 7 or 7
    day: date = today + timedelta(days=ahead + 7)
    starts_at = datetime.combine(day, time(10, 0), tzinfo=brazza)

    response = api_client.post(
        "/api/v1/public/bookings",
        {
            "service": str(salon_a.service.id),
            "starts_at": starts_at.isoformat(),
            "full_name": "Awa Diallo",
            "phone": "+242066112233",
            "accepts_policy": True,
        },
        format="json",
        headers=HOST_A,
    )

    assert response.status_code == 201, response.data


@pytest.mark.django_db
def test_an_anonymous_visitor_can_still_book_without_any_token(api_client, salon_a):
    """Le pendant : la reservation sans compte reste ouverte a tous.

    C'est le parcours majoritaire, et il ne doit rien exiger de plus qu'avant.
    """
    from datetime import date, datetime, time
    from zoneinfo import ZoneInfo

    brazza = ZoneInfo("Africa/Brazzaville")
    today = datetime.now(brazza).date()
    ahead = (0 - today.weekday()) % 7 or 7
    day: date = today + timedelta(days=ahead + 7)
    starts_at = datetime.combine(day, time(11, 0), tzinfo=brazza)

    response = api_client.post(
        "/api/v1/public/bookings",
        {
            "service": str(salon_a.service.id),
            "starts_at": starts_at.isoformat(),
            "full_name": "Sans Compte",
            "phone": "+242066777888",
            "accepts_policy": True,
        },
        format="json",
        headers=HOST_A,
    )

    assert response.status_code == 201, response.data


@pytest.mark.django_db
def test_every_booking_carries_a_link_to_its_own_status_page(api_client, salon_a):
    """Le chemin de retour, depuis l'espace vers le detail d'un rendez-vous.

    Une cliente qui ferme la page de reglement doit pouvoir revenir : sans ce
    jeton, l'espace montre une carte resumee et rien qui mene au detail - ni
    au montant reellement encaisse, ni au QR d'arrivee, ni au motif d'un
    refus de versement.

    Il est emis pour **tous** les rendez-vous, y compris passes : c'est la
    page qu'on rouvre pour retrouver ce qu'on a paye.
    """
    signup(api_client, HOST_A)
    user = ClientProfile.objects.get(user__email="awa@example.com").user

    make_booking(salon_a, salon_a.customer, service_name="Box braids")
    ClientSalonLink.objects.create(
        user=user, tenant=salon_a.tenant, customer_id=salon_a.customer.id
    )

    response = api_client.get("/api/v1/public/client/bookings", headers=HOST_A)

    rows = response.data["bookings"]
    assert rows
    for row in rows:
        assert row["status_token"], f"{row['service_name']} n'a pas de lien de suivi"

    # Et ce jeton ouvre bien la page de suivi du bon rendez-vous.
    detail = api_client.get(
        f"/api/v1/public/booking-status?token={rows[0]['status_token']}",
        headers=HOST_A,
    )
    assert detail.status_code == 200
    assert detail.data["booking"]["service_name"] == rows[0]["service_name"]


# ---------------------------------------------------------------------------
# Un acompte dont le delai est passe
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_an_expired_deposit_stops_asking_to_be_paid(api_client, salon_a):
    """Le defaut vu a l'ecran : « Un acompte reste a regler », et le bouton
    menait a « le delai est depasse ».

    Les deux ecrans disaient vrai chacun de son cote. L'espace cliente lisait
    le statut en base - toujours « en attente de paiement », faute de
    balayage Celery - pendant que la page de reglement recalculait
    l'echeance a la seconde. On invitait quelqu'un a payer, puis on lui
    fermait la porte.
    """
    from apps.payments.services import MOTIF_EXPIRATION, PAYMENT_WINDOW

    signup(api_client, HOST_A)
    user = ClientProfile.objects.get(user__email="awa@example.com").user

    debut = timezone.now() + timedelta(days=3)
    with as_tenant(salon_a.tenant):
        reservation = Booking.objects.create(
            tenant=salon_a.tenant,
            customer=salon_a.customer,
            staff_member=salon_a.staff,
            service=salon_a.service,
            starts_at=debut,
            ends_at=debut + timedelta(hours=2),
            status=Booking.Status.PENDING_PAYMENT,
            service_name="Box braids",
            total_amount=Decimal("450"),
            deposit_amount=Decimal("150"),
        )
        # `created_at` est pose automatiquement : on le recule par `update`.
        Booking.objects.filter(id=reservation.id).update(
            created_at=timezone.now() - PAYMENT_WINDOW - timedelta(minutes=1)
        )

    ClientSalonLink.objects.create(
        user=user, tenant=salon_a.tenant, customer_id=salon_a.customer.id
    )

    response = api_client.get("/api/v1/public/client/bookings", headers=HOST_A)

    assert response.status_code == 200
    ligne = next(
        row for row in response.data["bookings"] if row["id"] == str(reservation.id)
    )
    assert ligne["status"] == Booking.Status.CANCELLED
    # Plus aucun chemin vers le paiement : c'est le bouton de la capture.
    assert ligne["payment_token"] == ""
    # Et le motif, pour ne pas laisser chercher ce qui s'est passe.
    assert ligne["cancellation_reason"] == MOTIF_EXPIRATION

    with as_tenant(salon_a.tenant):
        reservation.refresh_from_db()
    assert reservation.status == Booking.Status.CANCELLED


@pytest.mark.django_db
def test_a_deposit_still_within_its_window_keeps_its_button(api_client, salon_a):
    """Le garde-fou : la lecture n'annule que ce qui est deja echu."""
    signup(api_client, HOST_A)
    user = ClientProfile.objects.get(user__email="awa@example.com").user

    debut = timezone.now() + timedelta(days=3)
    with as_tenant(salon_a.tenant):
        reservation = Booking.objects.create(
            tenant=salon_a.tenant,
            customer=salon_a.customer,
            staff_member=salon_a.staff,
            service=salon_a.service,
            starts_at=debut,
            ends_at=debut + timedelta(hours=2),
            status=Booking.Status.PENDING_PAYMENT,
            service_name="Box braids",
            total_amount=Decimal("450"),
            deposit_amount=Decimal("150"),
        )

    ClientSalonLink.objects.create(
        user=user, tenant=salon_a.tenant, customer_id=salon_a.customer.id
    )

    response = api_client.get("/api/v1/public/client/bookings", headers=HOST_A)

    ligne = next(
        row for row in response.data["bookings"] if row["id"] == str(reservation.id)
    )
    assert ligne["status"] == Booking.Status.PENDING_PAYMENT
    assert ligne["payment_token"] != ""
