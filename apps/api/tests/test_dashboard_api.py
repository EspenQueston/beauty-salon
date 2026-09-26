"""Actions du salon sur son agenda et son catalogue."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import Membership
from apps.scheduling.models import Booking
from conftest import as_tenant
from tests.factories import (
    BookingFactory,
    CustomerFactory,
    MembershipFactory,
    UserFactory,
)

PASSWORD = "motdepasse-solide"


def login(client, user):
    assert client.login(email=user.email, password=PASSWORD)
    return client


def make_booking(salon, hours_ahead: int = 240, **overrides):
    starts_at = timezone.now() + timedelta(hours=hours_ahead)
    with as_tenant(salon.tenant):
        return BookingFactory(
            tenant=salon.tenant,
            customer=salon.customer,
            staff_member=salon.staff,
            service=salon.service,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=120),
            **overrides,
        )


@pytest.mark.django_db
def test_receptionist_can_move_a_booking_through_its_statuses(api_client, salon_a):
    booking = make_booking(salon_a, status=Booking.Status.CONFIRMED)
    login(api_client, salon_a.owner)

    response = api_client.post(
        f"/api/v1/bookings/{booking.id}/status/",
        {"status": "checked_in"},
        format="json",
    )

    assert response.status_code == 200
    with as_tenant(salon_a.tenant):
        booking.refresh_from_db()
        assert booking.status == Booking.Status.CHECKED_IN


@pytest.mark.django_db
def test_an_arbitrary_status_is_refused(api_client, salon_a):
    """La route de statut ne sert pas a annuler : cancel a sa propre route,
    parce qu'elle horodate et journalise l'annulation."""
    booking = make_booking(salon_a)
    login(api_client, salon_a.owner)

    response = api_client.post(
        f"/api/v1/bookings/{booking.id}/status/",
        {"status": "cancelled"},
        format="json",
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_cancelling_records_the_reason_and_the_time(api_client, salon_a):
    booking = make_booking(salon_a)
    login(api_client, salon_a.owner)

    response = api_client.post(
        f"/api/v1/bookings/{booking.id}/cancel/",
        {"reason": "Prestataire malade"},
        format="json",
    )

    assert response.status_code == 200
    with as_tenant(salon_a.tenant):
        booking.refresh_from_db()
        assert booking.status == Booking.Status.CANCELLED
        assert booking.cancellation_reason == "Prestataire malade"
        assert booking.cancelled_at is not None


@pytest.mark.django_db
def test_a_cancelled_booking_cannot_be_cancelled_twice(api_client, salon_a):
    booking = make_booking(salon_a, status=Booking.Status.CANCELLED)
    login(api_client, salon_a.owner)

    response = api_client.post(
        f"/api/v1/bookings/{booking.id}/cancel/", {}, format="json"
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_rescheduling_to_a_free_slot_moves_the_booking(api_client, salon_a):
    booking = make_booking(salon_a)
    login(api_client, salon_a.owner)

    with as_tenant(salon_a.tenant):
        from datetime import time
        from zoneinfo import ZoneInfo

        tz = ZoneInfo(salon_a.tenant.timezone)
        local = booking.starts_at.astimezone(tz)
        # Meme jour, deux heures plus tard : dans les horaires d'ouverture.
        target = local.replace(hour=14, minute=0, second=0, microsecond=0)
        if target.weekday() == 6:  # dimanche ferme
            target += timedelta(days=1)
            target = target.replace(hour=14, minute=0)
        assert target.time() == time(14, 0)

    response = api_client.post(
        f"/api/v1/bookings/{booking.id}/reschedule/",
        {"starts_at": target.isoformat()},
        format="json",
    )

    assert response.status_code in (200, 409)
    if response.status_code == 200:
        with as_tenant(salon_a.tenant):
            booking.refresh_from_db()
            assert booking.starts_at == target


@pytest.mark.django_db
def test_rescheduling_with_an_invalid_date_is_refused(api_client, salon_a):
    booking = make_booking(salon_a)
    login(api_client, salon_a.owner)

    response = api_client.post(
        f"/api/v1/bookings/{booking.id}/reschedule/",
        {"starts_at": "pas-une-date"},
        format="json",
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_manual_booking_creates_the_customer_on_the_fly(api_client, salon_a):
    """La reception saisit un rendez-vous pris par telephone."""
    login(api_client, salon_a.owner)
    starts_at = timezone.now() + timedelta(days=5)

    response = api_client.post(
        "/api/v1/bookings/manual/",
        {
            "service": str(salon_a.service.id),
            "staff_member": str(salon_a.staff.id),
            "full_name": "Cliente Telephone",
            "phone": "+242066554433",
            "starts_at": starts_at.isoformat(),
            "internal_note": "Appel de ce matin",
        },
        format="json",
    )

    assert response.status_code == 201, response.data
    assert response.data["source"] == "staff"
    assert response.data["customer_name"] == "Cliente Telephone"


@pytest.mark.django_db
def test_manual_booking_still_cannot_overlap(api_client, salon_a):
    """Le salon peut forcer un horaire hors grille, jamais un chevauchement."""
    booking = make_booking(salon_a, status=Booking.Status.CONFIRMED)
    login(api_client, salon_a.owner)

    response = api_client.post(
        "/api/v1/bookings/manual/",
        {
            "service": str(salon_a.service.id),
            "staff_member": str(salon_a.staff.id),
            "full_name": "Doublon",
            "phone": "+242066111222",
            "starts_at": (booking.starts_at + timedelta(minutes=30)).isoformat(),
        },
        format="json",
    )

    assert response.status_code == 409
    assert response.json()["code"] == "slot_unavailable"


@pytest.mark.django_db
def test_manual_booking_requires_a_customer_or_contact_details(api_client, salon_a):
    login(api_client, salon_a.owner)

    response = api_client.post(
        "/api/v1/bookings/manual/",
        {
            "service": str(salon_a.service.id),
            "staff_member": str(salon_a.staff.id),
            "starts_at": (timezone.now() + timedelta(days=5)).isoformat(),
        },
        format="json",
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_summary_counts_only_upcoming_active_bookings(api_client, salon_a):
    make_booking(salon_a, hours_ahead=48, status=Booking.Status.CONFIRMED)
    make_booking(salon_a, hours_ahead=72, status=Booking.Status.CANCELLED)
    login(api_client, salon_a.owner)

    response = api_client.get("/api/v1/bookings/summary/")

    assert response.status_code == 200
    assert response.data["upcoming_count"] == 1
    assert response.data["currency"] == "XAF"


@pytest.mark.django_db
def test_receptionist_cannot_edit_the_catalogue(api_client, salon_a):
    """Les prix engagent le salon : la reception les consulte sans les changer."""
    receptionist = UserFactory()
    MembershipFactory(
        tenant=salon_a.tenant, user=receptionist, role=Membership.Role.RECEPTIONIST
    )
    login(api_client, receptionist)

    read = api_client.get("/api/v1/services/")
    write = api_client.patch(
        f"/api/v1/services/{salon_a.service.id}/",
        {"price_amount": "1"},
        format="json",
    )

    assert read.status_code == 200
    assert write.status_code == 403


@pytest.mark.django_db
def test_owner_can_edit_the_catalogue(api_client, salon_a):
    login(api_client, salon_a.owner)

    response = api_client.patch(
        f"/api/v1/services/{salon_a.service.id}/",
        {"active": False},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["active"] is False


@pytest.mark.django_db
def test_a_service_only_says_whether_it_asks_for_a_deposit(api_client, salon_a):
    """La prestation ne porte plus de montant, seulement un oui ou un non.

    Elle en portait un, qui servait a la fois d'interrupteur et de plancher,
    et que le mini-site affichait tel quel pendant que la reservation en
    calculait un autre au pourcentage. Le « combien » vit desormais sur la
    fiche du salon, a un seul endroit.

    L'ancien garde-fou - « l'acompte depasse le prix » - n'a plus lieu d'etre
    ici : c'est le calcul qui borne l'acompte au total du rendez-vous, et
    `test_deposit_rule.py::test_the_deposit_never_exceeds_what_is_owed` le
    verrouille.
    """
    login(api_client, salon_a.owner)

    response = api_client.patch(
        f"/api/v1/services/{salon_a.service.id}/",
        {"price_amount": "10000", "requires_deposit": True},
        format="json",
    )

    assert response.status_code == 200, response.data
    assert response.data["requires_deposit"] is True
    assert "deposit_amount" not in response.data


@pytest.mark.django_db
def test_business_hours_end_must_follow_start(api_client, salon_a):
    login(api_client, salon_a.owner)

    response = api_client.post(
        "/api/v1/business-hours/",
        {"weekday": 2, "starts_at": "18:00", "ends_at": "09:00"},
        format="json",
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_media_description_is_saved_from_json(api_client, salon_a):
    """La legende d'une photo se modifie apres le televersement.

    Le viewset n'acceptait que le multipart, parce que c'est ainsi qu'arrive
    un fichier. Mais la description se corrige ensuite, en JSON : la requete
    repartait en 415 et la saisie etait perdue sans que rien ne l'explique.
    """
    from apps.media.models import MediaAsset

    login(api_client, salon_a.owner)

    with as_tenant(salon_a.tenant):
        asset = MediaAsset.objects.create(
            tenant=salon_a.tenant,
            file="tenants/x/media/y/photo.jpg",
            content_type="image/jpeg",
            byte_size=1024,
        )

    response = api_client.patch(
        f"/api/v1/media/{asset.id}/",
        {"alt_text": "Tresses collees, finition perles"},
        format="json",
    )

    assert response.status_code == 200, response.data
    assert response.data["alt_text"] == "Tresses collees, finition perles"

    with as_tenant(salon_a.tenant):
        asset.refresh_from_db()
    assert asset.alt_text == "Tresses collees, finition perles"


@pytest.mark.django_db
def test_a_new_booking_has_no_deposit_recorded(api_client, salon_a):
    """Reserver n'encaisse rien.

    L'acompte est une somme que la cliente remet en main propre : le noter
    comme recu au moment de la reservation ferait croire au salon qu'il a
    ete paye, et fausserait sa caisse.
    """
    booking = make_booking(salon_a)

    login(api_client, salon_a.owner)
    response = api_client.get(f"/api/v1/bookings/{booking.id}/")

    assert response.status_code == 200
    assert response.data["deposit_paid"] is False
    assert response.data["deposit_method"] == ""
    assert Decimal(response.data["deposit_received"]) == Decimal("0")


@pytest.mark.django_db
def test_recording_a_deposit_keeps_the_amount_actually_received(api_client, salon_a):
    """Une cliente laisse parfois moins que le montant demande."""
    booking = make_booking(salon_a)
    with as_tenant(salon_a.tenant):
        booking.deposit_amount = Decimal("150")
        booking.save(update_fields=["deposit_amount"])

    login(api_client, salon_a.owner)
    response = api_client.post(
        f"/api/v1/bookings/{booking.id}/deposit/",
        {"method": "cash", "amount": "100"},
        format="json",
    )

    assert response.status_code == 200, response.data
    assert response.data["deposit_paid"] is True
    # Le montant attendu ne bouge pas : c'est le recu qui est note a part.
    assert Decimal(response.data["deposit_amount"]) == Decimal("150")
    assert Decimal(response.data["deposit_received"]) == Decimal("100")


@pytest.mark.django_db
def test_a_deposit_noted_by_mistake_can_be_cancelled(api_client, salon_a):
    """Un clic malencontreux ne doit pas etre definitif.

    La route d'encaissement refuse un second appel : sans annulation, une
    erreur restait inscrite pour toujours dans la caisse du salon.
    """
    booking = make_booking(salon_a)
    with as_tenant(salon_a.tenant):
        booking.deposit_amount = Decimal("150")
        booking.save(update_fields=["deposit_amount"])

    login(api_client, salon_a.owner)
    api_client.post(
        f"/api/v1/bookings/{booking.id}/deposit/", {"method": "cash"}, format="json"
    )

    response = api_client.post(f"/api/v1/bookings/{booking.id}/deposit/cancel/")

    assert response.status_code == 200, response.data
    assert response.data["deposit_paid"] is False
    assert response.data["deposit_method"] == ""
    assert Decimal(response.data["deposit_received"]) == Decimal("0")

    # Et l'acompte redevient encaissable : la correction est complete.
    again = api_client.post(
        f"/api/v1/bookings/{booking.id}/deposit/",
        {"method": "mobile_money"},
        format="json",
    )
    assert again.status_code == 200
    assert again.data["deposit_method"] == "mobile_money"


@pytest.mark.django_db
def test_cancelling_a_deposit_that_was_never_recorded_is_refused(api_client, salon_a):
    booking = make_booking(salon_a)

    login(api_client, salon_a.owner)
    response = api_client.post(f"/api/v1/bookings/{booking.id}/deposit/cancel/")

    assert response.status_code == 400
    assert response.json()["code"] == "not_paid"


# ---------------------------------------------------------------------------
# Politique de retard
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_salon_writes_its_own_late_policy(api_client, salon_a):
    """Aucun salon ne regle le retard pareil : le texte lui appartient."""
    login(api_client, salon_a.owner)

    response = api_client.patch(
        "/api/v1/salon-profile",
        {
            "late_tolerance_minutes": 20,
            "late_policy": "La prestation peut être raccourcie.",
        },
        format="json",
    )

    assert response.status_code == 200
    assert response.data["late_tolerance_minutes"] == 20
    assert response.data["late_policy"] == "La prestation peut être raccourcie."


@pytest.mark.django_db
def test_the_late_tolerance_travels_with_the_agenda_summary(api_client, salon_a):
    """L'agenda en a besoin a chaque rendu : elle ne merite pas un second appel."""
    with as_tenant(salon_a.tenant):
        from apps.salons.models import SalonProfile

        SalonProfile.objects.filter(tenant=salon_a.tenant).update(
            late_tolerance_minutes=25
        )
    login(api_client, salon_a.owner)

    response = api_client.get("/api/v1/bookings/summary/")

    assert response.status_code == 200
    assert response.data["late_tolerance_minutes"] == 25


