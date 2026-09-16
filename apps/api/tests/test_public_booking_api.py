"""Le parcours public de reservation, vu depuis HTTP.

C'est le chemin le plus expose du produit : accessible sans compte, ouvert
sur internet, et le seul qui cree des donnees a partir d'entrees anonymes.
"""

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from django.core import mail

from apps.customers.models import Customer
from apps.scheduling.models import Booking
from apps.tenants.models import Tenant
from conftest import as_tenant, salon_host

BRAZZAVILLE = ZoneInfo("Africa/Brazzaville")
HOST = {"Host": salon_host("blondrose")}


def next_weekday_at(hour: int, weekday: int = 0) -> datetime:
    """Prochain jour ouvre du salon (lundi par defaut), a l'heure locale."""
    today = datetime.now(BRAZZAVILLE).date()
    ahead = (weekday - today.weekday()) % 7 or 7
    day: date = today + timedelta(days=ahead + 7)
    return datetime.combine(day, time(hour, 0), tzinfo=BRAZZAVILLE)


def booking_payload(salon, starts_at, **overrides):
    payload = {
        "service": str(salon.service.id),
        "starts_at": starts_at.isoformat(),
        "full_name": "Awa Diallo",
        "phone": "+242066112233",
        "email": "awa@example.com",
        "accepts_policy": True,
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Disponibilites
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_availability_returns_slots(api_client, salon_a):
    start = next_weekday_at(9).date()
    response = api_client.get(
        "/api/v1/public/availability",
        {
            "service": str(salon_a.service.id),
            "date_from": start.isoformat(),
            "date_to": start.isoformat(),
        },
        headers=HOST,
    )

    assert response.status_code == 200
    slots = response.data["slots"]
    assert slots
    assert {"starts_at", "ends_at", "staff_member_id"} <= set(slots[0])


@pytest.mark.django_db
def test_availability_rejects_an_oversized_date_range(api_client, salon_a):
    start = date(2026, 3, 2)
    response = api_client.get(
        "/api/v1/public/availability",
        {
            "service": str(salon_a.service.id),
            "date_from": start.isoformat(),
            "date_to": (start + timedelta(days=400)).isoformat(),
        },
        headers=HOST,
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_availability_of_an_unknown_service_is_404(api_client, salon_a):
    response = api_client.get(
        "/api/v1/public/availability",
        {
            "service": "11111111-1111-1111-1111-111111111111",
            "date_from": "2026-03-02",
            "date_to": "2026-03-02",
        },
        headers=HOST,
    )

    assert response.status_code == 404


@pytest.mark.django_db
def test_availability_of_another_salons_service_is_404(api_client, salon_a, salon_b):
    """Le service existe, mais pas pour ce salon : il doit rester invisible."""
    response = api_client.get(
        "/api/v1/public/availability",
        {
            "service": str(salon_b.service.id),
            "date_from": "2026-03-02",
            "date_to": "2026-03-02",
        },
        headers=HOST,
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Creation de reservation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_booking_is_created_and_notified(api_client, salon_a):
    starts_at = next_weekday_at(10)
    response = api_client.post(
        "/api/v1/public/bookings",
        booking_payload(salon_a, starts_at),
        format="json",
        headers=HOST,
    )

    assert response.status_code == 201, response.data
    assert response.data["service_name"] == "Tresses"
    assert response.data["staff_member_name"] == "Fatou"

    with as_tenant(salon_a.tenant):
        booking = Booking.objects.get(id=response.data["id"])
        assert booking.status == Booking.Status.REQUESTED
        assert booking.source == Booking.Source.WEB
        assert booking.customer.phone == "+242066112233"
        # Instantane du prix : le catalogue peut changer ensuite.
        assert booking.total_amount == salon_a.service.price_amount

    # Celery tourne en mode eager pendant les tests : les e-mails partent
    # dans la foulee. Un pour la cliente, un pour le salon.
    assert len(mail.outbox) == 2


@pytest.mark.django_db
def test_second_booking_on_the_same_slot_is_refused(api_client, salon_a):
    starts_at = next_weekday_at(10)
    first = api_client.post(
        "/api/v1/public/bookings",
        booking_payload(salon_a, starts_at),
        format="json",
        headers=HOST,
    )
    assert first.status_code == 201

    second = api_client.post(
        "/api/v1/public/bookings",
        booking_payload(salon_a, starts_at, phone="+242066998877", full_name="Mireille"),
        format="json",
        headers=HOST,
    )

    assert second.status_code == 409
    with as_tenant(salon_a.tenant):
        assert Booking.objects.count() == 1


@pytest.mark.django_db
def test_honeypot_submission_creates_nothing(api_client, salon_a):
    """Un robot remplit le champ piege ; on repond 201 sans rien creer, pour
    ne pas lui indiquer ce qui l'a trahi."""
    starts_at = next_weekday_at(10)
    response = api_client.post(
        "/api/v1/public/bookings",
        booking_payload(salon_a, starts_at, website="http://spam.example"),
        format="json",
        headers=HOST,
    )

    assert response.status_code == 201
    with as_tenant(salon_a.tenant):
        assert Booking.objects.count() == 0


@pytest.mark.django_db
def test_policy_must_be_accepted(api_client, salon_a):
    response = api_client.post(
        "/api/v1/public/bookings",
        booking_payload(salon_a, next_weekday_at(10), accepts_policy=False),
        format="json",
        headers=HOST,
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_a_slot_in_the_past_is_refused(api_client, salon_a):
    past = datetime.now(BRAZZAVILLE) - timedelta(days=3)
    response = api_client.post(
        "/api/v1/public/bookings",
        booking_payload(salon_a, past),
        format="json",
        headers=HOST,
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_a_closed_slot_is_refused(api_client, salon_a):
    """Le salon ouvre a 9h : 6h du matin n'est jamais reservable."""
    response = api_client.post(
        "/api/v1/public/bookings",
        booking_payload(salon_a, next_weekday_at(6)),
        format="json",
        headers=HOST,
    )

    assert response.status_code == 409


@pytest.mark.django_db
def test_a_suspended_salon_accepts_nothing(api_client, salon_a):
    salon_a.tenant.status = Tenant.Status.SUSPENDED
    salon_a.tenant.save()

    response = api_client.post(
        "/api/v1/public/bookings",
        booking_payload(salon_a, next_weekday_at(10)),
        format="json",
        headers=HOST,
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_a_suspended_salon_shows_a_notice_instead_of_its_site(api_client, salon_a):
    salon_a.tenant.status = Tenant.Status.SUSPENDED
    salon_a.tenant.save()

    response = api_client.get("/api/v1/public/salon", headers=HOST)

    assert response.status_code == 503
    assert response.data["code"] == "suspended"


@pytest.mark.django_db
def test_idempotency_key_prevents_a_duplicate(api_client, salon_a):
    starts_at = next_weekday_at(10)
    payload = booking_payload(salon_a, starts_at)
    headers = {**HOST, "Idempotency-Key": "abc-123"}

    first = api_client.post(
        "/api/v1/public/bookings", payload, format="json", headers=headers
    )
    second = api_client.post(
        "/api/v1/public/bookings", payload, format="json", headers=headers
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.data["id"] == second.data["id"]
    with as_tenant(salon_a.tenant):
        assert Booking.objects.count() == 1


@pytest.mark.django_db
def test_a_returning_customer_keeps_a_single_record(api_client, salon_a):
    """Le telephone fait office d'identite : deux reservations, une fiche."""
    for hour in (10, 14):
        response = api_client.post(
            "/api/v1/public/bookings",
            booking_payload(salon_a, next_weekday_at(hour)),
            format="json",
            headers=HOST,
        )
        assert response.status_code == 201, response.data

    with as_tenant(salon_a.tenant):
        assert Customer.objects.filter(phone="+242066112233").count() == 1
        assert Booking.objects.count() == 2


@pytest.mark.django_db
def test_marketing_consent_is_recorded_with_its_date(api_client, salon_a):
    response = api_client.post(
        "/api/v1/public/bookings",
        booking_payload(salon_a, next_weekday_at(10), marketing_consent=True),
        format="json",
        headers=HOST,
    )
    assert response.status_code == 201

    with as_tenant(salon_a.tenant):
        customer = Customer.objects.get(phone="+242066112233")
        assert customer.marketing_consent is True
        assert customer.marketing_consent_at is not None


@pytest.mark.django_db
def test_the_logo_and_the_banner_stay_out_of_the_public_gallery(api_client, salon_a):
    """Le logo est une image de marque, pas une realisation.

    Les trois sont televerses dans la meme reserve et portent le meme `kind`,
    donc rien dans le modele ne les distingue : seul le profil du salon sait
    lequel sert de logo. Sans l'exclusion faite a la lecture, un logo se
    retrouvait affiche au milieu des photos de coiffures.
    """
    from apps.media.models import MediaAsset
    from apps.salons.models import SalonProfile

    with as_tenant(salon_a.tenant):
        logo, banner, work = (
            MediaAsset.objects.create(
                tenant_id=salon_a.tenant.id,
                file=f"tenants/{salon_a.tenant.id}/media/{name}.jpg",
                content_type="image/jpeg",
                kind=MediaAsset.Kind.GALLERY,
                alt_text=name,
            )
            for name in ("logo", "banner", "tresses")
        )
        SalonProfile.objects.filter(tenant=salon_a.tenant).update(
            logo=logo, banner=banner
        )

    response = api_client.get("/api/v1/public/salon", headers=HOST)

    assert response.status_code == 200
    published = {item["id"] for item in response.data["gallery"]}
    assert published == {str(work.id)}

    # Ils restent joignables la ou ils ont un sens : rien n'a ete supprime,
    # seul l'affichage change.
    assert response.data["logo"]["id"] == str(logo.id)
    assert response.data["banner"]["id"] == str(banner.id)


# ---------------------------------------------------------------------------
# Prestations a domicile
# ---------------------------------------------------------------------------


def make_zone(salon, name="Bacongo", fee="3000", **overrides):
    from apps.salons.models import TravelZone

    with as_tenant(salon.tenant):
        return TravelZone.objects.create(
            tenant=salon.tenant, name=name, fee_amount=Decimal(fee), **overrides
        )


def allow_home(salon, mode="hybrid"):
    from apps.salons.models import ServiceMode

    assert mode in ServiceMode.values
    with as_tenant(salon.tenant):
        salon.service.location_mode = mode
        salon.service.save(update_fields=["location_mode"])


@pytest.mark.django_db
def test_a_home_booking_adds_the_travel_fee_to_the_announced_total(api_client, salon_a):
    """Un seul montant : la cliente ne doit pas avoir d'addition a faire."""
    allow_home(salon_a)
    zone = make_zone(salon_a, fee="3000")
    starts_at = next_weekday_at(10)

    response = api_client.post(
        "/api/v1/public/bookings",
        booking_payload(
            salon_a, starts_at, travel_zone=str(zone.id), address="12 rue des Manguiers"
        ),
        format="json",
        headers=HOST,
    )

    assert response.status_code == 201
    expected = salon_a.service.price_amount + Decimal("3000")
    assert Decimal(response.data["total_amount"]) == expected

    with as_tenant(salon_a.tenant):
        booking = Booking.objects.get(id=response.data["id"])
    # Le nom est copie, pas reference : renommer la zone demain ne doit pas
    # reecrire ce qui a ete vendu aujourd'hui.
    assert booking.travel_zone_name == "Bacongo"
    assert booking.travel_fee_amount == Decimal("3000")
    assert booking.location_mode == "home"
    assert booking.address == "12 rue des Manguiers"


@pytest.mark.django_db
def test_renaming_a_zone_does_not_rewrite_past_bookings(api_client, salon_a):
    allow_home(salon_a)
    zone = make_zone(salon_a, name="Bacongo", fee="3000")
    api_client.post(
        "/api/v1/public/bookings",
        booking_payload(
            salon_a, next_weekday_at(10), travel_zone=str(zone.id), address="Chez moi"
        ),
        format="json",
        headers=HOST,
    )

    with as_tenant(salon_a.tenant):
        zone.name = "Bacongo Sud"
        zone.fee_amount = Decimal("5000")
        zone.save()

        booking = Booking.objects.latest("created_at")

    assert booking.travel_zone_name == "Bacongo"
    assert booking.travel_fee_amount == Decimal("3000")


@pytest.mark.django_db
def test_a_zone_belonging_to_another_salon_is_refused(api_client, salon_a, salon_b):
    """Le tarif est relu en base : un identifiant devine n'ouvre rien."""
    allow_home(salon_a)
    make_zone(salon_a, name="Bacongo", fee="3000")
    intruder = make_zone(salon_b, name="Gratuite", fee="0")

    response = api_client.post(
        "/api/v1/public/bookings",
        booking_payload(
            salon_a,
            next_weekday_at(10),
            travel_zone=str(intruder.id),
            address="Chez moi",
        ),
        format="json",
        headers=HOST,
    )

    assert response.status_code == 400
    assert response.data["code"] == "unknown_travel_zone"


@pytest.mark.django_db
def test_a_salon_only_service_refuses_a_travel_zone(api_client, salon_a):
    """Sans ce controle, on se ferait livrer une prestation non deplacable."""
    zone = make_zone(salon_a)

    response = api_client.post(
        "/api/v1/public/bookings",
        booking_payload(
            salon_a, next_weekday_at(10), travel_zone=str(zone.id), address="Chez moi"
        ),
        format="json",
        headers=HOST,
    )

    assert response.status_code == 400
    assert response.data["code"] == "travel_not_available"


@pytest.mark.django_db
def test_a_home_only_service_requires_a_zone(api_client, salon_a):
    """Sinon le rendez-vous partirait sans adresse et sans frais."""
    allow_home(salon_a, mode="home")
    make_zone(salon_a)

    response = api_client.post(
        "/api/v1/public/bookings",
        booking_payload(salon_a, next_weekday_at(10)),
        format="json",
        headers=HOST,
    )

    assert response.status_code == 400
    assert response.data["code"] == "travel_zone_required"


@pytest.mark.django_db
def test_a_home_booking_without_an_address_is_refused(api_client, salon_a):
    allow_home(salon_a)
    zone = make_zone(salon_a)

    response = api_client.post(
        "/api/v1/public/bookings",
        booking_payload(salon_a, next_weekday_at(10), travel_zone=str(zone.id)),
        format="json",
        headers=HOST,
    )

    assert response.status_code == 400
    assert response.data["code"] == "address_required"


@pytest.mark.django_db
def test_the_mini_site_lists_only_the_zones_still_served(api_client, salon_a):
    make_zone(salon_a, name="Bacongo", fee="3000")
    make_zone(salon_a, name="Kintélé", fee="8000", active=False)

    response = api_client.get("/api/v1/public/salon", headers=HOST)

    assert response.status_code == 200
    assert [zone["name"] for zone in response.data["travel_zones"]] == ["Bacongo"]


# ---------------------------------------------------------------------------
# Options de prestation
# ---------------------------------------------------------------------------


def make_option(salon, name="Longueur XL", price="5000", minutes=0, **overrides):
    from apps.catalog.models import ServiceOption

    with as_tenant(salon.tenant):
        return ServiceOption.objects.create(
            tenant=salon.tenant,
            service=salon.service,
            name=name,
            price_delta=Decimal(price),
            duration_delta_minutes=minutes,
            **overrides,
        )


@pytest.mark.django_db
def test_an_option_that_takes_time_removes_the_slots_it_no_longer_fits(
    api_client, salon_a
):
    """Le coeur du chantier : une option n'est pas qu'une ligne de facture.

    La prestation dure 2 h et le salon ferme a 18 h. Une option de 90 min la
    porte a 3 h 30 : les creneaux de fin de journee qui la contenaient encore
    a 2 h ne la contiennent plus. Les proposer quand meme ferait deborder le
    rendez-vous sur la fermeture.
    """
    option = make_option(salon_a, name="Longueur XL", minutes=90)
    day = next_weekday_at(9).date()
    base = {
        "service": str(salon_a.service.id),
        "date_from": day.isoformat(),
        "date_to": day.isoformat(),
    }

    without = api_client.get("/api/v1/public/availability", base, headers=HOST)
    with_option = api_client.get(
        "/api/v1/public/availability",
        {**base, "options": [str(option.id)]},
        headers=HOST,
    )

    assert without.status_code == 200 and with_option.status_code == 200
    short = [slot["starts_at"] for slot in without.data["slots"]]
    long = [slot["starts_at"] for slot in with_option.data["slots"]]

    assert len(long) < len(short), "L'option n'a pas raccourci la liste"
    # Aucun creneau nouveau n'apparait : une prestation plus longue ne peut
    # que perdre des possibilites.
    assert set(long) <= set(short)


@pytest.mark.django_db
def test_a_booking_with_options_is_longer_and_costs_more(api_client, salon_a):
    option = make_option(salon_a, name="Longueur XL", price="5000", minutes=45)
    starts_at = next_weekday_at(10)

    response = api_client.post(
        "/api/v1/public/bookings",
        booking_payload(salon_a, starts_at, options=[str(option.id)]),
        format="json",
        headers=HOST,
    )

    assert response.status_code == 201, response.data
    with as_tenant(salon_a.tenant):
        booking = Booking.objects.get(id=response.data["id"])

    expected_end = starts_at + timedelta(
        minutes=salon_a.service.duration_minutes + 45
    )
    assert booking.ends_at == expected_end
    assert booking.total_amount == salon_a.service.price_amount + Decimal("5000")
    assert booking.options_amount == Decimal("5000")
    assert booking.options_snapshot == [
        {"name": "Longueur XL", "price": "5000.00", "minutes": 45}
    ]


@pytest.mark.django_db
def test_retarifying_an_option_does_not_rewrite_past_bookings(api_client, salon_a):
    option = make_option(salon_a, name="Longueur XL", price="5000", minutes=45)
    api_client.post(
        "/api/v1/public/bookings",
        booking_payload(salon_a, next_weekday_at(10), options=[str(option.id)]),
        format="json",
        headers=HOST,
    )

    with as_tenant(salon_a.tenant):
        option.name = "Longueur extra-longue"
        option.price_delta = Decimal("9000")
        option.save()

        booking = Booking.objects.latest("created_at")

    assert booking.options_snapshot[0]["name"] == "Longueur XL"
    assert booking.options_amount == Decimal("5000")


@pytest.mark.django_db
def test_an_option_of_another_service_is_refused(api_client, salon_a):
    """Le tarif et la duree sont relus en base : un identifiant devine
    n'ouvre ni un supplement gratuit, ni un creneau trop court."""
    from apps.catalog.models import Service, ServiceOption

    with as_tenant(salon_a.tenant):
        other = Service.objects.create(
            tenant=salon_a.tenant,
            category=salon_a.category,
            name="Autre prestation",
            duration_minutes=30,
            price_amount=Decimal("5000"),
        )
        intruder = ServiceOption.objects.create(
            tenant=salon_a.tenant, service=other, name="Option voisine"
        )

    response = api_client.post(
        "/api/v1/public/bookings",
        booking_payload(
            salon_a, next_weekday_at(10), options=[str(intruder.id)]
        ),
        format="json",
        headers=HOST,
    )

    assert response.status_code == 400
    assert response.data["code"] == "unknown_option"


@pytest.mark.django_db
def test_an_option_belonging_to_another_salon_is_refused(api_client, salon_a, salon_b):
    intruder = make_option(salon_b, name="Option d'ailleurs", price="0")

    response = api_client.post(
        "/api/v1/public/bookings",
        booking_payload(salon_a, next_weekday_at(10), options=[str(intruder.id)]),
        format="json",
        headers=HOST,
    )

    assert response.status_code == 400
    assert response.data["code"] == "unknown_option"


@pytest.mark.django_db
def test_a_deactivated_option_can_no_longer_be_booked(api_client, salon_a):
    option = make_option(salon_a, name="Ancienne option", active=False)

    response = api_client.post(
        "/api/v1/public/bookings",
        booking_payload(salon_a, next_weekday_at(10), options=[str(option.id)]),
        format="json",
        headers=HOST,
    )

    assert response.status_code == 400
    assert response.data["code"] == "unknown_option"


@pytest.mark.django_db
def test_the_mini_site_lists_the_options_of_each_service(api_client, salon_a):
    make_option(salon_a, name="Longueur XL", price="5000", minutes=45)
    make_option(salon_a, name="Retirée", active=False)

    response = api_client.get("/api/v1/public/salon", headers=HOST)

    assert response.status_code == 200
    options = response.data["categories"][0]["services"][0]["options"]
    assert [option["name"] for option in options] == ["Longueur XL"]
    assert options[0]["duration_delta_minutes"] == 45


# ---------------------------------------------------------------------------
# Ressources limitees
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_shared_basin_blocks_a_slot_even_with_a_free_stylist(api_client, salon_a):
    """Le cas que le moteur ne voyait pas.

    Deux prestataires libres, mais un seul bac a shampooing. Quand l'un des
    deux l'utilise, l'autre ne peut pas se voir proposer le meme creneau -
    meme si la personne, elle, est disponible.
    """
    from apps.catalog.models import Resource, ServiceResource
    from apps.scheduling.models import BusinessHours
    from apps.staff.models import StaffMember, StaffService

    with as_tenant(salon_a.tenant):
        basin = Resource.objects.create(
            tenant=salon_a.tenant, name="Bac", capacity=1, kind=Resource.Kind.BASIN
        )
        ServiceResource.objects.create(
            tenant=salon_a.tenant, service=salon_a.service, resource=basin
        )

        second = StaffMember.objects.create(
            tenant=salon_a.tenant, name="Seconde coiffeuse"
        )
        StaffService.objects.create(
            tenant=salon_a.tenant, staff_member=second, service=salon_a.service
        )
        for hours in BusinessHours.objects.filter(staff_member__isnull=True):
            BusinessHours.objects.get_or_create(
                tenant=salon_a.tenant,
                staff_member=second,
                weekday=hours.weekday,
                starts_at=hours.starts_at,
                ends_at=hours.ends_at,
            )

    starts_at = next_weekday_at(10)
    day = starts_at.date().isoformat()
    query = {"service": str(salon_a.service.id), "date_from": day, "date_to": day}

    before = api_client.get("/api/v1/public/availability", query, headers=HOST)
    offered_before = {
        datetime.fromisoformat(slot["starts_at"].replace("Z", "+00:00"))
        for slot in before.data["slots"]
    }
    assert starts_at in offered_before, "Le creneau doit exister avant d'etre pris"

    # Une cliente prend le creneau : le bac unique part avec elle.
    booked = api_client.post(
        "/api/v1/public/bookings",
        booking_payload(salon_a, starts_at),
        format="json",
        headers=HOST,
    )
    assert booked.status_code == 201, booked.data

    after = api_client.get("/api/v1/public/availability", query, headers=HOST)
    remaining = {
        datetime.fromisoformat(slot["starts_at"].replace("Z", "+00:00"))
        for slot in after.data["slots"]
    }

    assert starts_at not in remaining, (
        "Le creneau reste propose alors que l'unique bac est occupe"
    )


@pytest.mark.django_db
def test_two_basins_still_allow_a_second_booking_at_the_same_time(api_client, salon_a):
    """Le pendant : une ressource en double ne doit rien bloquer trop tot."""
    from apps.catalog.models import Resource, ServiceResource
    from apps.scheduling.models import BusinessHours
    from apps.staff.models import StaffMember, StaffService

    with as_tenant(salon_a.tenant):
        basin = Resource.objects.create(
            tenant=salon_a.tenant, name="Bacs", capacity=2, kind=Resource.Kind.BASIN
        )
        ServiceResource.objects.create(
            tenant=salon_a.tenant, service=salon_a.service, resource=basin
        )
        second = StaffMember.objects.create(
            tenant=salon_a.tenant, name="Seconde coiffeuse"
        )
        StaffService.objects.create(
            tenant=salon_a.tenant, staff_member=second, service=salon_a.service
        )
        for hours in BusinessHours.objects.filter(staff_member__isnull=True):
            BusinessHours.objects.get_or_create(
                tenant=salon_a.tenant,
                staff_member=second,
                weekday=hours.weekday,
                starts_at=hours.starts_at,
                ends_at=hours.ends_at,
            )

    starts_at = next_weekday_at(10)
    api_client.post(
        "/api/v1/public/bookings",
        booking_payload(salon_a, starts_at),
        format="json",
        headers=HOST,
    )

    day = starts_at.date().isoformat()
    after = api_client.get(
        "/api/v1/public/availability",
        {"service": str(salon_a.service.id), "date_from": day, "date_to": day},
        headers=HOST,
    )

    # Comparaison d'instants, pas de chaines : l'API repond en UTC alors que
    # `starts_at` est en heure locale du salon. Les deux designent le meme
    # moment et doivent etre reconnus comme tel.
    offered = {
        datetime.fromisoformat(slot["starts_at"].replace("Z", "+00:00"))
        for slot in after.data["slots"]
    }
    assert starts_at in offered, "Le second bac aurait du rester disponible"


@pytest.mark.django_db
def test_every_media_with_a_job_stays_out_of_the_gallery(api_client, salon_a):
    """La correction ecrite a la main s'est perimee deux fois.

    D'abord au logo, puis aux QR codes de paiement : le selecteur de medias
    est commun, tout arrive avec `kind = gallery`, et chaque nouvel ecran qui
    choisit une image en ajoutait une a la galerie du salon.

    La liste est donc deduite des cles etrangeres vers MediaAsset. Ce test
    couvre les emplois d'aujourd'hui - et celui de demain s'y ajoutera tout
    seul, puisque rien n'est enumere ici non plus.
    """
    from apps.media.models import MediaAsset
    from apps.media.reserved import reserved_media_ids
    from apps.payments.models import PaymentChannel
    from apps.salons.models import SalonProfile
    from apps.store.models import Product

    with as_tenant(salon_a.tenant):
        def image(name):
            return MediaAsset.objects.create(
                tenant_id=salon_a.tenant.id,
                file=f"tenants/{salon_a.tenant.id}/media/{name}.jpg",
                content_type="image/jpeg",
                kind=MediaAsset.Kind.GALLERY,
                alt_text=name,
            )

        logo, qr, article, work = (
            image(n) for n in ("logo", "qr-wechat", "meches", "tresses")
        )

        SalonProfile.objects.filter(tenant=salon_a.tenant).update(logo=logo)
        PaymentChannel.objects.create(
            tenant=salon_a.tenant, kind=PaymentChannel.Kind.WECHAT, qr_image=qr
        )
        Product.objects.create(
            tenant=salon_a.tenant, name="Mèches", price=Decimal("10"), image=article
        )

        taken = reserved_media_ids()

    assert {logo.id, qr.id, article.id} <= taken
    assert work.id not in taken

    response = api_client.get("/api/v1/public/salon", headers=HOST)

    published = {item["id"] for item in response.data["gallery"]}
    assert published == {str(work.id)}


# ---------------------------------------------------------------------------
# Ce qui n'a rien a faire dans les realisations
# ---------------------------------------------------------------------------
#
# Ces tests verrouillent un defaut signale trois fois : des QR codes de
# paiement affiches sur la page « Realisations » d'un salon, entre deux
# coiffures.
#
# La cause tenait a un defaut de conception, pas a un oubli. Tout
# televersement arrivait etiquete « galerie », quel que soit l'ecran
# d'origine - le selecteur de medias est partage. Tant que l'image finissait
# rattachee a son emploi, l'exclusion par cle etrangere la retirait. Mais un
# televersement jamais rattache - on se trompe de fichier, on en essaie deux,
# on en change plus tard - restait « galerie » pour toujours.


def _media(salon, nom, genre=None, taille=1000):
    from apps.media.models import MediaAsset

    return MediaAsset.objects.create(
        tenant_id=salon.tenant.id,
        file=f"tenants/{salon.tenant.id}/media/{uuid4()}/{nom}",
        content_type="image/png",
        byte_size=taille,
        kind=genre or MediaAsset.Kind.GALLERY,
        alt_text=nom,
    )


@pytest.mark.django_db
def test_a_payment_qr_never_reaches_the_public_gallery(api_client, salon_a):
    """Meme rattache a un moyen de paiement, le QR reste hors des realisations."""
    from apps.media.models import MediaAsset
    from apps.payments.models import PaymentChannel

    with as_tenant(salon_a.tenant):
        qr = _media(salon_a, "wechat.png", MediaAsset.Kind.PAYMENT)
        travail = _media(salon_a, "tresses.png")
        PaymentChannel.objects.create(
            tenant=salon_a.tenant, kind=PaymentChannel.Kind.WECHAT, qr_image=qr
        )

    response = api_client.get("/api/v1/public/salon", headers=HOST)

    assert {item["id"] for item in response.data["gallery"]} == {str(travail.id)}


@pytest.mark.django_db
def test_an_unattached_payment_upload_is_excluded_too(api_client, salon_a):
    """Le cas qui echappait a l'ancienne regle.

    Un QR televerse puis jamais rattache n'etait vise par aucune cle
    etrangere : rien ne le distinguait d'une coiffure. Le genre, pose au
    televersement par l'ecran qui sait ce qu'il fait, le regle.
    """
    from apps.media.models import MediaAsset

    with as_tenant(salon_a.tenant):
        orphelin = _media(salon_a, "alipay.png", MediaAsset.Kind.PAYMENT)
        travail = _media(salon_a, "tresses.png")

    response = api_client.get("/api/v1/public/salon", headers=HOST)

    publies = {item["id"] for item in response.data["gallery"]}
    assert publies == {str(travail.id)}
    assert str(orphelin.id) not in publies


@pytest.mark.django_db
def test_the_same_file_uploaded_twice_appears_once(api_client, salon_a):
    """Le selecteur televerse a chaque choix : essayer deux fichiers laisse
    deux copies, et la meme photo deux fois dans une mosaique est un bug."""
    with as_tenant(salon_a.tenant):
        copies = {
            str(_media(salon_a, "tresses.png", taille=4242).id) for _ in range(2)
        }
        autre = _media(salon_a, "ongles.png", taille=4242)

    response = api_client.get("/api/v1/public/salon", headers=HOST)

    publies = {item["id"] for item in response.data["gallery"]}

    # Une seule des deux copies survit. Laquelle n.a aucune importance :
    # elles portent le meme fichier. L.affirmer figerait une regle de
    # departage arbitraire.
    assert len(publies & copies) == 1

    # Un fichier de meme poids mais de nom different n.est pas un doublon.
    assert str(autre.id) in publies
    assert len(publies) == 2


@pytest.mark.django_db
def test_a_second_copy_of_a_used_image_is_excluded(api_client, salon_a):
    """Le cas exact du signalement.

    Le QR rattache au moyen de paiement etait bien exclu ; sa copie, restee
    dans la reserve, s'affichait. Les medias deja employes servent donc
    d'amorce au detecteur de doublons.
    """
    from apps.media.models import MediaAsset
    from apps.payments.models import PaymentChannel

    with as_tenant(salon_a.tenant):
        qr = _media(salon_a, "alipay.png", MediaAsset.Kind.PAYMENT, taille=151635)
        # La copie porte le genre « galerie » : c'est ainsi que les anciens
        # televersements ont ete enregistres.
        copie = _media(salon_a, "alipay.png", taille=151635)
        travail = _media(salon_a, "tresses.png")
        PaymentChannel.objects.create(
            tenant=salon_a.tenant, kind=PaymentChannel.Kind.ALIPAY, qr_image=qr
        )

    response = api_client.get("/api/v1/public/salon", headers=HOST)

    publies = {item["id"] for item in response.data["gallery"]}
    assert str(copie.id) not in publies
    assert publies == {str(travail.id)}


@pytest.mark.django_db
def test_a_deposit_proof_never_reaches_the_public_gallery(api_client, salon_a):
    """La piece la plus sensible de la reserve, et deux barrieres.

    Une capture d'ecran de paiement porte le nom de la cliente et parfois son
    solde bancaire. Elle etait deja rangee en `private` - mais sous le genre
    « galerie », donc la protection ne tenait qu'a un seul drapeau. Le test
    bascule justement ce drapeau : le genre doit tenir seul.
    """
    from apps.media.models import MediaAsset

    with as_tenant(salon_a.tenant):
        preuve = _media(salon_a, "capture-wechat.png", MediaAsset.Kind.PROOF)
        # Le drapeau de visibilite saute - accident, script de reprise,
        # manipulation. La capture ne doit pas apparaitre pour autant.
        MediaAsset.objects.filter(id=preuve.id).update(
            visibility=MediaAsset.Visibility.PUBLIC
        )
        travail = _media(salon_a, "tresses.png")

    response = api_client.get("/api/v1/public/salon", headers=HOST)

    publies = {item["id"] for item in response.data["gallery"]}
    assert str(preuve.id) not in publies
    assert publies == {str(travail.id)}


@pytest.mark.django_db
def test_a_real_proof_upload_lands_private_and_out_of_the_gallery(
    api_client, salon_a, tmp_path
):
    """Le chemin reel, depuis la page de reglement.

    Verifie ce que produit vraiment l'envoi d'une preuve, et non ce qu'on
    croit qu'il produit : genre `proof` et visibilite `private`, les deux.
    """
    from django.core.files.uploadedfile import SimpleUploadedFile

    from apps.media.models import MediaAsset
    from apps.payments.tokens import payment_token

    starts_at = next_weekday_at(10)
    with as_tenant(salon_a.tenant):
        booking = Booking.objects.create(
            tenant=salon_a.tenant,
            customer=salon_a.customer,
            staff_member=salon_a.staff,
            service=salon_a.service,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(hours=1),
            status=Booking.Status.PENDING_PAYMENT,
            service_name="Box braids",
            deposit_amount=Decimal("150"),
        )

    # Un vrai PNG, fabrique a la volee.
    #
    # Le champ image de DRF ouvre le fichier avec Pillow : des octets
    # bricoles sont refuses, et le type MIME declare n'y change rien. Ce test
    # l'a appris a ses depens, et c'est une bonne chose - la validation qu'il
    # traverse est celle que traversera la capture d'une vraie cliente.
    from io import BytesIO

    from PIL import Image

    tampon = BytesIO()
    Image.new("RGB", (8, 8), "white").save(tampon, format="PNG")
    image = SimpleUploadedFile("capture.png", tampon.getvalue(), "image/png")

    response = api_client.post(
        "/api/v1/public/payment/proof",
        {"token": payment_token(booking), "image": image},
        format="multipart",
        headers=HOST,
    )

    assert response.status_code in (200, 201), response.data

    with as_tenant(salon_a.tenant):
        asset = MediaAsset.objects.get(alt_text="Preuve de versement")
    assert asset.kind == MediaAsset.Kind.PROOF
    assert asset.visibility == MediaAsset.Visibility.PRIVATE

    galerie = api_client.get("/api/v1/public/salon", headers=HOST).data["gallery"]
    assert str(asset.id) not in {item["id"] for item in galerie}
