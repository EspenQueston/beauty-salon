"""Les notifications WhatsApp, en plus des e-mails.

Ce que ces tests tiennent :

  - un numero n'est accepte qu'avec son indicatif international ;
  - chaque evenement programme un message, un seul, dans la langue de la
    personne, avec son lien et la mention STOP pour la cliente ;
  - la cliente qui a decoche la case, ou repondu STOP, ne recoit rien ;
  - la direction est prevenue des reservations, les proprietaires de leur
    abonnement ;
  - l'envoi passe par Evolution sur l'instance de la plateforme, et une
    passerelle en panne laisse le message a retenter, puis en echec ;
  - sans configuration, rien ne part et la ligne le dit ;
  - le webhook n'accepte que le bon jeton et n'entend que STOP.
"""

from datetime import UTC, datetime, timedelta

import pytest
from django.test import override_settings
from django.urls import reverse

from apps.assistants.evolution import EvolutionIndisponible
from apps.billing import services
from apps.billing.rappels import envoyer_rappels
from apps.notifications import tasks, whatsapp
from apps.notifications.models import DesinscriptionWhatsApp, MessageWhatsApp
from apps.scheduling.models import Booking
from conftest import as_tenant
from tests.test_abonnements import (
    ADMIN,
    _admin,
    _demande,
    abonnement_de,
    medias_temporaires,
    moyens,
    offres,
)
from tests.test_dashboard_api import make_booking

FIXTURES_PARTAGEES = (medias_temporaires, moyens, offres)

CONFIGURE = override_settings(
    WHATSAPP_INSTANCE="beauty-salon",
    EVOLUTION_API_URL="http://evolution.test",
    EVOLUTION_API_KEY="cle-de-test",
)
MIDI = datetime(2027, 3, 10, 11, 0, tzinfo=UTC)


def messages(genre=None):
    qs = MessageWhatsApp.objects.order_by("created_at")
    return list(qs.filter(genre=genre) if genre else qs)


@pytest.fixture
def envoyes(monkeypatch):
    """Remplace l'appel a Evolution : rien ne quitte la machine."""
    journal: list[tuple[str, str]] = []

    def faux(chiffres, texte):
        journal.append((chiffres, texte))
        return f"ID{len(journal)}"

    monkeypatch.setattr(whatsapp, "_envoyer", faux)
    return journal


# ---------------------------------------------------------------------------
# Numeros
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "saisi, attendu",
    [
        ("+86 185 0695 9673", "8618506959673"),
        ("0086 18506959673", "8618506959673"),
        ("+242 06-123-45-67", "242061234567"),
        ("0612345678", None),  # pas d'indicatif : on ne devine pas le pays
        ("+0612345678", None),
        ("+33 6 12 AB", None),
        ("", None),
        (None, None),
    ],
)
def test_le_numero_exige_un_indicatif(saisi, attendu):
    assert whatsapp.numero(saisi) == attendu


# ---------------------------------------------------------------------------
# La cliente
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_la_confirmation_du_salon_part_une_seule_fois_avec_lien_et_stop(
    salon_a, django_capture_on_commit_callbacks
):
    booking = make_booking(salon_a, status=Booking.Status.CONFIRMED, language="fr")

    with django_capture_on_commit_callbacks(execute=True):
        tasks.send_booking_accepted(str(booking.id), str(salon_a.tenant.id))
        tasks.send_booking_accepted(str(booking.id), str(salon_a.tenant.id))

    (message,) = messages("cliente_accepte")
    assert message.numero == salon_a.customer.phone.lstrip("+")
    assert message.texte.startswith("Bonjour ")
    assert "Blond Rose a confirmé votre rendez-vous" in message.texte
    assert "/rendez-vous?token=" in message.texte
    assert message.texte.endswith("Répondez STOP pour ne plus recevoir ces messages.")
    # Sans instance configuree (la suite de tests), la ligne le dit.
    assert message.statut == MessageWhatsApp.Statut.IGNORE
    assert message.erreur == "WhatsApp non configuré."


@pytest.mark.django_db
def test_en_anglais_et_acompte_paye_le_texte_suit(salon_a, django_capture_on_commit_callbacks):
    booking = make_booking(
        salon_a, status=Booking.Status.CONFIRMED, language="en", deposit_paid=True
    )
    with django_capture_on_commit_callbacks(execute=True):
        tasks.send_booking_accepted(str(booking.id), str(salon_a.tenant.id))

    (message,) = messages("cliente_accepte_acompte")
    assert "has received your deposit" in message.texte
    assert message.texte.endswith("Reply STOP to stop receiving these messages.")


