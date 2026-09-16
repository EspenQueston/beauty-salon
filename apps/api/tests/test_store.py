"""La boutique du salon, vue depuis la reservation.

Trois choses doivent tenir : on ne peut pas s'offrir un article a un prix
qu'on a choisi soi-meme, on ne peut pas vendre deux fois le dernier
exemplaire, et une reservation annulee rend la marchandise.
"""

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from apps.finance.models import Transaction
from apps.scheduling.models import Booking
from apps.store.models import Product, Requirement, RequirementProduct
from conftest import as_tenant, salon_host

BRAZZAVILLE = ZoneInfo("Africa/Brazzaville")
HOST = {"Host": salon_host("blondrose")}


def next_monday_at(hour: int) -> datetime:
    today = datetime.now(BRAZZAVILLE).date()
    ahead = (0 - today.weekday()) % 7 or 7
    day: date = today + timedelta(days=ahead + 7)
    return datetime.combine(day, time(hour, 0), tzinfo=BRAZZAVILLE)


def make_store(salon, *, price="12000", stock=5, mandatory=True):
    with as_tenant(salon.tenant):
        product = Product.objects.create(
            tenant=salon.tenant,
            name="Mèches kanekalon",
            price=Decimal(price),
            stock=stock,
        )
        requirement = Requirement.objects.create(
            tenant=salon.tenant,
            service=salon.service,
            label="3 paquets de mèches",
            mandatory=mandatory,
        )
        RequirementProduct.objects.create(
            tenant=salon.tenant, requirement=requirement, product=product
        )
    return product, requirement


