"""Annuler et deplacer un rendez-vous.

---------------------------------------------------------------------------
Les deux trous que ces tests ferment
---------------------------------------------------------------------------

`reschedule_booking` existait, etait teste, et n'etait appele par aucun
ecran. Il lui manquait par ailleurs trois choses qu'on ne voit qu'en
l'utilisant : il acceptait de deplacer un rendez-vous deja termine ou
annule, il ne prevenait pas la cliente, et il laissait `reminder_sent_at`
en place — donc pas de rappel pour la nouvelle date.

Cote cliente, le salon publiait « annulation gratuite jusqu'a 24 h avant »
sans qu'aucun bouton ne permette de l'exercer. La promesse existait, pas le
geste.
"""

from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone

from apps.payments.tokens import cancel_token, status_token
from apps.customers.models import Customer
from apps.salons.models import SalonProfile
from apps.scheduling.models import Booking
from conftest import as_tenant, salon_host
from tests.test_dashboard_api import login, make_booking

HOST = {"Host": salon_host("blondrose")}


def delai(salon, heures: int) -> None:
    with as_tenant(salon.tenant):
        SalonProfile.objects.filter(tenant=salon.tenant).update(
            cancellation_deadline_hours=heures
        )


def creneau_libre(salon, jours: int = 12, heure: int = 10):
    """Un creneau ouvert, loin devant, dans le fuseau du salon."""
    from zoneinfo import ZoneInfo

    zone = ZoneInfo(salon.tenant.timezone or "UTC")
    jour = (timezone.now().astimezone(zone) + timedelta(days=jours)).date()
    # Les fixtures ouvrent du lundi au samedi : on evite le dimanche.
    while jour.weekday() == 6:
        jour += timedelta(days=1)
    from datetime import datetime, time

    return datetime.combine(jour, time(heure, 0), tzinfo=zone)


# ---------------------------------------------------------------------------
# Deplacer, cote salon
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_le_salon_deplace_un_rendez_vous(api_client, salon_a):
    booking = make_booking(salon_a, status=Booking.Status.CONFIRMED)
    nouveau = creneau_libre(salon_a)
    login(api_client, salon_a.owner)

    reponse = api_client.post(
        f"/api/v1/bookings/{booking.id}/reschedule/",
        {"starts_at": nouveau.isoformat()},
        format="json",
    )

    assert reponse.status_code == 200, reponse.data
    with as_tenant(salon_a.tenant):
        booking.refresh_from_db()
    assert booking.starts_at == nouveau
    # La fin suit la duree de la prestation : la laisser en place donnerait
    # un rendez-vous qui commence apres qu'il est cense finir.
    assert booking.ends_at == nouveau + timedelta(
        minutes=salon_a.service.duration_minutes
    )


@pytest.mark.django_db
def test_la_cliente_est_prevenue_du_deplacement(api_client, salon_a):
    """C'etait silencieux : le salon changeait l'heure, la cliente se
    presentait a l'ancienne."""
    booking = make_booking(salon_a, status=Booking.Status.CONFIRMED)
    # La fixture cree une cliente sans adresse — on reserve aussi par
    # telephone, et `send_email` le tolere sans rien envoyer. Ici c'est
    # justement l'envoi qu'on mesure.
    with as_tenant(salon_a.tenant):
        Customer.objects.filter(id=booking.customer_id).update(
            email="awa@exemple.test"
        )
    login(api_client, salon_a.owner)
    mail.outbox.clear()

    api_client.post(
        f"/api/v1/bookings/{booking.id}/reschedule/",
        {"starts_at": creneau_libre(salon_a).isoformat()},
        format="json",
    )

    messages = [m for m in mail.outbox if "déplacé" in m.subject]
    assert messages, [m.subject for m in mail.outbox]
    assert "awa@exemple.test" in messages[0].to
    # Les deux dates cote a cote : donner seulement la nouvelle obligerait a
    # retrouver l'e-mail precedent pour comprendre ce qui a bouge.
    assert "Ancienne date" in messages[0].body or "Ancienne" in messages[0].body


@pytest.mark.django_db
def test_le_rappel_se_rearme_apres_un_deplacement(api_client, salon_a):
    """Sinon la cliente a recu un rappel pour l'ancienne date et n'en recevra
    aucun pour la nouvelle : le pire des deux cas."""
    booking = make_booking(salon_a, status=Booking.Status.CONFIRMED)
    with as_tenant(salon_a.tenant):
        Booking.objects.filter(id=booking.id).update(reminder_sent_at=timezone.now())

    login(api_client, salon_a.owner)
    api_client.post(
        f"/api/v1/bookings/{booking.id}/reschedule/",
        {"starts_at": creneau_libre(salon_a).isoformat()},
        format="json",
    )

    with as_tenant(salon_a.tenant):
        booking.refresh_from_db()
    assert booking.reminder_sent_at is None