@pytest.mark.django_db
def test_un_deplacement_puis_un_autre_sont_annonces_tous_les_deux(
    salon_a, django_capture_on_commit_callbacks
):
    booking = make_booking(salon_a, status=Booking.Status.CONFIRMED)
    with django_capture_on_commit_callbacks(execute=True):
        tasks.send_booking_rescheduled(str(booking.id), str(salon_a.tenant.id))
    with as_tenant(salon_a.tenant):
        booking.starts_at += timedelta(days=1)
        booking.ends_at += timedelta(days=1)
        booking.save(update_fields=["starts_at", "ends_at"])
    with django_capture_on_commit_callbacks(execute=True):
        tasks.send_booking_rescheduled(str(booking.id), str(salon_a.tenant.id))

    assert len(messages("cliente_deplace")) == 2


@pytest.mark.django_db
def test_case_decochee_ou_stop_rien_ne_part(salon_a, django_capture_on_commit_callbacks):
    booking = make_booking(salon_a, status=Booking.Status.CONFIRMED)
    with as_tenant(salon_a.tenant):
        salon_a.customer.notifications_whatsapp = False
        salon_a.customer.save(update_fields=["notifications_whatsapp"])
    with django_capture_on_commit_callbacks(execute=True):
        tasks.send_booking_accepted(str(booking.id), str(salon_a.tenant.id))
    assert messages("cliente_accepte") == []

    with as_tenant(salon_a.tenant):
        salon_a.customer.notifications_whatsapp = True
        salon_a.customer.save(update_fields=["notifications_whatsapp"])
    DesinscriptionWhatsApp.objects.create(numero=salon_a.customer.phone.lstrip("+"))
    with django_capture_on_commit_callbacks(execute=True):
        tasks.send_booking_accepted(str(booking.id), str(salon_a.tenant.id))
    assert messages("cliente_accepte") == []


@pytest.mark.django_db
def test_un_numero_sans_indicatif_n_est_pas_devine(salon_a, django_capture_on_commit_callbacks):
    with as_tenant(salon_a.tenant):
        salon_a.customer.phone = "061234567"
        salon_a.customer.save(update_fields=["phone"])
    booking = make_booking(salon_a, status=Booking.Status.CONFIRMED)
    with django_capture_on_commit_callbacks(execute=True):
        tasks.send_booking_accepted(str(booking.id), str(salon_a.tenant.id))
    assert messages() == []


# ---------------------------------------------------------------------------
# La direction et les proprietaires
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_la_reservation_previent_la_cliente_et_la_direction_dans_sa_langue(
    salon_a, django_capture_on_commit_callbacks
):
    salon_a.owner.phone = "+86 185 0000 1111"
    salon_a.owner.locale = "en"
    salon_a.owner.save(update_fields=["phone", "locale"])
    booking = make_booking(salon_a, status=Booking.Status.REQUESTED)

    with django_capture_on_commit_callbacks(execute=True):
        tasks.send_booking_notifications(str(booking.id), str(salon_a.tenant.id))

    (cliente,) = messages("cliente_demande")
    assert "Le salon vous confirme très vite." in cliente.texte
    (pro,) = messages("pro_reservation")
    assert pro.numero == "8618500001111"
    assert pro.texte.startswith("New booking at Blond Rose:")
    assert "STOP" not in pro.texte


@pytest.mark.django_db
def test_sans_telephone_de_compte_le_numero_du_salon_sert_de_repli(
    salon_a, django_capture_on_commit_callbacks
):
    with as_tenant(salon_a.tenant):
        salon_a.profile.whatsapp_number = "+242 06 999 88 77"
        salon_a.profile.save(update_fields=["whatsapp_number"])
    booking = make_booking(salon_a, status=Booking.Status.CONFIRMED)
    with django_capture_on_commit_callbacks(execute=True):
        tasks.send_booking_notifications(str(booking.id), str(salon_a.tenant.id))

    (pro,) = messages("pro_reservation")
    assert pro.numero == "242069998877"


@pytest.mark.django_db
def test_le_rappel_d_abonnement_dit_dans_combien_de_jours(salon_a, offres):
    salon_a.owner.phone = "+242061112233"
    salon_a.owner.save(update_fields=["phone"])
    abonnement_de(salon_a, fin=MIDI + timedelta(days=6, hours=20))

    envoyer_rappels(MIDI)
    envoyer_rappels(MIDI + timedelta(hours=1))

    (rappel,) = messages("pro_trial")
    assert rappel.texte.startswith("Votre essai gratuit Beauty Salon se termine dans 7 jours, le ")


@ADMIN
def test_le_paiement_valide_est_annonce_aux_proprietaires(salon_a, moyens):
    salon_a.owner.phone = "+242061112233"
    salon_a.owner.save(update_fields=["phone"])
    abonnement_de(salon_a, fin=datetime.now(UTC) - timedelta(days=1))
    demande = _demande(salon_a, moyens["momo"], reference="REF-WA-1")
    services.approuver_paiement(demande.id, administrateur=_admin())

    (valide,) = messages("pro_abo_valide")
    assert valide.texte.startswith("Paiement validé : votre abonnement Beauty Salon (")
    assert "actif jusqu'au" in valide.texte


