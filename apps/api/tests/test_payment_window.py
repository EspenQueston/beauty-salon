"""La page de reglement a un debut, une fin, et une porte de sortie.

---------------------------------------------------------------------------
Le probleme que ces regles resolvent
---------------------------------------------------------------------------

Le lien de paiement etait valable six heures et ne savait rien de l'etat du
rendez-vous. Trois situations ordinaires s'y terminaient mal :

  - une cliente fermait l'onglet, le creneau de quatre heures restait gele
    deux heures pour quelqu'un qui ne reviendrait pas ;
  - le salon acceptait le versement, et le lien continuait a proposer de
    payer - la meme somme, une seconde fois ;
  - le delai passait, le lien affichait « ce lien n'est plus valable », sans
    dire si c'etait le creneau qui etait perdu ou juste le lien.

Desormais le jeton n'authentifie que la porteuse. C'est **l'etat du
rendez-vous** qui decide ce que la page a le droit de montrer, et le serveur
le relit a chaque appel.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.payments import services
from apps.payments.models import DepositProof
from apps.payments.services import PAYMENT_WINDOW, PaymentState, release_expired
from apps.payments.tokens import payment_token, status_token
from apps.scheduling.models import Booking
from conftest import as_tenant, salon_host
from tests.factories import BookingFactory

HOST = {"Host": salon_host("blondrose")}


def booking_for(salon, **overrides):
    starts_at = timezone.now() + timedelta(days=3)
    with as_tenant(salon.tenant):
        return BookingFactory(
            tenant=salon.tenant,
            customer=salon.customer,
            staff_member=salon.staff,
            service=salon.service,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=120),
            status=Booking.Status.PENDING_PAYMENT,
            deposit_amount=Decimal("150"),
            **overrides,
        )


def age(salon, booking, minutes: int):
    """Recule la date de creation, pour vieillir le rendez-vous.

    `created_at` est pose automatiquement : on passe par `update` plutot que
    par `save`, qui le reecrirait. Et le tout dans le contexte du salon,
    sans lequel la politique RLS ne montre aucune ligne - le comportement
    voulu, mais qui ressemble ici a « la reservation a disparu ».
    """
    with as_tenant(salon.tenant):
        Booking.objects.filter(id=booking.id).update(
            created_at=timezone.now() - timedelta(minutes=minutes)
        )
        booking.refresh_from_db()
    return booking


# ---------------------------------------------------------------------------
# Trente minutes, et pas six heures
# ---------------------------------------------------------------------------


def test_the_window_is_half_an_hour():
    """Une valeur qu'on lit dans le code doit se lire aussi dans un test.

    Elle se negocie - c'est un arbitrage entre le confort de la cliente et
    le creneau immobilise du salon. La voir affirmee ici oblige a decider de
    la changer, plutot qu'a la changer par inadvertance.
    """
    assert timedelta(minutes=30) == PAYMENT_WINDOW


@pytest.mark.django_db
def test_a_slot_is_still_held_just_before_the_window_closes(salon_a):
    booking = age(salon_a, booking_for(salon_a), minutes=29)

    with as_tenant(salon_a.tenant):
        assert release_expired() == 0
        assert services.payment_state(booking) == PaymentState.PAYABLE


@pytest.mark.django_db
def test_a_slot_is_released_once_the_window_has_closed(salon_a):
    booking = age(salon_a, booking_for(salon_a), minutes=31)

    with as_tenant(salon_a.tenant):
        assert services.payment_state(booking) == PaymentState.EXPIRED
        assert release_expired() == 1
        booking.refresh_from_db()

    assert booking.status == Booking.Status.CANCELLED


@pytest.mark.django_db
def test_sending_a_proof_stops_the_countdown(salon_a):
    """La balle passe dans le camp du salon, et le delai n'a plus de sens.

    Reprendre son creneau a une cliente qui a peut-etre reellement paye
    serait la pire issue du produit : elle a envoye l'argent, et elle perd
    le rendez-vous pendant que personne ne regarde sa capture.
    """
    booking = booking_for(salon_a)
    with as_tenant(salon_a.tenant):
        services.submit_proof(booking=booking, channel="wechat")
    age(salon_a, booking, minutes=180)

    with as_tenant(salon_a.tenant):
        assert services.payment_deadline(booking) is None
        assert services.payment_state(booking) == PaymentState.WAITING
        assert release_expired() == 0


# ---------------------------------------------------------------------------
# Ce que la page a le droit de montrer
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_payment_page_announces_its_own_deadline(api_client, salon_a):
    booking = booking_for(salon_a)

    response = api_client.get(
        f"/api/v1/public/payment?token={payment_token(booking)}", headers=HOST
    )

    assert response.status_code == 200, response.data
    assert response.data["state"] == PaymentState.PAYABLE
    # Le compte a rebours de la page se cale dessus : sans date, il ne
    # resterait qu'un « depechez-vous » sans echeance, qui n'informe pas.
    assert response.data["expires_at"] == booking.created_at + PAYMENT_WINDOW
    assert response.data["status_token"]


@pytest.mark.django_db
def test_the_payment_page_closes_itself_once_the_salon_has_confirmed(
    api_client, salon_a
):
    """C'est la demande centrale : ne jamais proposer de payer deux fois."""
    booking = booking_for(salon_a)
    with as_tenant(salon_a.tenant):
        services.submit_proof(booking=booking, channel="wechat")
        services.accept(booking=booking, actor=salon_a.owner)

    response = api_client.get(
        f"/api/v1/public/payment?token={payment_token(booking)}", headers=HOST
    )

    assert response.status_code == 200, response.data
    assert response.data["state"] == PaymentState.SETTLED
    # Et elle dit ou aller : la page de suivi, qui elle a encore quelque
    # chose a montrer.
    assert response.data["status_token"]


