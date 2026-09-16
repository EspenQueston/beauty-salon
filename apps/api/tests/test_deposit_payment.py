"""Le chemin d'un acompte : QR code, preuve, acceptation.

Nous ne voyons jamais le paiement — il va directement du téléphone de la
cliente au compte du salon. Ces tests vérifient donc surtout **qui** peut
faire avancer l'état, et que rien n'avance tout seul.
"""

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from django.core import mail

from apps.finance.models import Transaction
from apps.payments.models import DepositProof, PaymentChannel
from apps.scheduling.models import Booking
from conftest import as_tenant, salon_host

BRAZZAVILLE = ZoneInfo("Africa/Brazzaville")
HOST = {"Host": salon_host("blondrose")}
PASSWORD = "motdepasse-solide"


def login(client, user):
    assert client.login(email=user.email, password=PASSWORD)
    return client


def next_monday_at(hour: int) -> datetime:
    today = datetime.now(BRAZZAVILLE).date()
    ahead = (0 - today.weekday()) % 7 or 7
    day: date = today + timedelta(days=ahead + 7)
    return datetime.combine(day, time(hour, 0), tzinfo=BRAZZAVILLE)


def give_channel(salon, kind=PaymentChannel.Kind.WECHAT):
    with as_tenant(salon.tenant):
        return PaymentChannel.objects.create(
            tenant=salon.tenant,
            kind=kind,
            account_name="Blondrose Salon",
            instructions="Mettez votre nom en commentaire.",
        )


def require_deposit(salon, amount="150"):
    """La prestation demande un acompte, et le salon en fixe le montant.

    Deux endroits, deux roles : la prestation dit oui ou non, la fiche du
    salon dit combien. Le montant passe donc par le plancher, seul reglage
    qui donne une valeur exacte quel que soit le prix."""
    from apps.salons.models import SalonProfile

    with as_tenant(salon.tenant):
        salon.service.requires_deposit = True
        salon.service.save()
        SalonProfile.objects.filter(tenant=salon.tenant).update(
            deposit_rate=0, deposit_minimum=Decimal(amount)
        )


def book(api_client, salon, hour=10, **overrides):
    payload = {
        "service": str(salon.service.id),
        "starts_at": next_monday_at(hour).isoformat(),
        "full_name": "Awa Diallo",
        "phone": "+242066112233",
        "email": "awa@example.com",
        "accepts_policy": True,
    }
    payload.update(overrides)
    return api_client.post(
        "/api/v1/public/bookings", payload, format="json", headers=HOST
    )


# ---------------------------------------------------------------------------
# Quand la page de paiement s'ouvre, et quand elle ne s'ouvre pas
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_deposit_and_a_qr_code_send_the_booking_to_payment(api_client, salon_a):
    require_deposit(salon_a)
    give_channel(salon_a)

    response = book(api_client, salon_a)

    assert response.status_code == 201, response.data
    assert response.data["status"] == Booking.Status.PENDING_PAYMENT
    assert response.data["payment_token"]


@pytest.mark.django_db
def test_without_a_qr_code_nothing_changes(api_client, salon_a):
    """Un salon sans moyen d'encaisser encaisse sur place, comme avant.

    L'envoyer sur une page de paiement qui ne montre rien serait une impasse.
    """
    require_deposit(salon_a)

    response = book(api_client, salon_a)

    assert response.data["status"] == Booking.Status.REQUESTED
    assert response.data["payment_token"] == ""


@pytest.mark.django_db
def test_without_a_deposit_nothing_changes(api_client, salon_a):
    give_channel(salon_a)
    with as_tenant(salon_a.tenant):
        salon_a.service.requires_deposit = False
        salon_a.service.save()

    response = book(api_client, salon_a)

    assert response.data["status"] == Booking.Status.REQUESTED


@pytest.mark.django_db
def test_a_channel_without_qr_or_instructions_is_not_offered(api_client, salon_a):
    """Un moyen activé mais entièrement vide n'est qu'une impasse."""
    require_deposit(salon_a)
    with as_tenant(salon_a.tenant):
        PaymentChannel.objects.create(
            tenant=salon_a.tenant, kind=PaymentChannel.Kind.ALIPAY
        )

    response = book(api_client, salon_a)

    assert response.data["status"] == Booking.Status.REQUESTED