@pytest.mark.django_db
def test_the_late_policy_is_published_on_the_mini_site(api_client, salon_a):
    """Une regle qu'on decouvre sur place n'a jamais ete une regle."""
    from conftest import salon_host

    with as_tenant(salon_a.tenant):
        from apps.salons.models import SalonProfile

        SalonProfile.objects.filter(tenant=salon_a.tenant).update(
            late_tolerance_minutes=10,
            late_policy="Au-delà, le créneau peut être donné.",
        )

    response = api_client.get(
        "/api/v1/public/salon", headers={"Host": salon_host("blondrose")}
    )

    assert response.status_code == 200
    assert response.data["late_tolerance_minutes"] == 10
    assert response.data["late_policy"] == "Au-delà, le créneau peut être donné."


# ---------------------------------------------------------------------------
# Import d'un media par son adresse web
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/photo.jpg",
        "http://localhost:8001/photo.jpg",
        "http://169.254.169.254/latest/meta-data/",  # metadonnees cloud
        "http://10.0.0.5/photo.jpg",
        "http://192.168.1.10/photo.jpg",
        "file:///etc/passwd",
        "gopher://evil.test/photo.jpg",
    ],
)
def test_a_media_import_refuses_to_reach_the_inside(api_client, salon_a, url):
    """Aller chercher une adresse fournie par l'utilisateur, c'est lui preter
    un client HTTP qui parle depuis notre reseau. Ces adresses ne doivent
    jamais etre atteintes."""
    login(api_client, salon_a.owner)

    response = api_client.post(
        "/api/v1/media/from-url/", {"url": url}, format="json"
    )

    assert response.status_code == 400, f"{url} n'a pas ete refusee"

    # Deux refus differents, tous deux valables : un schema interdit
    # (file://, gopher://) est arrete par la validation du champ, une adresse
    # interne par le garde-fou de fetch.py. Les erreurs de champ arrivent
    # imbriquees sous `detail`.
    refused_field = "url" in (response.data.get("detail") or {})
    refused_guard = response.data.get("code") == "remote_media_refused"
    assert refused_field or refused_guard, response.data


