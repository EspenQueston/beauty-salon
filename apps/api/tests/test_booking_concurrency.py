"""Deux clientes, un seul creneau.

Ces tests tournent en mode `transaction=True` : chaque thread ouvre sa propre
connexion PostgreSQL, comme deux requetes HTTP simultanees. Sans cela on
testerait deux ecritures dans la meme transaction, ce qui ne prouve rien.
"""

import threading
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.db import IntegrityError, OperationalError, connection

from apps.common.db import tenant_context
from apps.common.exceptions import SlotUnavailable
from apps.scheduling.models import Booking
from apps.scheduling.services.booking import CustomerDetails, create_booking
from conftest import as_tenant

BRAZZAVILLE = ZoneInfo("Africa/Brazzaville")


def next_monday_at(hour: int) -> datetime:
    """Un lundi a venir : la reservation reelle refuse le passe."""
    today = datetime.now(UTC).date()
    ahead = (7 - today.weekday()) % 7 or 7
    day: date = today + timedelta(days=ahead + 7)
    return datetime.combine(day, time(hour, 0), tzinfo=BRAZZAVILLE)


def _insert_directly(tenant_id, payload, results, index, barrier):
    """Insere une reservation depuis un thread, connexion dediee."""
    try:
        with tenant_context(tenant_id):
            # Les deux threads sont maintenant dans une transaction ouverte.
            barrier.wait(timeout=10)
            Booking.objects.create(**payload)
        results[index] = "ok"
    except IntegrityError:
        results[index] = "conflit"
    except OperationalError as exc:
        # Un interblocage est l'autre facon dont PostgreSQL refuse le second
        # inserant : la verification de la contrainte d'exclusion prend des
        # verrous, et quand les deux transactions les prennent en sens
        # inverse, il en tue une. C'est le meme evenement metier - quelqu'un
        # a perdu la course - et le service le traite comme tel.
        if getattr(exc.__cause__, "sqlstate", None) == "40P01":
            results[index] = "conflit"
        else:
            results[index] = f"erreur: {exc!r}"
    except Exception as exc:  # noqa: BLE001 - remonte tel quel dans l'assertion
        results[index] = f"erreur: {exc!r}"
    finally:
        connection.close()


@pytest.mark.django_db(transaction=True)
def test_two_simultaneous_bookings_only_one_wins(salon_a):
    """Le cas que la contrainte d'exclusion existe pour attraper."""
    starts_at = next_monday_at(10)
    payload = {
        "tenant_id": salon_a.tenant.id,
        "customer_id": salon_a.customer.id,
        "staff_member_id": salon_a.staff.id,
        "service_id": salon_a.service.id,
        "starts_at": starts_at,
        "ends_at": starts_at + timedelta(minutes=120),
        "status": Booking.Status.CONFIRMED,
        "service_name": salon_a.service.name,
    }

    results: dict[int, str] = {}
    barrier = threading.Barrier(2)
    threads = [
        threading.Thread(
            target=_insert_directly,
            args=(salon_a.tenant.id, dict(payload), results, index, barrier),
        )
        for index in range(2)
    ]

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    # Un `join` avec delai rend la main meme si le thread n'a pas fini. Sans
    # ce controle, une machine chargee produisait « Resultats inattendus :
    # {0: 'ok'} » - un message qui accuse la contrainte d'exclusion alors que
    # le seul coupable est le thread qui n'a jamais repondu.
    assert len(results) == 2, (
        f"Un thread n'a pas rendu de resultat en 20 s (obtenu : {results}). "
        "C'est un probleme d'environnement, pas de verrouillage."
    )

    # Un thread qui n'a pas pu parler a la base n'a rien prouve ni infirme :
    # on le distingue d'un vrai defaut de verrouillage plutot que de le
    # laisser echouer sur la comparaison de liste, ou il ressemblait a une
    # contrainte d'exclusion defaillante.
    broken = [value for value in results.values() if value.startswith("erreur:")]
    assert not broken, (
        f"Un thread n'a pas atteint la base : {broken}. "
        "C'est un probleme d'environnement, pas de verrouillage."
    )

    outcomes = sorted(results.values())
    assert outcomes == ["conflit", "ok"], f"Resultats inattendus : {results}"

    # L'invariant, celui qui compte vraiment : une seule reservation tient.
    #
    # C'est PostgreSQL qui le garantit, par la contrainte d'exclusion sur
    # (tenant, prestataire, plage horaire). Les deux threads ne sont qu'une
    # facon de la mettre a l'epreuve.
    with as_tenant(salon_a.tenant):
        assert Booking.objects.filter(starts_at=starts_at).count() == 1


@pytest.mark.django_db(transaction=True)
def test_overlapping_booking_is_refused_even_if_it_starts_later(salon_a):
    """Un chevauchement partiel est un conflit, pas seulement un doublon."""
    starts_at = next_monday_at(10)

    with as_tenant(salon_a.tenant):
        Booking.objects.create(
            tenant=salon_a.tenant,
            customer=salon_a.customer,
            staff_member=salon_a.staff,
            service=salon_a.service,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=120),
            status=Booking.Status.CONFIRMED,
            service_name=salon_a.service.name,
        )

        with pytest.raises(IntegrityError):
            Booking.objects.create(
                tenant=salon_a.tenant,
                customer=salon_a.customer,
                staff_member=salon_a.staff,
                service=salon_a.service,
                starts_at=starts_at + timedelta(minutes=60),
                ends_at=starts_at + timedelta(minutes=180),
                status=Booking.Status.CONFIRMED,
                service_name=salon_a.service.name,
            )


