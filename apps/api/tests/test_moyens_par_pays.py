"""Les moyens d'encaissement des acomptes, selon le pays du salon.

- chaque pays reçoit les moyens qui y existent : WeChat Pay et Alipay en
  Chine ; Mobile Money, Orange ou Airtel là où l'opérateur est présent, et
  virement, en Afrique ;
- le serveur refuse de créer un moyen d'un autre pays ;
- un moyen d'un autre pays (le salon a déménagé) est gardé mais n'est plus
  proposé aux clientes : sans autre moyen, la réservation ne passe plus par
  la page de paiement ;
- à Douala comme à Brazzaville, un acompte par Mobile Money va jusqu'au bout :
  page de paiement en XAF entiers, preuve, acceptation par le salon.
"""

from decimal import Decimal

import pytest

from apps.payments.models import PaymentChannel
from apps.payments.moyens import moyens_du_pays
from apps.scheduling.models import Booking
from conftest import as_tenant
from tests.test_deposit_payment import HOST, book, login, require_deposit


def placer(salon, pays, devise="XAF"):
    salon.tenant.country, salon.tenant.currency = pays, devise
    salon.tenant.save(update_fields=["country", "currency"])


def moyen(salon, kind, consigne="MTN MoMo : 06 123 45 67"):
    with as_tenant(salon.tenant):
        return PaymentChannel.objects.create(
            tenant=salon.tenant, kind=kind, account_name="Salon", instructions=consigne
        )


@pytest.mark.parametrize(
    "pays, attendus",
    [
        ("CN", ["wechat", "alipay"]),
        ("CM", ["mobile_money", "orange_money", "bank"]),
        ("CG", ["mobile_money", "airtel_money", "bank"]),
        ("CD", ["mobile_money", "orange_money", "airtel_money", "bank"]),
        ("BJ", ["mobile_money", "bank"]),
    ],
)
def test_chaque_pays_recoit_ses_moyens(pays, attendus):
    assert moyens_du_pays(pays) == attendus


@pytest.mark.django_db
@pytest.mark.parametrize(
    "pays, attendus",
    [("CM", ["mobile_money", "orange_money", "bank"]), ("CN", ["wechat", "alipay"])],
)
def test_le_tableau_de_bord_lit_les_moyens_du_pays(api_client, salon_a, pays, attendus):
    placer(salon_a, pays)
    login(api_client, salon_a.owner)
    reponse = api_client.get(
        "/api/v1/payment-channels/disponibles/", HTTP_X_TENANT_ID=str(salon_a.tenant.pk)
    )
    assert reponse.status_code == 200, reponse.content
    assert [m["kind"] for m in reponse.json()] == attendus


@pytest.mark.django_db
def test_le_serveur_refuse_un_moyen_d_un_autre_pays(api_client, salon_a):
    placer(salon_a, "CG")
    login(api_client, salon_a.owner)
    tete = {"HTTP_X_TENANT_ID": str(salon_a.tenant.pk)}
    for kind in ("wechat", "orange_money"):  # Chine ; Orange n'est pas au Congo
        r = api_client.post("/api/v1/payment-channels/", {"kind": kind}, format="json", **tete)
        assert r.status_code == 400, (kind, r.content)
        assert "pas proposé dans votre pays" in str(r.json())
    for kind in ("mobile_money", "airtel_money", "bank"):
        r = api_client.post("/api/v1/payment-channels/", {"kind": kind}, format="json", **tete)
        assert r.status_code == 201, (kind, r.content)


@pytest.mark.django_db
def test_un_moyen_d_un_autre_pays_n_est_plus_propose(api_client, salon_a):
    """Le salon a quitté la Chine : son QR WeChat reste, mais aucune cliente
    de Brazzaville n'est envoyée le payer."""
    require_deposit(salon_a, amount="5000")
    placer(salon_a, "CG")
    moyen(salon_a, "wechat", consigne="QR")

    login(api_client, salon_a.owner)
    liste = api_client.get(
        "/api/v1/payment-channels/", HTTP_X_TENANT_ID=str(salon_a.tenant.pk)
    ).json()
    assert [(m["kind"], m["propose"]) for m in liste] == [("wechat", False)]
    api_client.logout()

    reponse = book(api_client, salon_a)
    assert reponse.status_code == 201, reponse.data
    assert reponse.data["status"] == Booking.Status.REQUESTED


@pytest.mark.django_db
@pytest.mark.parametrize("pays, operateur", [("CM", "orange_money"), ("CG", "airtel_money")])
def test_un_acompte_mobile_money_en_afrique_de_bout_en_bout(api_client, salon_a, pays, operateur):
    from apps.salons.models import SalonProfile

    placer(salon_a, pays)
    require_deposit(salon_a)
    with as_tenant(salon_a.tenant):
        salon_a.service.price_amount = Decimal("15000")
        salon_a.service.save(update_fields=["price_amount"])
        # 30 % de 15 000 = 4 500 XAF, au-dessus du plancher de 2 000.
        SalonProfile.objects.filter(tenant=salon_a.tenant).update(
            deposit_rate=Decimal("30"), deposit_minimum=Decimal("2000")
        )
    moyen(salon_a, operateur, consigne="06 123 45 67 — votre nom en motif")

    cree = book(api_client, salon_a)
    assert cree.status_code == 201, cree.data
    assert cree.data["status"] == Booking.Status.PENDING_PAYMENT

    page = api_client.get(
        "/api/v1/public/payment", {"token": cree.data["payment_token"]}, headers=HOST
    )
    assert page.status_code == 200, page.content
    donnees = page.json()
    assert [c["kind"] for c in donnees["channels"]] == [operateur]
    assert donnees["channels"][0]["instructions"].startswith("06 123 45 67")
    assert Decimal(donnees["booking"]["deposit_amount"]) == Decimal("4500")

    preuve = api_client.post(
        "/api/v1/public/payment/proof",
        {
            "token": cree.data["payment_token"],
            "channel": operateur,
            "reference": "MP241016.1234.A5",
        },
        format="json",
        headers=HOST,
    )
    assert preuve.status_code in (200, 201), preuve.content

    login(api_client, salon_a.owner)
    with as_tenant(salon_a.tenant):
        booking = Booking.objects.get(pk=cree.data["id"])
        assert booking.status == Booking.Status.REQUESTED
    ok = api_client.post(
        f"/api/v1/bookings/{booking.pk}/accept/",
        {},
        format="json",
        HTTP_X_TENANT_ID=str(salon_a.tenant.pk),
    )
    assert ok.status_code == 200, ok.content
    with as_tenant(salon_a.tenant):
        booking.refresh_from_db()
        assert booking.status == Booking.Status.CONFIRMED
        assert booking.deposit_paid and booking.deposit_received == Decimal("4500")
        assert booking.deposit_method == operateur