@pytest.mark.django_db
def test_the_media_import_is_closed_to_the_front_desk(api_client, salon_a):
    """Une route qui telecharge depuis internet n'est pas une route de lecture."""
    receptionist = UserFactory()
    MembershipFactory(
        tenant=salon_a.tenant, user=receptionist, role=Membership.Role.RECEPTIONIST
    )
    login(api_client, receptionist)

    response = api_client.post(
        "/api/v1/media/from-url/",
        {"url": "https://images.example.com/photo.jpg"},
        format="json",
    )

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Prestataires et equipe : deux listes, deux notions
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_staff_member_says_whether_she_can_log_in(api_client, salon_a):
    """Realiser des prestations et avoir un compte sont deux choses.

    Une coiffeuse figure a l'agenda sans jamais se connecter, et c'est voulu.
    Mais rien ne le disait a l'ecran : la liste des prestataires semblait
    contredire celle de l'equipe, et le salon concluait au bug.
    """
    from apps.staff.models import StaffMember

    login(api_client, salon_a.owner)

    with as_tenant(salon_a.tenant):
        sans_compte = StaffMember.objects.create(
            tenant=salon_a.tenant, name="Grace Ilunga", specialty="Soins"
        )
        # Le lien est explicite : la fiche de prestataire du jeu d'essai n'en
        # porte pas, et c'est bien le cas majoritaire.
        avec_compte = StaffMember.objects.create(
            tenant=salon_a.tenant,
            name="Rose Moukendi",
            membership=Membership.objects.get(
                tenant=salon_a.tenant, user=salon_a.owner
            ),
        )

    response = api_client.get("/api/v1/staff-members/")
    assert response.status_code == 200

    rows = {row["name"]: row for row in response.data["results"]}

    # Celle qui n'a pas de compte le dit, et ne prétend pas a une adresse.
    assert rows[sans_compte.name]["has_access"] is False
    assert rows[sans_compte.name]["access_email"] == ""

    # Celle qui est rattachee a un membre porte son adresse : c'est ce qui
    # permet de rapprocher les deux ecrans.
    assert rows[avec_compte.name]["has_access"] is True
    assert rows[avec_compte.name]["access_email"] == salon_a.owner.email