@pytest.mark.django_db
def test_a_refused_payment_reopens_the_page(api_client, salon_a):
    booking = booking_for(salon_a)
    with as_tenant(salon_a.tenant):
        services.submit_proof(booking=booking, channel="wechat")
        services.reject_proof(
            booking=booking, actor=salon_a.owner, reason="Montant différent"
        )

    response = api_client.get(
        f"/api/v1/public/payment?token={payment_token(booking)}", headers=HOST
    )

    assert response.data["state"] == PaymentState.REFUSED
    # Le creneau n'est pas repris : la cliente a peut-etre bien paye.
    assert response.data["expires_at"] is None


# ---------------------------------------------------------------------------
# La page de suivi
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_status_page_opens_with_its_own_token(api_client, salon_a):
    booking = booking_for(salon_a)

    response = api_client.get(
        f"/api/v1/public/booking-status?token={status_token(booking)}", headers=HOST
    )

    assert response.status_code == 200, response.data
    assert response.data["booking"]["service_name"] == booking.service_name
    assert response.data["payment"]["state"] == PaymentState.PAYABLE
    # Tant qu'il reste a payer, le chemin du retour est ouvert.
    assert response.data["payment"]["payment_token"]


@pytest.mark.django_db
def test_the_status_page_refuses_a_token_it_did_not_sign(api_client, salon_a):
    """Un jeton de paiement n'ouvre pas la page de suivi, et reciproquement.

    Les sels different justement pour cela : un jeton vole sur une page
    n'etend pas les droits qu'il donne sur l'autre.
    """
    booking = booking_for(salon_a)

    response = api_client.get(
        f"/api/v1/public/booking-status?token={payment_token(booking)}", headers=HOST
    )

    assert response.status_code == 404


@pytest.mark.django_db
def test_a_status_token_does_not_open_under_another_salon(
    api_client, salon_a, salon_b
):
    """Le jeton dit « ce rendez-vous » ; l'hote dit « ce salon ».

    Les deux doivent concorder. Sans ce controle, un lien legitime ouvert
    sous le sous-domaine d'un concurrent lui montrerait le nom d'une
    cliente et ce qu'elle a paye.
    """
    booking = booking_for(salon_a)

    response = api_client.get(
        f"/api/v1/public/booking-status?token={status_token(booking)}",
        headers={"Host": salon_host("beautybyanna")},
    )

    assert response.status_code == 404


@pytest.mark.django_db
def test_the_status_page_shows_the_pass_only_once_confirmed(api_client, salon_a):
    booking = booking_for(salon_a)

    def lire():
        return api_client.get(
            f"/api/v1/public/booking-status?token={status_token(booking)}",
            headers=HOST,
        ).data

    assert lire()["checkin_token"] == ""

    with as_tenant(salon_a.tenant):
        services.submit_proof(booking=booking, channel="wechat")
        services.accept(booking=booking, actor=salon_a.owner)

    reponse = lire()
    assert reponse["checkin_token"], "le QR d'arrivée manque après confirmation"
    assert reponse["payment"]["deposit_paid"] is True
    # Plus rien a payer, donc plus de chemin vers la page de reglement.
    assert reponse["payment"]["payment_token"] == ""


@pytest.mark.django_db
def test_the_status_page_explains_a_cancellation(api_client, salon_a):
    """Un rendez-vous annule garde une page : c'est la qu'on lit pourquoi."""
    booking = age(salon_a, booking_for(salon_a), minutes=31)
    with as_tenant(salon_a.tenant):
        release_expired()

    response = api_client.get(
        f"/api/v1/public/booking-status?token={status_token(booking)}", headers=HOST
    )

    assert response.status_code == 200
    assert response.data["payment"]["state"] == PaymentState.CANCELLED
    assert response.data["booking"]["cancellation_reason"]


