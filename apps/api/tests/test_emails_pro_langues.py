"""Les e-mails aux professionnels parlent la langue de chaque compte.

Ce que ces tests tiennent :

  - la langue de la page d'inscription est retenue sur le compte des sa
    creation : un salon qui s'inscrit en anglais recoit sa bienvenue et son
    lien de verification en anglais — sans rien configurer, pour n'importe
    quel salon a venir ;
  - un meme evenement part en francais a la proprietaire et en anglais a la
    gerante, chacune avec des liens qui ouvrent sa langue ;
  - mot de passe oublie, invitation, alerte de securite, rappels
    d'abonnement suivent la meme regle ;
  - le francais reste exactement ce qu'il etait.
"""

from datetime import UTC, datetime, timedelta

import pytest
from django.core import mail

from apps.accounts import tasks as comptes
from apps.accounts.models import Membership, User
from apps.billing import courriers
from apps.billing.rappels import envoyer_rappels
from apps.notifications import tasks
from apps.notifications.textes import EN, FR
from conftest import as_tenant
from tests.factories import BookingFactory, MembershipFactory, UserFactory
from tests.test_abonnements import abonnement_de, medias_temporaires, moyens, offres

FIXTURES_PARTAGEES = (medias_temporaires, moyens, offres)
TRANSACTIONNEL = pytest.mark.django_db(databases=["default", "admin"], transaction=True)
PASSWORD = "motdepasse-solide"
MIDI = datetime(2027, 3, 10, 11, 0, tzinfo=UTC)


def a(adresse):
    return [m for m in mail.outbox if adresse in m.to]


def en_anglais(user):
    user.locale = "en"
    user.save(update_fields=["locale"])
    return user


# ---------------------------------------------------------------------------
# Le catalogue
# ---------------------------------------------------------------------------


def test_chaque_phrase_pro_existe_dans_les_deux_langues():
    pro = {cle for cle in FR if cle.startswith(("pro_", "bienvenue_", "invitation_",
                                                 "reinit_", "secu_", "role_", "source_"))}
    assert pro, "Le catalogue pro n'a pas ete fusionne."
    assert pro <= set(EN)
    assert all(EN[cle].strip() for cle in pro)


# ---------------------------------------------------------------------------
# Inscription : la langue de la page devient celle du compte
# ---------------------------------------------------------------------------


@TRANSACTIONNEL
def test_un_salon_inscrit_en_anglais_recoit_tout_en_anglais(api_client):
    reponse = api_client.post(
        "/api/v1/account/signup",
        {
            "salon_name": "Studio Glow",
            "slug": "studio-glow",
            "email": "owner@example.com",
            "password": "un-mot-de-passe-solide",
            "accepts_terms": True,
        },
        format="json",
        HTTP_ACCEPT_LANGUAGE="en",
    )

    assert reponse.status_code == 201, reponse.data
    assert User.objects.get(email="owner@example.com").locale == "en"
    sujets = sorted(m.subject for m in mail.outbox)
    assert sujets == [
        "Confirm your email address — Beauty Salon",
        "Welcome to Beauty Salon, Studio Glow",
    ]
    bienvenue = next(m for m in mail.outbox if m.subject.startswith("Welcome"))
    assert "Your salon Studio Glow has been created on Beauty Salon." in bienvenue.body
    assert "/en" in bienvenue.body
    html = bienvenue.alternatives[0][0]
    assert '<html lang="en">' in html
    assert "Bienvenue" not in html
    verification = next(m for m in mail.outbox if m.subject.startswith("Confirm"))
    assert "/en/verifier-email?token=" in verification.body


@TRANSACTIONNEL
def test_un_salon_inscrit_en_francais_reste_en_francais(api_client):
    api_client.post(
        "/api/v1/account/signup",
        {
            "salon_name": "Studio Kiné",
            "slug": "studio-kine",
            "email": "proprietaire@example.com",
            "password": "un-mot-de-passe-solide",
            "accepts_terms": True,
        },
        format="json",
        HTTP_ACCEPT_LANGUAGE="fr-FR,fr;q=0.9",
    )

    assert User.objects.get(email="proprietaire@example.com").locale == "fr"
    assert sorted(m.subject for m in mail.outbox) == [
        "Bienvenue sur Beauty Salon, Studio Kiné",
        "Confirmez votre adresse e-mail — Beauty Salon",
    ]
    bienvenue = next(m for m in mail.outbox if m.subject.startswith("Bienvenue"))
    assert "/en" not in bienvenue.body


# ---------------------------------------------------------------------------
# Mot de passe oublie, invitation, alerte
# ---------------------------------------------------------------------------