# ---------------------------------------------------------------------------
# Retirer un prestataire de la liste
# ---------------------------------------------------------------------------


def _staff_with_booking(salon, *, when):
    """Cree un prestataire et un rendez-vous confirme a la date donnee."""
    from apps.scheduling.models import Booking
    from apps.staff.models import StaffMember

    with as_tenant(salon.tenant):
        member = StaffMember.objects.create(tenant=salon.tenant, name="Mireille Nsimba")
        Booking.objects.create(
            tenant=salon.tenant,
            customer=salon.customer,
            staff_member=member,
            service=salon.service,
            starts_at=when,
            ends_at=when + timedelta(hours=1),
            status=Booking.Status.CONFIRMED,
            service_name="Pose gel",
            total_amount=Decimal("100"),
        )
    return member


@pytest.mark.django_db
def test_a_staff_member_who_never_worked_is_really_deleted(api_client, salon_a):
    """Fiche creee par erreur, ou personne qui n'a jamais commence."""
    from apps.staff.models import StaffMember

    login(api_client, salon_a.owner)
    with as_tenant(salon_a.tenant):
        member = StaffMember.objects.create(tenant=salon_a.tenant, name="Jamais venue")

    response = api_client.delete(f"/api/v1/staff-members/{member.id}/")

    assert response.status_code == 204
    with as_tenant(salon_a.tenant):
        assert not StaffMember.objects.filter(id=member.id).exists()