@pytest.mark.django_db
@pytest.mark.parametrize(
    "etat", [Booking.Status.COMPLETED, Booking.Status.CANCELLED, Booking.Status.NO_SHOW]
)
def test_un_rendez_vous_clos_ne_se_deplace_pas(api_client, salon_a, etat):
    """Rien ne l'interdisait : on pouvait donner une nouvelle date a une
    prestation deja facturee, ou ressusciter une annulation dont la cliente
    avait ete prevenue."""
    booking = make_booking(salon_a, status=etat)
    login(api_client, salon_a.owner)

    reponse = api_client.post(
        f"/api/v1/bookings/{booking.id}/reschedule/",
        {"starts_at": creneau_libre(salon_a).isoformat()},
        format="json",
    )

    assert reponse.status_code == 400
    with as_tenant(salon_a.tenant):
        booking.refresh_from_db()
    assert booking.status == etat


@pytest.mark.django_db
def test_un_creneau_deja_pris_est_refuse_avec_des_alternatives(api_client, salon_a):
    """Un refus sec oblige a deviner : la reponse porte de quoi reessayer."""
    occupe = creneau_libre(salon_a)
    voisin = make_booking(salon_a, hours_ahead=240, status=Booking.Status.CONFIRMED)
    with as_tenant(salon_a.tenant):
        Booking.objects.filter(id=voisin.id).update(
            starts_at=occupe,
            ends_at=occupe + timedelta(minutes=salon_a.service.duration_minutes),
        )

    # Trois heures d'ecart : la contrainte d'exclusion interdit deux
    # rendez-vous qui se chevauchent chez la meme prestataire.
    deplace = make_booking(salon_a, hours_ahead=400, status=Booking.Status.CONFIRMED)
    login(api_client, salon_a.owner)

    reponse = api_client.post(
        f"/api/v1/bookings/{deplace.id}/reschedule/",
        {"starts_at": occupe.isoformat()},
        format="json",
    )

    assert reponse.status_code == 409
    assert reponse.data["code"] == "slot_unavailable"


# ---------------------------------------------------------------------------
# Annuler, cote cliente
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_la_cliente_annule_dans_la_fenetre_annoncee(api_client, salon_a):
    delai(salon_a, 24)
    booking = make_booking(salon_a, hours_ahead=72, status=Booking.Status.CONFIRMED)

    reponse = api_client.post(
        "/api/v1/public/booking/cancel",
        {"token": cancel_token(booking), "reason": "Empêchement"},
        format="json",
        headers=HOST,
    )

    assert reponse.status_code == 200, reponse.data
    with as_tenant(salon_a.tenant):
        booking.refresh_from_db()
    assert booking.status == Booking.Status.CANCELLED
    assert booking.cancellation_reason == "Empêchement"


@pytest.mark.django_db
def test_passe_le_delai_la_cliente_ne_peut_plus(api_client, salon_a):
    """La politique du salon est une promesse dans les deux sens : elle
    autorise avant, elle refuse apres."""
    delai(salon_a, 24)
    booking = make_booking(salon_a, hours_ahead=3, status=Booking.Status.CONFIRMED)
    jeton = cancel_token(booking)

    reponse = api_client.post(
        "/api/v1/public/booking/cancel",
        {"token": jeton},
        format="json",
        headers=HOST,
    )

    assert reponse.status_code == 409
    assert reponse.data["code"] == "cancel_window_closed"
    with as_tenant(salon_a.tenant):
        booking.refresh_from_db()
    assert booking.status == Booking.Status.CONFIRMED


@pytest.mark.django_db
def test_la_regle_est_revalidee_a_l_execution(api_client, salon_a):
    """Un jeton emis quand la fenetre etait ouverte ne doit pas ouvrir une
    porte que le delai vient de fermer."""
    delai(salon_a, 24)
    booking = make_booking(salon_a, hours_ahead=30, status=Booking.Status.CONFIRMED)
    jeton = cancel_token(booking)

    # Le rendez-vous se rapproche : il n'est plus qu'a deux heures.
    with as_tenant(salon_a.tenant):
        proche = timezone.now() + timedelta(hours=2)
        Booking.objects.filter(id=booking.id).update(
            starts_at=proche,
            ends_at=proche + timedelta(minutes=salon_a.service.duration_minutes),
        )

    reponse = api_client.post(
        "/api/v1/public/booking/cancel",
        {"token": jeton},
        format="json",
        headers=HOST,
    )

    assert reponse.status_code == 409