def booking_payload(salon, starts_at, **overrides):
    payload = {
        "service": str(salon.service.id),
        "starts_at": starts_at.isoformat(),
        "full_name": "Awa Diallo",
        "phone": "+242066112233",
        "accepts_policy": True,
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Ce que la cliente voit avant de reserver
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_mini_site_says_what_to_bring(api_client, salon_a):
    make_store(salon_a)

    response = api_client.get("/api/v1/public/salon", headers=HOST)

    service = response.data["categories"][0]["services"][0]
    requirement = service["requirements"][0]
    assert requirement["label"] == "3 paquets de mèches"
    assert requirement["mandatory"] is True
    assert requirement["products"][0]["name"] == "Mèches kanekalon"


@pytest.mark.django_db
def test_a_product_out_of_stock_is_shown_as_unavailable_not_hidden(
    api_client, salon_a
):
    """Le faire disparaitre laisserait croire que le salon n'en vend pas."""
    make_store(salon_a, stock=0)

    response = api_client.get("/api/v1/public/salon", headers=HOST)

    product = response.data["categories"][0]["services"][0]["requirements"][0][
        "products"
    ][0]
    assert product["available"] is False


# ---------------------------------------------------------------------------
# Acheter pendant la reservation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_buying_what_is_needed_adds_it_to_the_total(api_client, salon_a):
    product, _ = make_store(salon_a, price="12000")
    starts_at = next_monday_at(10)

    response = api_client.post(
        "/api/v1/public/bookings",
        booking_payload(
            salon_a,
            starts_at,
            items=[{"product": str(product.id), "quantity": 3}],
        ),
        format="json",
        headers=HOST,
    )

    assert response.status_code == 201, response.data
    with as_tenant(salon_a.tenant):
        booking = Booking.objects.get(id=response.data["id"])

    assert booking.items_amount == Decimal("36000")
    assert booking.total_amount == salon_a.service.price_amount + Decimal("36000")
    assert booking.items_snapshot[0]["quantity"] == 3


@pytest.mark.django_db
def test_the_price_comes_from_the_database_not_the_request(api_client, salon_a):
    """Sinon il suffirait de modifier la requete pour s'offrir une perruque."""
    product, _ = make_store(salon_a, price="12000")
    starts_at = next_monday_at(10)

    response = api_client.post(
        "/api/v1/public/bookings",
        booking_payload(
            salon_a,
            starts_at,
            items=[
                {"product": str(product.id), "quantity": 1, "unit_price": "1", "total": "1"}
            ],
        ),
        format="json",
        headers=HOST,
    )

    assert response.status_code == 201
    with as_tenant(salon_a.tenant):
        booking = Booking.objects.get(id=response.data["id"])
    assert booking.items_amount == Decimal("12000")


@pytest.mark.django_db
def test_buying_removes_the_item_from_stock(api_client, salon_a):
    product, _ = make_store(salon_a, stock=5)
    starts_at = next_monday_at(10)

    api_client.post(
        "/api/v1/public/bookings",
        booking_payload(
            salon_a, starts_at, items=[{"product": str(product.id), "quantity": 2}]
        ),
        format="json",
        headers=HOST,
    )

    with as_tenant(salon_a.tenant):
        product.refresh_from_db()
    assert product.stock == 3


@pytest.mark.django_db
def test_the_last_item_cannot_be_sold_twice(api_client, salon_a):
    product, _ = make_store(salon_a, stock=1)
    starts_at = next_monday_at(10)

    first = api_client.post(
        "/api/v1/public/bookings",
        booking_payload(
            salon_a, starts_at, items=[{"product": str(product.id), "quantity": 1}]
        ),
        format="json",
        headers=HOST,
    )
    second = api_client.post(
        "/api/v1/public/bookings",
        booking_payload(
            salon_a,
            next_monday_at(14),
            phone="+242066999000",
            items=[{"product": str(product.id), "quantity": 1}],
        ),
        format="json",
        headers=HOST,
    )

    assert first.status_code == 201
    assert second.status_code == 400
    assert second.data["code"] == "store_refused"


@pytest.mark.django_db
def test_cancelling_gives_the_stock_back(api_client, salon_a):
    from apps.scheduling.services.booking import cancel_booking

    product, _ = make_store(salon_a, stock=4)
    created = api_client.post(
        "/api/v1/public/bookings",
        booking_payload(
            salon_a,
            next_monday_at(10),
            items=[{"product": str(product.id), "quantity": 2}],
        ),
        format="json",
        headers=HOST,
    )

    with as_tenant(salon_a.tenant):
        product.refresh_from_db()
        assert product.stock == 2

        cancel_booking(booking=Booking.objects.get(id=created.data["id"]))
        product.refresh_from_db()

    assert product.stock == 4


@pytest.mark.django_db
def test_an_article_from_another_service_is_refused(api_client, salon_a):
    from apps.catalog.models import Service

    with as_tenant(salon_a.tenant):
        other = Service.objects.create(
            tenant=salon_a.tenant,
            category=salon_a.category,
            name="Autre prestation",
            duration_minutes=30,
            price_amount=Decimal("5000"),
        )
        intruder = Product.objects.create(
            tenant=salon_a.tenant, name="Perruque", price=Decimal("50000"), stock=2
        )
        requirement = Requirement.objects.create(
            tenant=salon_a.tenant, service=other, label="Une perruque"
        )
        RequirementProduct.objects.create(
            tenant=salon_a.tenant, requirement=requirement, product=intruder
        )

    response = api_client.post(
        "/api/v1/public/bookings",
        booking_payload(
            salon_a,
            next_monday_at(10),
            items=[{"product": str(intruder.id), "quantity": 1}],
        ),
        format="json",
        headers=HOST,
    )

    assert response.status_code == 400
    assert response.data["code"] == "store_refused"


@pytest.mark.django_db
def test_another_salons_product_is_refused(api_client, salon_a, salon_b):
    with as_tenant(salon_b.tenant):
        intruder = Product.objects.create(
            tenant=salon_b.tenant, name="Mèches du salon B", price=Decimal("1"), stock=9
        )

    response = api_client.post(
        "/api/v1/public/bookings",
        booking_payload(
            salon_a,
            next_monday_at(10),
            items=[{"product": str(intruder.id), "quantity": 1}],
        ),
        format="json",
        headers=HOST,
    )

    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Le silence, plutot que le mensonge
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_mandatory_requirement_must_be_answered(api_client, salon_a):
    """Reserver quatre heures sans dire ce qu'on fait des meches finit en
    rendez-vous annule sur place."""
    make_store(salon_a, mandatory=True)

    response = api_client.post(
        "/api/v1/public/bookings",
        booking_payload(salon_a, next_monday_at(10)),
        format="json",
        headers=HOST,
    )

    assert response.status_code == 400
    assert response.data["code"] == "requirement_unanswered"


@pytest.mark.django_db
def test_saying_she_brings_it_is_enough(api_client, salon_a):
    """On la croit sur parole : lui refuser sa propre perruque serait absurde."""
    _, requirement = make_store(salon_a, mandatory=True)

    response = api_client.post(
        "/api/v1/public/bookings",
        booking_payload(
            salon_a, next_monday_at(10), owned_requirements=[str(requirement.id)]
        ),
        format="json",
        headers=HOST,
    )

    assert response.status_code == 201, response.data


@pytest.mark.django_db
def test_an_optional_requirement_blocks_nothing(api_client, salon_a):
    make_store(salon_a, mandatory=False)

    response = api_client.post(
        "/api/v1/public/bookings",
        booking_payload(salon_a, next_monday_at(10)),
        format="json",
        headers=HOST,
    )

    assert response.status_code == 201


# ---------------------------------------------------------------------------
# Comptabilite : la vente est distincte de la prestation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_counter_sale_is_booked_apart_from_the_service(api_client, salon_a):
    """Deux metiers, deux marges : le graphique « d'ou vient l'argent »
    n'a d'interet que s'il les distingue."""
    from tests.test_finance_automatic import login

    product, _ = make_store(salon_a, price="12000")
    created = api_client.post(
        "/api/v1/public/bookings",
        booking_payload(
            salon_a,
            next_monday_at(10),
            items=[{"product": str(product.id), "quantity": 1}],
        ),
        format="json",
        headers=HOST,
    )

    login(api_client, salon_a.owner)
    api_client.post(
        f"/api/v1/bookings/{created.data['id']}/status/",
        {"status": Booking.Status.COMPLETED},
        format="json",
    )

    with as_tenant(salon_a.tenant):
        lines = {
            row.source: (row.category, row.amount)
            for row in Transaction.objects.filter(booking_id=created.data["id"])
        }

    assert lines["booking_items"][0] == Transaction.IncomeCategory.PRODUCT
    assert lines["booking_items"][1] == Decimal("12000")
    # Le solde ne compte pas la vente une seconde fois.
    assert lines["booking_balance"][1] == salon_a.service.price_amount


@pytest.mark.django_db
def test_the_total_recorded_never_exceeds_what_was_charged(api_client, salon_a):
    from tests.test_finance_automatic import login

    product, _ = make_store(salon_a, price="12000")
    created = api_client.post(
        "/api/v1/public/bookings",
        booking_payload(
            salon_a,
            next_monday_at(10),
            items=[{"product": str(product.id), "quantity": 2}],
        ),
        format="json",
        headers=HOST,
    )

    login(api_client, salon_a.owner)
    for _ in range(3):
        api_client.post(
            f"/api/v1/bookings/{created.data['id']}/status/",
            {"status": Booking.Status.COMPLETED},
            format="json",
        )

    with as_tenant(salon_a.tenant):
        booking = Booking.objects.get(id=created.data["id"])
        recorded = sum(
            (
                row.amount
                for row in Transaction.objects.filter(
                    booking=booking, kind=Transaction.Kind.INCOME
                )
            ),
            Decimal("0"),
        )

    assert recorded == booking.total_amount


# ---------------------------------------------------------------------------
# Corriger la boutique apres coup
# ---------------------------------------------------------------------------
#
# Un prix bouge, un fournisseur change de reference, une precision manquait.
# Jusqu'ici la boutique ne se remplissait qu'une fois : seul le stock etait
# modifiable, et il fallait supprimer l'article pour en corriger le nom - ce
# qui emportait au passage les fournitures qui le proposaient.


@pytest.mark.django_db
def test_a_price_and_a_name_can_be_corrected(api_client, salon_a):
    from tests.test_dashboard_api import login

    product, _ = make_store(salon_a, price="12000")
    login(api_client, salon_a.owner)

    response = api_client.patch(
        f"/api/v1/products/{product.id}/",
        {"name": "Mèches kanekalon 26 pouces", "price": "15000", "unit": "pack"},
        format="json",
    )

    assert response.status_code == 200, response.data
    with as_tenant(salon_a.tenant):
        product.refresh_from_db()
    assert product.name == "Mèches kanekalon 26 pouces"
    assert product.price == Decimal("15000")
    assert product.unit == Product.Unit.PACK


@pytest.mark.django_db
def test_correcting_an_article_keeps_the_requirement_that_offers_it(
    api_client, salon_a
):
    """C'est tout l'interet de la modification : supprimer puis recreer
    l'article aurait casse le lien avec « 3 paquets de meches »."""
    from tests.test_dashboard_api import login

    product, requirement = make_store(salon_a, price="12000")
    login(api_client, salon_a.owner)

    api_client.patch(
        f"/api/v1/products/{product.id}/", {"price": "15000"}, format="json"
    )

    with as_tenant(salon_a.tenant):
        assert requirement.offers.filter(product=product).exists()


@pytest.mark.django_db
def test_renaming_onto_a_taken_name_is_refused_in_french_not_in_a_500(
    api_client, salon_a
):
    from tests.test_dashboard_api import login

    product, _ = make_store(salon_a)
    with as_tenant(salon_a.tenant):
        other = Product.objects.create(
            tenant=salon_a.tenant, name="Perruque", price=Decimal("50000")
        )
    login(api_client, salon_a.owner)

    response = api_client.patch(
        f"/api/v1/products/{other.id}/", {"name": product.name}, format="json"
    )

    assert response.status_code == 400
    # Le gestionnaire d'exceptions du projet replie les erreurs de champ
    # sous `detail` : c'est cette forme que le tableau de bord sait lire
    # pour afficher la phrase au lieu d'un « une erreur est survenue ».
    assert "déjà ce nom" in str(response.data["detail"]["name"][0])


@pytest.mark.django_db
def test_saving_an_article_without_touching_its_name_is_not_a_duplicate(
    api_client, salon_a
):
    """Le controle d'unicite doit s'exclure lui-meme, sinon corriger un prix
    seul deviendrait impossible."""
    from tests.test_dashboard_api import login

    product, _ = make_store(salon_a, price="12000")
    login(api_client, salon_a.owner)

    response = api_client.patch(
        f"/api/v1/products/{product.id}/",
        {"name": product.name, "price": "13000"},
        format="json",
    )

    assert response.status_code == 200, response.data


@pytest.mark.django_db
def test_two_salons_may_sell_the_same_thing(api_client, salon_a, salon_b):
    """L'unicite vaut dans une boutique, pas sur la plateforme."""
    from tests.test_dashboard_api import login

    make_store(salon_a)
    login(api_client, salon_b.owner)

    response = api_client.post(
        "/api/v1/products/",
        {"name": "Mèches kanekalon", "price": "9000"},
        format="json",
    )

    assert response.status_code == 201, response.data


@pytest.mark.django_db
def test_what_to_bring_can_be_corrected(api_client, salon_a):
    from tests.test_dashboard_api import login

    _, requirement = make_store(salon_a, mandatory=True)
    login(api_client, salon_a.owner)

    response = api_client.patch(
        f"/api/v1/requirements/{requirement.id}/",
        {
            "label": "4 paquets de mèches",
            "detail": "Longueur 26 pouces, couleur 1B",
            "mandatory": False,
        },
        format="json",
    )

    assert response.status_code == 200, response.data
    with as_tenant(salon_a.tenant):
        requirement.refresh_from_db()
    assert requirement.label == "4 paquets de mèches"
    assert requirement.detail == "Longueur 26 pouces, couleur 1B"
    assert requirement.mandatory is False


@pytest.mark.django_db
def test_the_precision_reaches_the_client_before_she_books(api_client, salon_a):
    """La precision existait en base et s'affichait a la reservation, mais
    aucun ecran ne permettait de l'ecrire : elle etait vide pour tout le
    monde."""
    from tests.test_dashboard_api import login

    _, requirement = make_store(salon_a)
    login(api_client, salon_a.owner)
    api_client.patch(
        f"/api/v1/requirements/{requirement.id}/",
        {"detail": "Longueur 26 pouces, couleur 1B"},
        format="json",
    )

    api_client.logout()
    response = api_client.get("/api/v1/public/salon", headers=HOST)

    published = response.data["categories"][0]["services"][0]["requirements"][0]
    assert published["detail"] == "Longueur 26 pouces, couleur 1B"


@pytest.mark.django_db
def test_a_requirement_cannot_be_moved_onto_another_salons_service(
    api_client, salon_a, salon_b
):
    from tests.test_dashboard_api import login

    _, requirement = make_store(salon_a)
    login(api_client, salon_a.owner)

    response = api_client.patch(
        f"/api/v1/requirements/{requirement.id}/",
        {"service": str(salon_b.service.id)},
        format="json",
    )

    assert response.status_code == 400
    with as_tenant(salon_a.tenant):
        requirement.refresh_from_db()
    assert requirement.service_id == salon_a.service.id


@pytest.mark.django_db
def test_a_receptionist_may_read_the_shop_but_not_rewrite_it(api_client, salon_a):
    """La reception vend au comptoir : elle voit les prix, elle ne les fixe
    pas."""
    from apps.accounts.models import Membership
    from tests.factories import MembershipFactory, UserFactory
    from tests.test_dashboard_api import login

    product, _ = make_store(salon_a, price="12000")
    receptionist = UserFactory()
    MembershipFactory(
        tenant=salon_a.tenant,
        user=receptionist,
        role=Membership.Role.RECEPTIONIST,
    )
    login(api_client, receptionist)

    assert api_client.get("/api/v1/products/").status_code == 200
    response = api_client.patch(
        f"/api/v1/products/{product.id}/", {"price": "1"}, format="json"
    )

    assert response.status_code == 403
    with as_tenant(salon_a.tenant):
        product.refresh_from_db()
    assert product.price == Decimal("12000")