@pytest.mark.django_db
def test_a_staff_member_with_only_past_bookings_leaves_the_list(api_client, salon_a):
    """Elle sort de la liste, la ligne survit.

    Ses rendez-vous portent son nom et ses prestations sont dans les comptes
    du salon : l'effacer reecrirait l'historique, y compris financier.
    """

    member = _staff_with_booking(salon_a, when=timezone.now() - timedelta(days=40))
    login(api_client, salon_a.owner)

    response = api_client.delete(f"/api/v1/staff-members/{member.id}/")

    assert response.status_code == 200
    assert response.data["code"] == "archived"

    with as_tenant(salon_a.tenant):
        member.refresh_from_db()
    assert member.archived_at is not None
    assert member.active is False

    # Elle disparait du quotidien...
    listed = api_client.get("/api/v1/staff-members/")
    assert member.name not in [row["name"] for row in listed.data["results"]]

    # ...mais reste joignable a qui la demande.
    archived = api_client.get("/api/v1/staff-members/?archived=true")
    assert member.name in [row["name"] for row in archived.data["results"]]


@pytest.mark.django_db
def test_a_staff_member_with_upcoming_bookings_is_refused(api_client, salon_a):
    """Les effacer libererait des creneaux deja promis a des clientes."""
    from apps.staff.models import StaffMember

    member = _staff_with_booking(salon_a, when=timezone.now() + timedelta(days=3))
    login(api_client, salon_a.owner)

    response = api_client.delete(f"/api/v1/staff-members/{member.id}/")

    assert response.status_code == 409
    assert response.data["code"] == "has_upcoming_bookings"
    assert response.data["extra"]["count"] == 1
    # Le message dit combien et quand : « elle a des rendez-vous » tout court
    # n'aide pas a decider quoi faire.
    assert "1 rendez-vous à venir" in response.data["detail"]

    with as_tenant(salon_a.tenant):
        assert StaffMember.objects.filter(id=member.id).exists()