# ---------------------------------------------------------------------------
# Le jeton : ce qu'il ouvre, et ce qu'il n'ouvre pas
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_token_shows_the_amount_and_the_qr_codes(api_client, salon_a):
    require_deposit(salon_a)
    give_channel(salon_a)
    created = book(api_client, salon_a)

    response = api_client.get(
        "/api/v1/public/payment",
        {"token": created.data["payment_token"]},
        headers=HOST,
    )

    assert response.status_code == 200
    assert response.data["booking"]["deposit_amount"] == "150.00"
    assert response.data["channels"][0]["kind"] == "wechat"
    assert response.data["proof"] is None


@pytest.mark.django_db
@pytest.mark.parametrize("token", ["", "n-importe-quoi", "eyJib29raW5nIjogIngifQ:fake"])
def test_a_forged_or_missing_token_opens_nothing(api_client, salon_a, token):
    """Un identifiant deviné ne doit ouvrir le rendez-vous de personne."""
    response = api_client.get("/api/v1/public/payment", {"token": token}, headers=HOST)

    assert response.status_code == 404
    assert response.data["code"] == "invalid_token"


@pytest.mark.django_db
def test_an_expired_token_opens_nothing(api_client, salon_a, monkeypatch):
    require_deposit(salon_a)
    give_channel(salon_a)
    created = book(api_client, salon_a)

    # Le jeton n'est pas une session : il expire.
    monkeypatch.setattr("apps.payments.tokens.TOKEN_MAX_AGE", -1)
    response = api_client.get(
        "/api/v1/public/payment",
        {"token": created.data["payment_token"]},
        headers=HOST,
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# La preuve : la cliente dit avoir payé
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_sending_a_proof_puts_the_booking_in_the_salons_hands(api_client, salon_a):
    require_deposit(salon_a)
    give_channel(salon_a)
    created = book(api_client, salon_a)
    mail.outbox.clear()

    response = api_client.post(
        "/api/v1/public/payment/proof",
        {
            "token": created.data["payment_token"],
            "channel": "wechat",
            "reference": "4200002145",
        },
        format="json",
        headers=HOST,
    )

    assert response.status_code == 201, response.data
    with as_tenant(salon_a.tenant):
        booking = Booking.objects.get(id=created.data["id"])
        proof = DepositProof.objects.get(booking=booking)

    # La balle est dans le camp du salon — rien n'est confirmé.
    assert booking.status == Booking.Status.REQUESTED
    assert booking.deposit_paid is False
    assert proof.status == DepositProof.Status.SUBMITTED
    assert proof.reference == "4200002145"


@pytest.mark.django_db
def test_the_salon_is_warned_that_money_is_waiting(api_client, salon_a):
    """La notification la plus urgente du produit : une cliente a envoyé de
    l'argent et attend une réponse."""
    require_deposit(salon_a)
    give_channel(salon_a)
    created = book(api_client, salon_a)
    mail.outbox.clear()

    api_client.post(
        "/api/v1/public/payment/proof",
        {"token": created.data["payment_token"], "channel": "wechat"},
        format="json",
        headers=HOST,
    )

    alerts = [m for m in mail.outbox if "Acompte à vérifier" in m.subject]
    assert alerts, [m.subject for m in mail.outbox]
    assert salon_a.owner.email in alerts[0].to


@pytest.mark.django_db
def test_a_proof_on_a_cancelled_booking_is_refused(api_client, salon_a):
    require_deposit(salon_a)
    give_channel(salon_a)
    created = book(api_client, salon_a)

    with as_tenant(salon_a.tenant):
        booking = Booking.objects.get(id=created.data["id"])
        booking.status = Booking.Status.CANCELLED
        booking.save()

    response = api_client.post(
        "/api/v1/public/payment/proof",
        {"token": created.data["payment_token"]},
        format="json",
        headers=HOST,
    )

    assert response.status_code == 400
    assert response.data["code"] == "proof_refused"


# ---------------------------------------------------------------------------
# L'acceptation : le salon confirme l'argent ET la prestation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_accepting_confirms_the_booking_and_books_the_deposit(api_client, salon_a):
    require_deposit(salon_a)
    give_channel(salon_a)
    created = book(api_client, salon_a)
    api_client.post(
        "/api/v1/public/payment/proof",
        {"token": created.data["payment_token"], "channel": "wechat"},
        format="json",
        headers=HOST,
    )

    login(api_client, salon_a.owner)
    response = api_client.post(
        f"/api/v1/bookings/{created.data['id']}/accept/", {}, format="json"
    )

    assert response.status_code == 200, response.data
    with as_tenant(salon_a.tenant):
        booking = Booking.objects.get(id=created.data["id"])
        line = Transaction.objects.get(
            booking=booking, source=Transaction.Source.BOOKING_DEPOSIT
        )

    assert booking.status == Booking.Status.CONFIRMED
    assert booking.deposit_paid is True
    assert booking.deposit_received == Decimal("150")
    # L'acompte entre en caisse le jour où il est constaté.
    assert line.amount == Decimal("150")


@pytest.mark.django_db
def test_accepting_a_partial_deposit_records_what_arrived(api_client, salon_a):
    require_deposit(salon_a)
    give_channel(salon_a)
    created = book(api_client, salon_a)

    login(api_client, salon_a.owner)
    api_client.post(
        f"/api/v1/bookings/{created.data['id']}/accept/",
        {"amount": "100", "method": "wechat"},
        format="json",
    )

    with as_tenant(salon_a.tenant):
        booking = Booking.objects.get(id=created.data["id"])
    assert booking.deposit_received == Decimal("100")


@pytest.mark.django_db
def test_rejecting_returns_the_booking_to_payment_without_cancelling(
    api_client, salon_a
):
    """Une capture floue se corrige. Annuler sec ferait perdre une cliente
    qui a peut-être réellement payé."""
    require_deposit(salon_a)
    give_channel(salon_a)
    created = book(api_client, salon_a)
    api_client.post(
        "/api/v1/public/payment/proof",
        {"token": created.data["payment_token"]},
        format="json",
        headers=HOST,
    )

    login(api_client, salon_a.owner)
    response = api_client.post(
        f"/api/v1/bookings/{created.data['id']}/deposit/reject/",
        {"reason": "Aucun versement à ce montant"},
        format="json",
    )

    assert response.status_code == 200
    with as_tenant(salon_a.tenant):
        booking = Booking.objects.get(id=created.data["id"])
        proof = DepositProof.objects.get(booking=booking)

    assert booking.status == Booking.Status.PENDING_PAYMENT
    assert proof.status == DepositProof.Status.REJECTED
    assert proof.rejection_reason == "Aucun versement à ce montant"


@pytest.mark.django_db
def test_she_can_send_a_new_proof_after_a_refusal(api_client, salon_a):
    require_deposit(salon_a)
    give_channel(salon_a)
    created = book(api_client, salon_a)
    token = created.data["payment_token"]

    api_client.post(
        "/api/v1/public/payment/proof", {"token": token}, format="json", headers=HOST
    )
    login(api_client, salon_a.owner)
    api_client.post(
        f"/api/v1/bookings/{created.data['id']}/deposit/reject/",
        {"reason": "Capture illisible"},
        format="json",
    )

    api_client.logout()
    again = api_client.post(
        "/api/v1/public/payment/proof",
        {"token": token, "reference": "4200009999"},
        format="json",
        headers=HOST,
    )

    assert again.status_code == 201
    with as_tenant(salon_a.tenant):
        proof = DepositProof.objects.get(booking_id=created.data["id"])
    # Le refus précédent est effacé : le salon doit regarder à neuf.
    assert proof.status == DepositProof.Status.SUBMITTED
    assert proof.rejection_reason == ""


@pytest.mark.django_db
def test_a_stranger_cannot_accept_a_booking(api_client, salon_a, salon_b):
    require_deposit(salon_a)
    give_channel(salon_a)
    created = book(api_client, salon_a)

    login(api_client, salon_b.owner)
    response = api_client.post(
        f"/api/v1/bookings/{created.data['id']}/accept/", {}, format="json"
    )

    assert response.status_code == 404


@pytest.mark.django_db
def test_an_anonymous_visitor_cannot_accept_a_booking(api_client, salon_a):
    require_deposit(salon_a)
    give_channel(salon_a)
    created = book(api_client, salon_a)

    response = api_client.post(
        f"/api/v1/bookings/{created.data['id']}/accept/", {}, format="json"
    )

    assert response.status_code in (401, 403)


# ---------------------------------------------------------------------------
# L'expiration : rendre les créneaux que personne n'a payés
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_an_unpaid_slot_is_released_after_the_window(api_client, salon_a):
    from apps.payments.services import PAYMENT_WINDOW, release_expired

    require_deposit(salon_a)
    give_channel(salon_a)
    created = book(api_client, salon_a)

    with as_tenant(salon_a.tenant):
        booking = Booking.objects.get(id=created.data["id"])
        # On recule la création au-delà du délai.
        Booking.objects.filter(id=booking.id).update(
            created_at=booking.created_at - PAYMENT_WINDOW - timedelta(minutes=1)
        )

        assert release_expired() == 1
        booking.refresh_from_db()

    assert booking.status == Booking.Status.CANCELLED


@pytest.mark.django_db
def test_a_slot_with_a_proof_is_never_released(api_client, salon_a):
    """Elle attend le salon, pas l'inverse : lui reprendre son créneau
    serait injuste."""
    from apps.payments.services import PAYMENT_WINDOW, release_expired

    require_deposit(salon_a)
    give_channel(salon_a)
    created = book(api_client, salon_a)
    api_client.post(
        "/api/v1/public/payment/proof",
        {"token": created.data["payment_token"]},
        format="json",
        headers=HOST,
    )

    with as_tenant(salon_a.tenant):
        booking = Booking.objects.get(id=created.data["id"])
        Booking.objects.filter(id=booking.id).update(
            created_at=booking.created_at - PAYMENT_WINDOW - timedelta(hours=5)
        )

        assert release_expired() == 0
        booking.refresh_from_db()

    assert booking.status == Booking.Status.REQUESTED


@pytest.mark.django_db
def test_a_pending_payment_still_holds_the_slot(api_client, salon_a):
    """Une cliente qui cherche son mot de passe WeChat ne doit pas se faire
    prendre son créneau."""
    require_deposit(salon_a)
    give_channel(salon_a)
    first = book(api_client, salon_a, hour=10)
    assert first.status_code == 201

    second = book(api_client, salon_a, hour=10, phone="+242066999888")

    assert second.status_code == 409


# ---------------------------------------------------------------------------
# Les QR codes appartiennent au salon
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_salon_never_sees_another_salons_qr_code(api_client, salon_a, salon_b):
    give_channel(salon_a, PaymentChannel.Kind.WECHAT)
    give_channel(salon_b, PaymentChannel.Kind.ALIPAY)

    login(api_client, salon_a.owner)
    response = api_client.get("/api/v1/payment-channels/")

    kinds = [row["kind"] for row in response.data]
    assert kinds == ["wechat"]


@pytest.mark.django_db
def test_the_front_desk_reads_the_channels_but_does_not_change_them(
    api_client, salon_a
):
    from apps.accounts.models import Membership
    from tests.factories import MembershipFactory, UserFactory

    give_channel(salon_a)
    receptionist = UserFactory()
    MembershipFactory(
        tenant=salon_a.tenant, user=receptionist, role=Membership.Role.RECEPTIONIST
    )
    login(api_client, receptionist)

    assert api_client.get("/api/v1/payment-channels/").status_code == 200
    assert (
        api_client.post(
            "/api/v1/payment-channels/", {"kind": "alipay"}, format="json"
        ).status_code
        == 403
    )