@pytest.mark.django_db(transaction=True)
def test_back_to_back_bookings_are_allowed(salon_a):
    """10h-12h puis 12h-14h : consecutif, pas conflictuel."""
    starts_at = next_monday_at(10)

    with as_tenant(salon_a.tenant):
        for offset in (0, 120):
            Booking.objects.create(
                tenant=salon_a.tenant,
                customer=salon_a.customer,
                staff_member=salon_a.staff,
                service=salon_a.service,
                starts_at=starts_at + timedelta(minutes=offset),
                ends_at=starts_at + timedelta(minutes=offset + 120),
                status=Booking.Status.CONFIRMED,
                service_name=salon_a.service.name,
            )

        assert Booking.objects.count() == 2


@pytest.mark.django_db(transaction=True)
def test_cancelled_booking_no_longer_blocks_the_slot(salon_a):
    """La contrainte est partielle : un rendez-vous annule libere son creneau."""
    starts_at = next_monday_at(10)

    with as_tenant(salon_a.tenant):
        first = Booking.objects.create(
            tenant=salon_a.tenant,
            customer=salon_a.customer,
            staff_member=salon_a.staff,
            service=salon_a.service,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=120),
            status=Booking.Status.CONFIRMED,
            service_name=salon_a.service.name,
        )
        first.status = Booking.Status.CANCELLED
        first.save(update_fields=["status"])

        Booking.objects.create(
            tenant=salon_a.tenant,
            customer=salon_a.customer,
            staff_member=salon_a.staff,
            service=salon_a.service,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=120),
            status=Booking.Status.CONFIRMED,
            service_name=salon_a.service.name,
        )

        assert Booking.objects.filter(status=Booking.Status.CONFIRMED).count() == 1


@pytest.mark.django_db(transaction=True)
def test_two_staff_members_can_be_booked_at_the_same_time(salon_a):
    """La contrainte porte sur le prestataire, pas sur le salon."""
    from tests.factories import StaffMemberFactory, StaffServiceFactory

    starts_at = next_monday_at(10)

    with as_tenant(salon_a.tenant):
        second = StaffMemberFactory(tenant=salon_a.tenant, name="Grace")
        StaffServiceFactory(
            tenant=salon_a.tenant, staff_member=second, service=salon_a.service
        )

        for member in (salon_a.staff, second):
            Booking.objects.create(
                tenant=salon_a.tenant,
                customer=salon_a.customer,
                staff_member=member,
                service=salon_a.service,
                starts_at=starts_at,
                ends_at=starts_at + timedelta(minutes=120),
                status=Booking.Status.CONFIRMED,
                service_name=salon_a.service.name,
            )

        assert Booking.objects.count() == 2


@pytest.mark.django_db(transaction=True)
def test_service_refuses_a_taken_slot_with_alternatives(salon_a):
    """Le service metier repond 409 avec des creneaux de repli."""
    starts_at = next_monday_at(10)
    details = CustomerDetails(full_name="Awa", phone="+242010101")

    with as_tenant(salon_a.tenant):
        create_booking(
            tenant=salon_a.tenant,
            service=salon_a.service,
            staff_member=salon_a.staff,
            starts_at=starts_at,
            customer=details,
        )

        with pytest.raises(SlotUnavailable) as caught:
            create_booking(
                tenant=salon_a.tenant,
                service=salon_a.service,
                staff_member=salon_a.staff,
                starts_at=starts_at,
                customer=CustomerDetails(full_name="Mireille", phone="+242020202"),
            )

    assert caught.value.extra["alternatives"], "Un refus doit proposer autre chose."


@pytest.mark.django_db(transaction=True)
def test_same_idempotency_key_does_not_create_two_bookings(salon_a):
    """Un double clic, ou un reseau instable qui rejoue la requete."""
    starts_at = next_monday_at(10)
    details = CustomerDetails(full_name="Awa", phone="+242010101")

    with as_tenant(salon_a.tenant):
        first = create_booking(
            tenant=salon_a.tenant,
            service=salon_a.service,
            staff_member=salon_a.staff,
            starts_at=starts_at,
            customer=details,
            idempotency_key="cle-unique",
        )
        second = create_booking(
            tenant=salon_a.tenant,
            service=salon_a.service,
            staff_member=salon_a.staff,
            starts_at=starts_at,
            customer=details,
            idempotency_key="cle-unique",
        )

        assert first.id == second.id
        assert Booking.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_booking_a_service_the_staff_member_cannot_perform_is_refused(salon_a):
    from apps.scheduling.services.booking import BookingRefused
    from tests.factories import StaffMemberFactory

    starts_at = next_monday_at(10)

    with as_tenant(salon_a.tenant), pytest.raises(BookingRefused):
        outsider = StaffMemberFactory(tenant=salon_a.tenant, name="Sans competence")
        create_booking(
            tenant=salon_a.tenant,
            service=salon_a.service,
            staff_member=outsider,
            starts_at=starts_at,
            customer=CustomerDetails(full_name="Awa", phone="+242010101"),
        )