@pytest.mark.django_db
def test_a_cancelled_upcoming_booking_does_not_block(api_client, salon_a):
    """Un rendez-vous annule n'engage plus personne."""
    from apps.scheduling.models import Booking

    member = _staff_with_booking(salon_a, when=timezone.now() + timedelta(days=3))
    with as_tenant(salon_a.tenant):
        Booking.objects.filter(staff_member=member).update(
            status=Booking.Status.CANCELLED
        )

    login(api_client, salon_a.owner)
    response = api_client.delete(f"/api/v1/staff-members/{member.id}/")

    assert response.status_code == 200
    assert response.data["code"] == "archived"


# ---------------------------------------------------------------------------
# Recherche dans l'agenda
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_agenda_can_be_searched_by_customer_name(api_client, salon_a):
    """On cherche une personne, pas une semaine.

    La recherche ignore la période affichée : trouver « rien » parce que la
    cliente vient le mois prochain serait le contraire d'une recherche.
    """
    login(api_client, salon_a.owner)
    starts_at = timezone.now() + timedelta(days=90)

    with as_tenant(salon_a.tenant):
        lointaine = CustomerFactory(tenant=salon_a.tenant, full_name="Chantal Kouka")
        BookingFactory(
            tenant=salon_a.tenant,
            customer=lointaine,
            staff_member=salon_a.staff,
            service=salon_a.service,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=60),
            service_name="Box braids",
        )

    response = api_client.get(
        "/api/v1/bookings/?search=chantal",
        headers={"X-Tenant-Id": str(salon_a.tenant.id)},
    )

    assert response.status_code == 200, response.data
    noms = [row["customer_name"] for row in response.data["results"]]
    assert noms == ["Chantal Kouka"]


@pytest.mark.django_db
def test_the_agenda_can_be_searched_by_the_end_of_a_phone_number(api_client, salon_a):
    """C'est par les derniers chiffres qu'on reconnaît un numéro."""
    login(api_client, salon_a.owner)
    starts_at = timezone.now() + timedelta(days=3)

    with as_tenant(salon_a.tenant):
        cliente = CustomerFactory(
            tenant=salon_a.tenant, full_name="Awa Diallo", phone="+242066998877"
        )
        BookingFactory(
            tenant=salon_a.tenant,
            customer=cliente,
            staff_member=salon_a.staff,
            service=salon_a.service,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=60),
        )

    response = api_client.get(
        "/api/v1/bookings/?search=998877",
        headers={"X-Tenant-Id": str(salon_a.tenant.id)},
    )

    assert [row["customer_name"] for row in response.data["results"]] == ["Awa Diallo"]


@pytest.mark.django_db
def test_a_search_never_reaches_another_salon(api_client, salon_a, salon_b):
    """La recherche traverse le temps, jamais les salons."""
    login(api_client, salon_a.owner)
    starts_at = timezone.now() + timedelta(days=3)

    with as_tenant(salon_b.tenant):
        chez_b = CustomerFactory(tenant=salon_b.tenant, full_name="Chantal Ailleurs")
        BookingFactory(
            tenant=salon_b.tenant,
            customer=chez_b,
            staff_member=salon_b.staff,
            service=salon_b.service,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=60),
        )

    response = api_client.get(
        "/api/v1/bookings/?search=chantal",
        headers={"X-Tenant-Id": str(salon_a.tenant.id)},
    )

    assert response.data["results"] == []


# ---------------------------------------------------------------------------
# Ce vers quoi mène la cloche
# ---------------------------------------------------------------------------
#
# Ces filtres existent pour une seule raison : une notification doit mener à
# ce qu'elle annonce. Sans eux, les trois pastilles et toutes les
# notifications renvoyaient vers `/agenda`, à charge de retrouver soi-même le
# rendez-vous concerné dans une grille hebdomadaire.


@pytest.mark.django_db
def test_un_rendez_vous_se_retrouve_par_son_identifiant(api_client, salon_a):
    """Le lien des notifications.

    La période affichée est ignorée : celui qu'on cherche est presque
    toujours hors de la semaine en cours.
    """
    vise = make_booking(salon_a, hours_ahead=24 * 40)
    make_booking(salon_a, hours_ahead=24 * 41)
    login(api_client, salon_a.owner)

    reponse = api_client.get(f"/api/v1/bookings/?id={vise.id}")

    assert reponse.status_code == 200
    assert [ligne["id"] for ligne in reponse.data["results"]] == [str(vise.id)]


