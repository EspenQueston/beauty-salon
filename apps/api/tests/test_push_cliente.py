"""Les notifications sur l'appareil d'une cliente.

Les e-mails ne changent pas ; ces tests tiennent ce que le push y ajoute :
qui le recoit (le compte rattache a la fiche du rendez-vous, et lui seul),
dans quelle langue, vers quelle page — et que seule une cliente inscrit un
appareil a cette portee.
"""

import pytest

from apps.accounts.models import Membership
from apps.clients.models import ClientProfile, ClientSalonLink
from apps.notifications import tasks
from apps.notifications.models import PushSubscription
from apps.scheduling.models import Booking
from tests.factories import UserFactory
from tests.test_dashboard_api import make_booking

ENDPOINT = "https://fcm.googleapis.com/fcm/send/jeton-cliente-1"


@pytest.fixture
def pousses(monkeypatch):
    envois: list[tuple] = []
    monkeypatch.setattr(tasks.pousser_notification, "delay", lambda *args: envois.append(args))
    return envois


def cliente_de(salon):
    compte = UserFactory()
    ClientProfile.objects.create(user=compte)
    ClientSalonLink.objects.create(user=compte, tenant=salon.tenant, customer_id=salon.customer.id)
    return compte


@pytest.mark.django_db
def test_la_confirmation_part_sur_l_appareil_de_la_cliente(
    salon_a, pousses, django_capture_on_commit_callbacks
):
    compte = cliente_de(salon_a)
    autre = UserFactory()  # un compte sans lien : jamais vise
    booking = make_booking(salon_a, status=Booking.Status.CONFIRMED, language="fr")

    with django_capture_on_commit_callbacks(execute=True):
        tasks.send_booking_accepted(str(booking.id), str(salon_a.tenant.id))

    ((comptes, portee, charge),) = pousses
    assert comptes == [str(compte.id)] and str(autre.id) not in comptes
    assert portee == "cliente"
    assert charge["titre"].startswith("Rendez-vous confirmé")
    assert charge["lien"] == "/compte#rendez-vous"


@pytest.mark.django_db
def test_en_anglais_le_texte_et_le_lien_suivent(
    salon_a, pousses, django_capture_on_commit_callbacks
):
    cliente_de(salon_a)
    booking = make_booking(salon_a, status=Booking.Status.CONFIRMED, language="en")

    with django_capture_on_commit_callbacks(execute=True):
        tasks.send_booking_rescheduled(str(booking.id), str(salon_a.tenant.id))

    ((_, _, charge),) = pousses
    assert charge["titre"].startswith("Appointment moved")
    assert charge["lien"] == "/en/compte#rendez-vous"


@pytest.mark.django_db
def test_sans_compte_ou_quand_elle_annule_elle_meme_rien_ne_part(
    salon_a, pousses, django_capture_on_commit_callbacks
):
    booking = make_booking(salon_a, status=Booking.Status.CONFIRMED)
    with django_capture_on_commit_callbacks(execute=True):
        tasks.send_booking_accepted(str(booking.id), str(salon_a.tenant.id))
    assert pousses == []

    cliente_de(salon_a)
    with django_capture_on_commit_callbacks(execute=True):
        tasks.send_booking_cancelled(str(booking.id), str(salon_a.tenant.id), by_salon=False)
    assert pousses == []

    with django_capture_on_commit_callbacks(execute=True):
        tasks.send_booking_cancelled(str(booking.id), str(salon_a.tenant.id), by_salon=True)
    assert len(pousses) == 1 and pousses[0][2]["genre"] == "cliente_annule"


@pytest.mark.django_db
def test_seule_une_cliente_inscrit_un_appareil_a_sa_portee(api_client, salon_a, settings):
    abonnement = {
        "endpoint": ENDPOINT,
        "cle_p256dh": "B" * 87,
        "cle_auth": "A" * 22,
        "portee": "cliente",
    }
    api_client.force_login(salon_a.owner)
    assert salon_a.tenant.memberships.filter(role=Membership.Role.OWNER).exists()
    assert api_client.post("/api/v1/push", abonnement, format="json").status_code == 403

    compte = cliente_de(salon_a)
    api_client.force_login(compte)
    reponse = api_client.post("/api/v1/push", abonnement, format="json")

    assert reponse.status_code == 201, reponse.json()
    assert PushSubscription.objects.get().portee == PushSubscription.Portee.CLIENTE


@pytest.mark.django_db
def test_la_session_repond_aux_visiteuses_sans_erreur(api_client, salon_a):
    """L'icône du compte la lit sur chaque page : jamais de 403 pour une visiteuse."""
    from conftest import salon_host

    hote = {"X-Tenant-Host": salon_host(salon_a.tenant.slug)}
    anonyme = api_client.get("/api/v1/public/client/session", headers=hote)

    compte = cliente_de(salon_a)
    api_client.force_login(compte)
    connectee = api_client.get("/api/v1/public/client/session", headers=hote)

    assert anonyme.status_code == 200 and anonyme.json() == {"connecte": False}
    assert connectee.json()["connecte"] is True and connectee.json()["is_client"] is True