# ---------------------------------------------------------------------------
# L'envoi
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_configure_le_message_part_par_evolution(
    salon_a, envoyes, django_capture_on_commit_callbacks
):
    booking = make_booking(salon_a, status=Booking.Status.CONFIRMED)
    with CONFIGURE, django_capture_on_commit_callbacks(execute=True):
        tasks.send_booking_accepted(str(booking.id), str(salon_a.tenant.id))

    (message,) = messages("cliente_accepte")
    assert message.statut == MessageWhatsApp.Statut.ENVOYE
    assert message.identifiant == "ID1" and message.tentatives == 1
    assert envoyes == [(message.numero, message.texte)]


@pytest.mark.django_db
def test_une_passerelle_en_panne_laisse_le_message_a_retenter_puis_en_echec(
    salon_a, monkeypatch
):
    def panne(chiffres, texte):
        raise EvolutionIndisponible("Passerelle WhatsApp injoignable.")

    monkeypatch.setattr(whatsapp, "_envoyer", panne)
    message = MessageWhatsApp.objects.create(
        cle="test:panne", genre="cliente_rappel", numero="242061112233", texte="Bonjour"
    )
    with CONFIGURE:
        assert whatsapp.envoyer(str(message.pk)) == "retenter"
    message.refresh_from_db()
    assert message.statut == MessageWhatsApp.Statut.EN_ATTENTE and message.tentatives == 1

    whatsapp.abandonner(str(message.pk))
    message.refresh_from_db()
    assert message.statut == MessageWhatsApp.Statut.ECHEC


@pytest.mark.django_db
def test_un_message_deja_envoye_ne_repart_pas(envoyes):
    message = MessageWhatsApp.objects.create(
        cle="test:deja", genre="cliente_rappel", numero="242061112233", texte="Bonjour",
        statut=MessageWhatsApp.Statut.ENVOYE,
    )
    with CONFIGURE:
        assert whatsapp.envoyer(str(message.pk)) == "deja-traite"
    assert envoyes == []


# ---------------------------------------------------------------------------
# STOP
# ---------------------------------------------------------------------------


def _reponse(texte, de="242061112233"):
    return {
        "event": "messages.upsert",
        "data": {
            "key": {"remoteJid": f"{de}@s.whatsapp.net", "fromMe": False, "id": "A1"},
            "message": {"conversation": texte},
        },
    }


@pytest.mark.django_db
def test_stop_desinscrit_le_numero_et_le_reste_est_ignore(client):
    url = reverse("webhook-whatsapp-plateforme", args=["bon-jeton"])

    def poster(adresse, texte):
        return client.post(adresse, _reponse(texte), content_type="application/json").status_code

    # Sans jeton configure, l'adresse n'existe pas.
    assert poster(url, "STOP") == 404

    with override_settings(WHATSAPP_WEBHOOK_TOKEN="bon-jeton"):
        mauvais = reverse("webhook-whatsapp-plateforme", args=["mauvais"])
        assert poster(mauvais, "STOP") == 404
        assert poster(url, "Merci !") == 200
        assert not DesinscriptionWhatsApp.objects.exists()
        assert poster(url, " Stop. ") == 200
        assert poster(url, "STOP") == 200

    assert list(DesinscriptionWhatsApp.objects.values_list("numero", flat=True)) == ["242061112233"]


# ---------------------------------------------------------------------------
# Le formulaire de reservation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_la_case_du_formulaire_decide_pour_la_fiche(api_client, salon_a):
    from apps.customers.models import Customer
    from tests.test_public_booking_api import HOST, booking_payload, next_weekday_at

    # Cochee par defaut : un formulaire qui ne l'envoie pas vaut « oui ».
    reponse = api_client.post(
        "/api/v1/public/bookings",
        booking_payload(salon_a, next_weekday_at(10)),
        format="json",
        headers=HOST,
    )
    assert reponse.status_code == 201, reponse.data
    assert messages("cliente_demande")[0].numero == "242066112233"

    # Decochee a la reservation suivante : la fiche suit, rien ne part plus.
    reponse = api_client.post(
        "/api/v1/public/bookings",
        booking_payload(salon_a, next_weekday_at(14), notifications_whatsapp=False),
        format="json",
        headers=HOST,
    )
    assert reponse.status_code == 201, reponse.data
    with as_tenant(salon_a.tenant):
        assert Customer.objects.get(phone="+242066112233").notifications_whatsapp is False
    assert len(messages("cliente_demande")) == 1