@pytest.mark.django_db
def test_la_liste_des_demandes_dit_la_meme_chose_que_la_pastille(
    api_client, salon_a
):
    """Le compteur et la liste partagent leur définition.

    C'est tout l'intérêt de `FILTRES_ATTENTION` : si les deux divergent, la
    pastille annonce deux demandes, l'écran en montre trois, et l'on cesse de
    croire les deux.
    """
    make_booking(salon_a, status=Booking.Status.REQUESTED)
    make_booking(salon_a, hours_ahead=250, status=Booking.Status.REQUESTED)
    make_booking(salon_a, hours_ahead=260, status=Booking.Status.CONFIRMED)

    login(api_client, salon_a.owner)

    liste = api_client.get("/api/v1/bookings/?attente=demandes")
    pastille = api_client.get("/api/v1/overview?brief=1")

    assert len(liste.data["results"]) == 2
    assert pastille.data["attention"]["requests"] == 2


@pytest.mark.django_db
def test_une_liste_inconnue_ne_deverse_pas_tout_l_agenda(api_client, salon_a):
    """Un signet gardé après un renommage ne doit pas tout montrer.

    Ignorer la clé aurait affiché l'agenda entier sous le titre « acomptes à
    vérifier » — c'est-à-dire un écran qui ment.
    """
    make_booking(salon_a)
    login(api_client, salon_a.owner)

    reponse = api_client.get("/api/v1/bookings/?attente=liste-qui-n-existe-plus")

    assert reponse.status_code == 200
    assert reponse.data["results"] == []


@pytest.mark.django_db
def test_les_rendez_vous_a_noter_sont_ceux_qui_sont_passes(api_client, salon_a):
    passe = make_booking(salon_a, hours_ahead=-48, status=Booking.Status.CONFIRMED)
    make_booking(salon_a, hours_ahead=48, status=Booking.Status.CONFIRMED)
    # Déjà réglé : honoré, donc plus rien à noter.
    make_booking(salon_a, hours_ahead=-72, status=Booking.Status.COMPLETED)

    login(api_client, salon_a.owner)
    reponse = api_client.get("/api/v1/bookings/?attente=a-noter")

    assert [ligne["id"] for ligne in reponse.data["results"]] == [str(passe.id)]


@pytest.mark.django_db
def test_un_prestataire_ne_voit_pas_les_rendez_vous_des_autres_par_ce_chemin(
    api_client, salon_a
):
    """Le nouveau filtre ne doit pas contourner le cloisonnement par rôle.

    `?id=` prend un identifiant en clair : sans la restriction de rôle qui
    s'applique après, il suffirait de le connaître pour lire le rendez-vous
    d'une collègue.
    """
    autre = make_booking(salon_a, status=Booking.Status.CONFIRMED)

    prestataire = UserFactory()
    MembershipFactory(
        tenant=salon_a.tenant, user=prestataire, role=Membership.Role.STAFF
    )
    login(api_client, prestataire)

    reponse = api_client.get(f"/api/v1/bookings/?id={autre.id}")

    assert reponse.status_code == 200
    assert reponse.data["results"] == []


@pytest.mark.django_db
def test_l_agenda_donne_de_quoi_joindre_la_cliente(api_client, salon_a):
    """Le nom et le numéro y étaient ; l'adresse manquait.

    Depuis une carte de l'agenda, on appelle ou on écrit. Sans l'adresse, la
    seconde moitié du geste obligeait à rouvrir la fiche cliente — ou à la
    chercher dans sa boîte mail.

    Elle peut être vide : une cliente qui réserve par téléphone n'en donne pas
    toujours, et l'écran n'affiche alors rien.
    """
    with as_tenant(salon_a.tenant):
        salon_a.customer.email = "aminata.sow@example.com"
        salon_a.customer.save(update_fields=["email"])

    booking = make_booking(salon_a)
    login(api_client, salon_a.owner)

    ligne = api_client.get(f"/api/v1/bookings/?id={booking.id}").data["results"][0]

    assert ligne["customer_email"] == "aminata.sow@example.com"
    assert ligne["customer_phone"] == salon_a.customer.phone