@pytest.mark.django_db
def test_a_rejected_proof_is_explained_on_the_status_page(api_client, salon_a):
    booking = booking_for(salon_a)
    with as_tenant(salon_a.tenant):
        services.submit_proof(booking=booking, channel="wechat")
        services.reject_proof(
            booking=booking, actor=salon_a.owner, reason="Capture illisible"
        )

    response = api_client.get(
        f"/api/v1/public/booking-status?token={status_token(booking)}", headers=HOST
    )

    assert response.data["payment"]["rejection_reason"] == "Capture illisible"
    assert response.data["payment"]["payment_token"], "il faut pouvoir renvoyer"


@pytest.mark.django_db
def test_an_accepted_proof_leaves_no_rejection_reason_behind(api_client, salon_a):
    """Un refus corrige ne doit pas rester affiche apres coup.

    La preuve est un seul enregistrement, reutilise a chaque envoi : le
    motif du refus precedent y survit tant que personne ne l'efface, et
    l'afficher sur un rendez-vous desormais confirme serait absurde.
    """
    booking = booking_for(salon_a)
    with as_tenant(salon_a.tenant):
        services.submit_proof(booking=booking, channel="wechat")
        services.reject_proof(
            booking=booking, actor=salon_a.owner, reason="Capture illisible"
        )
        services.submit_proof(booking=booking, channel="wechat")
        services.accept(booking=booking, actor=salon_a.owner)

    response = api_client.get(
        f"/api/v1/public/booking-status?token={status_token(booking)}", headers=HOST
    )

    assert response.data["payment"]["rejection_reason"] == ""


@pytest.mark.django_db
def test_a_deposit_recorded_by_the_salon_settles_the_page(api_client, salon_a):
    """Sans preuve envoyee, mais acompte encaisse : la page doit se fermer.

    Une cliente peut payer en especes au comptoir. Le salon note
    l'encaissement, et le lien de paiement qu'elle garde dans ses e-mails ne
    doit plus rien lui reclamer.
    """
    booking = booking_for(salon_a)
    with as_tenant(salon_a.tenant):
        booking.deposit_paid = True
        booking.deposit_received = Decimal("150")
        booking.save(update_fields=["deposit_paid", "deposit_received"])

    response = api_client.get(
        f"/api/v1/public/payment?token={payment_token(booking)}", headers=HOST
    )

    assert response.data["state"] == PaymentState.SETTLED


@pytest.mark.django_db
def test_a_proof_cannot_be_sent_once_the_window_has_closed(api_client, salon_a):
    """Le creneau a ete rendu : accepter une capture ferait croire l'inverse."""
    booking = age(salon_a, booking_for(salon_a), minutes=31)
    with as_tenant(salon_a.tenant):
        release_expired()

    response = api_client.post(
        "/api/v1/public/payment/proof",
        {"token": payment_token(booking), "channel": "wechat"},
        format="multipart",
        headers=HOST,
    )

    assert response.status_code == 400
    with as_tenant(salon_a.tenant):
        assert not DepositProof.objects.filter(booking=booking).exists()


@pytest.mark.django_db
def test_the_payment_method_is_named_the_way_a_human_writes_it(api_client, salon_a):
    """« Alipay », pas « alipay ».

    Le moyen vient de deux sources qui ne parlent pas la même langue : les
    choix du modèle quand le salon note un encaissement, le canal de la
    preuve quand il en accepte une. La seconde ne figure pas dans les
    premiers, et la valeur brute s'affichait telle quelle au milieu d'une
    page soignée.
    """
    booking = booking_for(salon_a)
    with as_tenant(salon_a.tenant):
        services.submit_proof(booking=booking, channel="alipay")
        services.accept(booking=booking, actor=salon_a.owner)

    response = api_client.get(
        f"/api/v1/public/booking-status?token={status_token(booking)}", headers=HOST
    )

    assert response.data["payment"]["deposit_method"] == "Alipay"


@pytest.mark.django_db
def test_an_unspecified_payment_method_is_left_unsaid(api_client, salon_a):
    """« Autre » n'apprend rien, sinon qu'on ne sait pas."""
    booking = booking_for(salon_a)
    with as_tenant(salon_a.tenant):
        services.accept(booking=booking, actor=salon_a.owner)

    response = api_client.get(
        f"/api/v1/public/booking-status?token={status_token(booking)}", headers=HOST
    )

    assert response.data["payment"]["deposit_method"] == ""
