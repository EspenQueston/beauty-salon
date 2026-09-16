"""Avis clientes : qui peut ecrire, qui peut lire, qui peut retirer."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.reviews.models import Review
from apps.reviews.services import make_token
from apps.scheduling.models import Booking
from conftest import as_tenant, salon_host
from tests.factories import BookingFactory

PASSWORD = "motdepasse-solide"


def completed_booking(salon, **overrides):
    """Rendez-vous honore hier : le cas normal pour laisser un avis."""
    starts_at = timezone.now() - timedelta(days=1)
    with as_tenant(salon.tenant):
        return BookingFactory(
            tenant=salon.tenant,
            customer=salon.customer,
            staff_member=salon.staff,
            service=salon.service,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=60),
            **{"status": Booking.Status.COMPLETED, **overrides},
        )


@pytest.mark.django_db
def test_a_completed_booking_can_be_reviewed(api_client, salon_a):
    booking = completed_booking(salon_a)

    response = api_client.post(
        "/api/v1/public/reviews/create",
        {
            "token": make_token(booking.id),
            "rating_result": 5,
            "rating_welcome": 5,
            "comment": "Travail impeccable.",
        },
        format="json",
        headers={"Host": salon_host(salon_a.tenant.slug)},
    )

    assert response.status_code == 201, response.data
    assert response.data["rating"] == 5

    with as_tenant(salon_a.tenant):
        review = Review.objects.get(booking=booking)
    assert review.status == Review.Status.PUBLISHED
    # La signature est recopiee : corriger le fichier clientes plus tard ne
    # doit pas changer l'auteur d'un avis deja publie.
    assert review.author_name == salon_a.customer.full_name


@pytest.mark.django_db
def test_a_booking_not_yet_honoured_cannot_be_reviewed(api_client, salon_a):
    """On ne note pas une prestation qu'on n'a pas encore recue."""
    starts_at = timezone.now() + timedelta(days=2)
    with as_tenant(salon_a.tenant):
        booking = BookingFactory(
            tenant=salon_a.tenant,
            customer=salon_a.customer,
            staff_member=salon_a.staff,
            service=salon_a.service,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=60),
            status=Booking.Status.CONFIRMED,
        )

    response = api_client.post(
        "/api/v1/public/reviews/create",
        {"token": make_token(booking.id), "rating_result": 5},
        format="json",
        headers={"Host": salon_host(salon_a.tenant.slug)},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "not_eligible"


@pytest.mark.django_db
def test_the_same_booking_cannot_be_reviewed_twice(api_client, salon_a):
    booking = completed_booking(salon_a)
    token = make_token(booking.id)
    host = {"Host": salon_host(salon_a.tenant.slug)}

    first = api_client.post(
        "/api/v1/public/reviews/create",
        {"token": token, "rating_result": 5},
        format="json",
        headers=host,
    )
    second = api_client.post(
        "/api/v1/public/reviews/create",
        {"token": token, "rating_result": 1},
        format="json",
        headers=host,
    )

    assert first.status_code == 201
    assert second.status_code == 409
    with as_tenant(salon_a.tenant):
        assert Review.objects.count() == 1


@pytest.mark.django_db
def test_a_forged_token_is_refused(api_client, salon_a):
    response = api_client.post(
        "/api/v1/public/reviews/create",
        {"token": "pas-un-jeton-signe", "rating_result": 5},
        format="json",
        headers={"Host": salon_host(salon_a.tenant.slug)},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_token"


@pytest.mark.django_db
def test_only_published_reviews_are_public(api_client, salon_a):
    booking = completed_booking(salon_a)
    with as_tenant(salon_a.tenant):
        Review.objects.create(
            tenant=salon_a.tenant,
            booking=booking,
            customer=salon_a.customer,
            author_name="Sandra",
            rating=2,
            comment="Bof.",
            status=Review.Status.HIDDEN,
        )

    response = api_client.get(
        "/api/v1/public/reviews", headers={"Host": salon_host(salon_a.tenant.slug)}
    )

    assert response.status_code == 200
    assert response.data["count"] == 0
    assert response.data["average"] is None
    assert response.data["results"] == []


@pytest.mark.django_db
def test_the_salon_reads_its_reviews_but_cannot_delete_them(api_client, salon_a):
    """La moderation appartient a la plateforme, pas au commerce note.

    Un salon capable de retirer les avis qui le derangent ne publierait que
    des cinq etoiles, et la note cesserait d'informer.
    """
    booking = completed_booking(salon_a)
    with as_tenant(salon_a.tenant):
        review = Review.objects.create(
            tenant=salon_a.tenant,
            booking=booking,
            customer=salon_a.customer,
            author_name="Sandra",
            rating=3,
            comment="Correct.",
        )

    assert api_client.login(email=salon_a.owner.email, password=PASSWORD)

    listing = api_client.get("/api/v1/reviews/")
    assert listing.status_code == 200
    assert len(listing.data) == 1
    assert listing.data[0]["rating"] == 3

    # 404 et non 405 : le routeur ne genere aucune route de detail pour un
    # viewset qui n'expose que la liste. La suppression n'est pas refusee,
    # elle n'existe pas — garantie plus forte qu'une methode interdite.
    assert api_client.delete(f"/api/v1/reviews/{review.id}/").status_code == 404
    assert (
        api_client.patch(
            f"/api/v1/reviews/{review.id}/", {"status": "hidden"}, format="json"
        ).status_code
        == 404
    )


@pytest.mark.django_db
def test_a_review_token_does_not_work_on_another_salon(api_client, salon_a, salon_b):
    """Le jeton designe un rendez-vous ; l'hote designe un salon.

    Presenter le jeton du salon A sur l'hote du salon B doit echouer : sans
    cela, le contexte tenant de la requete ecrirait l'avis chez le mauvais
    commerce.
    """
    booking = completed_booking(salon_a)

    response = api_client.post(
        "/api/v1/public/reviews/create",
        {"token": make_token(booking.id), "rating_result": 5},
        format="json",
        headers={"Host": salon_host(salon_b.tenant.slug)},
    )

    assert response.status_code == 404
    with as_tenant(salon_a.tenant):
        assert Review.objects.count() == 0


# ---------------------------------------------------------------------------
# Cinq criteres, et une note d'ensemble qui en decoule
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_overall_rating_is_the_average_of_the_criteria(api_client, salon_a):
    """La note d'ensemble n'est pas demandee : elle se calcule.

    L'accepter du client permettrait a un avis de porter « 5 sur 5 » au-dessus
    de cinq criteres a 1, et ce serait cette note-la qui compterait dans la
    moyenne publique du salon.
    """
    booking = completed_booking(salon_a)

    response = api_client.post(
        "/api/v1/public/reviews/create",
        {
            "token": make_token(booking.id),
            "rating_result": 5,
            "rating_welcome": 4,
            "rating_punctuality": 2,
            "rating_cleanliness": 5,
            "rating_value": 4,
        },
        format="json",
        headers={"Host": salon_host("blondrose")},
    )

    assert response.status_code == 201, response.data
    # (5 + 4 + 2 + 5 + 4) / 5 = 4,0
    assert response.data["rating"] == 4

    with as_tenant(salon_a.tenant):
        review = Review.objects.get()
    assert review.rating_punctuality == 2
    assert review.rating_value == 4


@pytest.mark.django_db
def test_a_half_point_average_rounds_up(api_client, salon_a):
    """3,5 donne 4, et non 3.

    Sur une echelle a cinq crans, une demi-note perdue se voit : elle fait
    passer un salon correct pour un salon moyen.
    """
    booking = completed_booking(salon_a)

    response = api_client.post(
        "/api/v1/public/reviews/create",
        {
            "token": make_token(booking.id),
            "rating_result": 4,
            "rating_welcome": 3,
        },
        format="json",
        headers={"Host": salon_host("blondrose")},
    )

    assert response.status_code == 201, response.data
    assert response.data["rating"] == 4


@pytest.mark.django_db
def test_a_criterion_left_blank_does_not_count_as_zero(api_client, salon_a):
    """Une cliente sans avis sur un critere le laisse vide.

    Compter ce vide comme un zero - ou comme un 3 par defaut - ferait dire a
    la moyenne quelque chose que personne n'a voulu dire.
    """
    booking = completed_booking(salon_a)

    response = api_client.post(
        "/api/v1/public/reviews/create",
        {
            "token": make_token(booking.id),
            "rating_result": 5,
            "rating_welcome": 5,
            "rating_punctuality": None,
            "rating_cleanliness": None,
            "rating_value": None,
        },
        format="json",
        headers={"Host": salon_host("blondrose")},
    )

    assert response.status_code == 201, response.data
    assert response.data["rating"] == 5
    assert [row["field"] for row in response.data["detail"]] == [
        "rating_result",
        "rating_welcome",
    ]


@pytest.mark.django_db
def test_an_avis_without_any_star_is_refused(api_client, salon_a):
    """Zero critere note ne fait pas un avis : il n'y aurait rien a moyenner."""
    booking = completed_booking(salon_a)

    response = api_client.post(
        "/api/v1/public/reviews/create",
        {"token": make_token(booking.id), "comment": "Bien."},
        format="json",
        headers={"Host": salon_host("blondrose")},
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_the_public_summary_carries_a_per_criterion_average(api_client, salon_a):
    """« 3,8 sur 5 » ne dit pas quoi reparer ; le detail, si."""
    for result, punctuality in ((5, 2), (5, 1)):
        booking = completed_booking(salon_a)
        api_client.post(
            "/api/v1/public/reviews/create",
            {
                "token": make_token(booking.id),
                "rating_result": result,
                "rating_punctuality": punctuality,
            },
            format="json",
            headers={"Host": salon_host("blondrose")},
        )

    response = api_client.get(
        "/api/v1/public/reviews", headers={"Host": salon_host("blondrose")}
    )

    par_critere = {row["field"]: row["average"] for row in response.data["criteria"]}
    assert par_critere["rating_result"] == 5.0
    assert par_critere["rating_punctuality"] == 1.5
    # Un critere que personne n'a note n'apparait pas : le montrer a zero le
    # ferait passer pour catastrophique.
    assert "rating_cleanliness" not in par_critere


# ---------------------------------------------------------------------------
# L'envoi automatique
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_marking_a_booking_completed_sends_the_review_request(api_client, salon_a):
    """C'est le salon qui declenche, en marquant « Terminée ».

    L'envoi etait accroche a l'heure de fin *prevue*, avec quatre heures de
    politesse : une prestation qui debordait recevait sa demande avant d'etre
    finie, et une prestation marquee terminee le lendemain n'en recevait
    aucune.
    """
    from django.core import mail

    # La cliente du jeu d.essai n.a pas d.adresse : sans elle, la demande est
    # marquee envoyee mais aucun courrier ne part - ce qui est le
    # comportement voulu, et ce qui rendrait ce test aveugle.
    with as_tenant(salon_a.tenant):
        salon_a.customer.email = "awa@example.com"
        salon_a.customer.save(update_fields=["email"])

    booking = completed_booking(salon_a, status=Booking.Status.CHECKED_IN)
    assert api_client.login(email=salon_a.owner.email, password=PASSWORD)

    mail.outbox.clear()
    response = api_client.post(
        f"/api/v1/bookings/{booking.id}/status/",
        {"status": "completed"},
        format="json",
        headers={"X-Tenant-Id": str(salon_a.tenant.id)},
    )

    assert response.status_code == 200, response.data
    with as_tenant(salon_a.tenant):
        booking.refresh_from_db()
    assert booking.review_invited_at is not None

    demande = [m for m in mail.outbox if "avis" in m.subject.lower()]
    assert demande, [m.subject for m in mail.outbox]
    # Les criteres sont nommes avant le clic : un bouton seul ne dit pas ce
    # qui attend derriere, et ce qui n.est pas dit est suppose long.
    assert "La ponctualité" in demande[0].body

    # Et dans la version HTML, qui est celle que 95 % des clientes voient.
    # Sans cette verification, une erreur de gabarit passerait inapercue :
    # `send_email` retombe silencieusement sur le texte seul.
    html = "".join(
        content for content, mime in demande[0].alternatives if mime == "text/html"
    )
    assert "La propreté du salon" in html
    assert "Laisser mon avis" in html


@pytest.mark.django_db
def test_marking_completed_twice_does_not_ask_twice(api_client, salon_a):
    """Repasser par « terminee » apres une correction ne relance rien."""
    from django.core import mail

    # La cliente du jeu d.essai n.a pas d.adresse : sans elle, la demande est
    # marquee envoyee mais aucun courrier ne part - ce qui est le
    # comportement voulu, et ce qui rendrait ce test aveugle.
    with as_tenant(salon_a.tenant):
        salon_a.customer.email = "awa@example.com"
        salon_a.customer.save(update_fields=["email"])

    booking = completed_booking(salon_a, status=Booking.Status.CHECKED_IN)
    assert api_client.login(email=salon_a.owner.email, password=PASSWORD)

    for _ in range(2):
        api_client.post(
            f"/api/v1/bookings/{booking.id}/status/",
            {"status": "completed"},
            format="json",
            headers={"X-Tenant-Id": str(salon_a.tenant.id)},
        )

    demandes = [m for m in mail.outbox if "avis" in m.subject.lower()]
    assert len(demandes) == 1, [m.subject for m in mail.outbox]


# ---------------------------------------------------------------------------
# Ce que l'espace cliente propose, et quand il arrete
# ---------------------------------------------------------------------------


def _ligne(api_client, booking):
    """La ligne de cette visite, telle que l'espace cliente la recoit."""
    rows = api_client.get(
        "/api/v1/public/client/bookings", headers={"Host": salon_host("blondrose")}
    ).data["bookings"]
    return next(row for row in rows if row["id"] == str(booking.id))


@pytest.mark.django_db
def test_a_completed_visit_offers_a_review_for_thirty_days(api_client, salon_a):
    """Le bouton n'apparait que sur une visite honoree, et pas indefiniment."""
    from tests.test_checkin_qr import make_client

    booking = completed_booking(salon_a)
    make_client(api_client, salon_a)

    ligne = _ligne(api_client, booking)
    assert ligne["can_review"] is True
    assert ligne["review_token"]
    assert ligne["reviewed"] is False
    # L'echeance accompagne le jeton : une date limite qu'on ne voit pas
    # approcher n'en est pas une.
    assert ligne["review_until"]


@pytest.mark.django_db
def test_an_old_visit_no_longer_offers_a_review(api_client, salon_a):
    """Au-dela de trente jours, le souvenir est trop flou pour noter.

    La ligne reste dans l'historique - c'est une visite reelle - mais sans
    bouton : le proposer ferait cliquer vers un refus.
    """
    from tests.test_checkin_qr import make_client

    booking = completed_booking(salon_a)
    make_client(api_client, salon_a)

    with as_tenant(salon_a.tenant):
        Booking.objects.filter(id=booking.id).update(
            starts_at=timezone.now() - timedelta(days=31),
            ends_at=timezone.now() - timedelta(days=31) + timedelta(hours=1),
        )

    ligne = _ligne(api_client, booking)
    assert ligne["can_review"] is False
    assert ligne["review_token"] == ""


@pytest.mark.django_db
def test_once_reviewed_the_option_disappears(api_client, salon_a):
    """Un avis laisse retire le bouton, et le dit."""
    from tests.test_checkin_qr import make_client

    booking = completed_booking(salon_a)
    make_client(api_client, salon_a)

    api_client.post(
        "/api/v1/public/reviews/create",
        {"token": make_token(booking.id), "rating_result": 5},
        format="json",
        headers={"Host": salon_host("blondrose")},
    )

    ligne = _ligne(api_client, booking)
    assert ligne["reviewed"] is True
    assert ligne["can_review"] is False
    assert ligne["review_token"] == ""


@pytest.mark.django_db
def test_an_upcoming_visit_offers_nothing_to_review(api_client, salon_a):
    """On ne note pas une prestation qui n'a pas eu lieu."""
    from tests.test_checkin_qr import make_client

    starts_at = timezone.now() + timedelta(days=3)
    with as_tenant(salon_a.tenant):
        booking = BookingFactory(
            tenant=salon_a.tenant,
            customer=salon_a.customer,
            staff_member=salon_a.staff,
            service=salon_a.service,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=60),
            status=Booking.Status.CONFIRMED,
        )
    make_client(api_client, salon_a)

    ligne = _ligne(api_client, booking)
    assert ligne["can_review"] is False
    assert ligne["reviewed"] is False