@TRANSACTIONNEL
def test_le_mot_de_passe_oublie_repond_dans_la_langue_de_la_page(api_client, salon_a):
    api_client.post(
        "/api/v1/account/password/reset",
        {"email": salon_a.owner.email},
        format="json",
        HTTP_ACCEPT_LANGUAGE="en",
    )

    (message,) = mail.outbox
    assert message.subject == "Reset your Beauty Salon password"
    assert "/en/mot-de-passe/nouveau?uid=" in message.body
    assert "This link is valid for" in message.body


@TRANSACTIONNEL
def test_une_invitation_envoyee_en_anglais_cree_un_compte_anglais(api_client, salon_a):
    assert api_client.login(email=salon_a.owner.email, password=PASSWORD)

    envoi = api_client.post(
        "/api/v1/invitations/",
        {"email": "reception@example.com", "role": "receptionist"},
        format="json",
        HTTP_ACCEPT_LANGUAGE="en",
    )

    assert envoi.status_code == 201, envoi.data
    (invitation,) = mail.outbox
    assert invitation.subject == "Join the Blond Rose team"
    assert "Role: Receptionist" in invitation.body
    assert "/en/invitation?token=" in invitation.body
    jeton = invitation.body.split("token=", 1)[1].split()[0]

    api_client.logout()
    acceptation = api_client.post(
        "/api/v1/account/invitation/accept",
        {"token": jeton, "password": "nouveau-motdepasse-42", "display_name": "Reception"},
        format="json",
        HTTP_ACCEPT_LANGUAGE="en",
    )

    assert acceptation.status_code == 201
    assert User.objects.get(email="reception@example.com").locale == "en"


@pytest.mark.django_db
def test_l_alerte_de_securite_suit_la_langue_passee():
    comptes.alerte_securite("a@example.com", "mfa_active", nom="Anna", langue="en")
    comptes.alerte_securite("b@example.com", "adresse", nouvelle_adresse="n@x.com")

    anglaise, francaise = mail.outbox
    assert anglaise.subject == "Two-factor authentication enabled on your Beauty Salon account"
    assert anglaise.body.startswith("Hello Anna,")
    assert "/en/mot-de-passe-oublie" in anglaise.body
    assert francaise.subject == "L'adresse e-mail de votre compte Beauty Salon a changé"
    assert "remplacée par n@x.com" in francaise.body


# ---------------------------------------------------------------------------
# Les e-mails du salon : un par langue
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_une_reservation_est_annoncee_a_chacun_dans_sa_langue(salon_a):
    gerante = en_anglais(UserFactory())
    MembershipFactory(tenant=salon_a.tenant, user=gerante, role=Membership.Role.MANAGER)
    debut = MIDI + timedelta(days=2)
    with as_tenant(salon_a.tenant):
        reservation = BookingFactory(
            tenant=salon_a.tenant,
            service=salon_a.service,
            staff_member=salon_a.staff,
            customer=salon_a.customer,
            starts_at=debut,
            ends_at=debut + timedelta(minutes=60),
        )

    tasks.send_booking_notifications(str(reservation.id), str(salon_a.tenant.id))

    prestation = reservation.service_name
    (francais,) = a(salon_a.owner.email)
    (anglais,) = a(gerante.email)
    assert francais.subject == f"Nouvelle réservation - {prestation}"
    assert "Cliente : " in francais.body
    assert f"/dashboard/agenda?rdv={reservation.id}" in francais.body
    assert "/en/" not in francais.body
    assert anglais.subject == f"New booking - {prestation}"
    assert "Client: " in anglais.body
    assert f"/en/dashboard/agenda?rdv={reservation.id}" in anglais.body
    assert "Nouvelle" not in anglais.alternatives[0][0]


# ---------------------------------------------------------------------------
# Abonnement
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_le_rappel_d_essai_part_en_anglais_a_une_proprietaire_anglophone(salon_a, offres):
    en_anglais(salon_a.owner)
    abonnement_de(salon_a, fin=MIDI + timedelta(days=6, hours=20))

    envoyer_rappels(MIDI)

    (message,) = mail.outbox
    assert message.subject == "Your Beauty Salon trial ends in 7 days"
    assert "Your trial period ends on 17 March 2027." in message.body
    assert "/en/abonnement" in message.body
    assert "15,000 XAF / month" in message.body


def test_les_usages_de_chaque_langue():
    moment = datetime(2026, 10, 1, 12, tzinfo=UTC)
    assert courriers.date_longue(moment) == "1er octobre 2026"
    assert courriers.date_longue(moment, langue="en") == "1 October 2026"
    assert courriers.argent(15000, "XAF") == "15 000 XAF"
    assert courriers.argent(15000, "XAF", "en") == "15,000 XAF"
    assert courriers.argent("12.5", "CNY", "en") == "12.50 CNY"
    assert courriers.quand(moment + timedelta(days=1), "UTC", moment, "en") == "tomorrow"