@pytest.mark.django_db
def test_le_jeton_de_suivi_n_annule_pas(api_client, salon_a):
    """Il promet de ne rien autoriser en ecriture, et il vit cent vingt jours
    dans un signet."""
    delai(salon_a, 24)
    booking = make_booking(salon_a, hours_ahead=72, status=Booking.Status.CONFIRMED)

    reponse = api_client.post(
        "/api/v1/public/booking/cancel",
        {"token": status_token(booking)},
        format="json",
        headers=HOST,
    )

    assert reponse.status_code == 404
    with as_tenant(salon_a.tenant):
        booking.refresh_from_db()
    assert booking.status == Booking.Status.CONFIRMED


@pytest.mark.django_db
def test_le_jeton_d_un_autre_salon_ne_passe_pas(api_client, salon_a, salon_b):
    delai(salon_b, 24)
    booking = make_booking(salon_b, hours_ahead=72, status=Booking.Status.CONFIRMED)

    reponse = api_client.post(
        "/api/v1/public/booking/cancel",
        {"token": cancel_token(booking)},
        format="json",
        # L'hote est celui du salon A : le jeton designe un rendez-vous du B.
        headers=HOST,
    )

    assert reponse.status_code == 404


@pytest.mark.django_db
def test_annuler_deux_fois_ne_fait_pas_d_erreur(api_client, salon_a):
    """Un deuxieme clic, ou un renvoi de formulaire, ne doit pas afficher une
    erreur a quelqu'un qui a obtenu ce qu'il voulait."""
    delai(salon_a, 24)
    booking = make_booking(salon_a, hours_ahead=72, status=Booking.Status.CONFIRMED)
    jeton = cancel_token(booking)

    premiere = api_client.post(
        "/api/v1/public/booking/cancel", {"token": jeton}, format="json", headers=HOST
    )
    seconde = api_client.post(
        "/api/v1/public/booking/cancel", {"token": jeton}, format="json", headers=HOST
    )

    assert premiere.status_code == 200
    assert seconde.status_code == 200


@pytest.mark.django_db
def test_le_salon_est_prevenu_qu_un_creneau_se_libere(api_client, salon_a):
    """Un creneau libere une journee a l'avance se repropose ; abandonne en
    silence, il coute une demi-journee de travail."""
    delai(salon_a, 24)
    booking = make_booking(salon_a, hours_ahead=72, status=Booking.Status.CONFIRMED)
    mail.outbox.clear()

    api_client.post(
        "/api/v1/public/booking/cancel",
        {"token": cancel_token(booking)},
        format="json",
        headers=HOST,
    )

    pour_le_salon = [m for m in mail.outbox if salon_a.owner.email in m.to]
    assert pour_le_salon, [(m.subject, m.to) for m in mail.outbox]


@pytest.mark.django_db
def test_une_cliente_arrivee_ne_peut_plus_annuler(api_client, salon_a):
    """Elle est dans le fauteuil : la prestation se termine ou se constate,
    elle ne se decommande pas depuis un telephone."""
    delai(salon_a, 24)
    booking = make_booking(salon_a, hours_ahead=72, status=Booking.Status.CHECKED_IN)

    reponse = api_client.post(
        "/api/v1/public/booking/cancel",
        {"token": cancel_token(booking)},
        format="json",
        headers=HOST,
    )

    assert reponse.status_code == 409


# ---------------------------------------------------------------------------
# Ce que la cliente voit
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_la_page_de_suivi_porte_le_droit_d_annuler(api_client, salon_a):
    delai(salon_a, 24)
    booking = make_booking(salon_a, hours_ahead=72, status=Booking.Status.CONFIRMED)

    reponse = api_client.get(
        f"/api/v1/public/booking-status?token={status_token(booking)}",
        headers=HOST,
    )

    fiche = reponse.data["booking"]
    assert fiche["can_cancel"] is True
    assert fiche["cancel_token"]
    assert fiche["cancel_deadline_hours"] == 24


@pytest.mark.django_db
def test_hors_fenetre_aucun_jeton_n_est_emis(api_client, salon_a):
    """Une capacite distribuee « au cas ou » finit par etre utilisee hors du
    cas prevu. La date limite, elle, reste : l'interface doit pouvoir dire
    pourquoi le bouton n'est pas la."""
    delai(salon_a, 24)
    booking = make_booking(salon_a, hours_ahead=3, status=Booking.Status.CONFIRMED)

    reponse = api_client.get(
        f"/api/v1/public/booking-status?token={status_token(booking)}",
        headers=HOST,
    )

    fiche = reponse.data["booking"]
    assert fiche["can_cancel"] is False
    assert fiche["cancel_token"] == ""
    assert fiche["cancel_until"]
