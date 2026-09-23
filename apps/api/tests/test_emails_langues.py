"""Une cliente qui réserve en anglais est écrite en anglais.

---------------------------------------------------------------------------
Ce qui est réellement en jeu
---------------------------------------------------------------------------

Le mini-site parle deux langues depuis peu. L'e-mail, lui, partait en français
à tout le monde : une cliente qui avait tout lu en anglais — les prestations,
le prix, la politique d'annulation qu'elle a cochée — recevait sa confirmation,
puis son rappel de la veille, dans une langue qu'elle ne lit peut-être pas.
C'est le premier message qu'elle reçoit du salon, et le seul qui lui serve de
justificatif.

Quatre affirmations, et ce fichier ne teste qu'elles :

  1. **La langue de lecture est retenue.** Au moment de la réservation, pas
     après : c'est dans celle-là qu'elle a lu ce qu'elle acceptait.

  2. **Elle décide de l'e-mail** — objet compris. L'objet est ce qu'on voit
     avant d'ouvrir, et un objet français dans une boîte anglaise ressemble à
     du courrier indésirable.

  3. **Le français reste la valeur par défaut.** Une réservation prise au
     téléphone par le salon n'en porte aucune, et rien ne doit casser.

  4. **Les deux catalogues ont les mêmes clés.** Une clé absente d'un côté
     s'afficherait telle quelle — « confirmation_titre » en haut du message.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone

from apps.notifications import tasks
from apps.notifications.details import grouper
from apps.notifications.textes import EN, FR, textes
from conftest import as_tenant, salon_host
from tests.factories import BookingFactory

# ------------------------------------------------------- 4. les catalogues


def test_les_deux_catalogues_ont_les_memes_cles():
    seul_fr = sorted(k for k in FR if k not in EN)
    seul_en = sorted(k for k in EN if k not in FR)
    assert not seul_fr, f"clés sans traduction anglaise : {seul_fr}"
    assert not seul_en, f"clés sans original français : {seul_en}"


def test_aucune_valeur_n_est_vide():
    """Une valeur vide est pire qu'une clé absente : elle ne se voit pas."""
    for nom, catalogue in (("fr", FR), ("en", EN)):
        vides = sorted(cle for cle, valeur in catalogue.items() if not valeur.strip())
        assert not vides, f"{nom} : valeurs vides — {vides}"


def test_les_variables_se_correspondent():
    """« {salon} » d'un côté doit être « {salon} » de l'autre.

    Une variable renommée dans la traduction ne lève pas : `dire()` rend le
    modèle tel quel, et la cliente lit « Rappel : votre rendez-vous chez
    {salon} ».
    """
    import re

    motif = re.compile(r"\{(\w+)\}")
    ecarts = []
    for cle, source in FR.items():
        attendues = set(motif.findall(source))
        obtenues = set(motif.findall(EN[cle]))
        if attendues != obtenues:
            ecarts.append(f"{cle} : fr={sorted(attendues)} en={sorted(obtenues)}")
    assert not ecarts, "variables dépareillées — " + " | ".join(ecarts)


def _reservation(salon_a, langue: str = "fr"):
    """Un rendez-vous complet, avec tout ce que la grille sait afficher.

    La cliente recoit une adresse : sans elle, `send_email` rend False sans
    rien envoyer — une reservation par telephone n'a pas d'e-mail, et ce n'est
    pas une erreur.
    """
    if not salon_a.customer.email:
        salon_a.customer.email = "grace@example.com"
        salon_a.customer.save(update_fields=["email"])

    debut = timezone.now() + timedelta(days=1)
    return BookingFactory(
        tenant=salon_a.tenant,
        customer=salon_a.customer,
        staff_member=salon_a.staff,
        service=salon_a.service,
        starts_at=debut,
        ends_at=debut + timedelta(minutes=210),
        language=langue,
    )


# --------------------------------------------- 1 et 3. la langue est retenue


@pytest.mark.django_db
def test_le_francais_est_la_valeur_par_defaut(tenant_a, salon_a):
    """Une réservation prise au téléphone n'a pas de langue de lecture."""
    with as_tenant(tenant_a):
        booking = _reservation(salon_a)
    assert booking.language == "fr"


@pytest.mark.django_db
def test_la_langue_de_lecture_est_retenue(tenant_a, salon_a):
    with as_tenant(tenant_a):
        booking = _reservation(salon_a, langue="en")
        booking.refresh_from_db()
    assert booking.language == "en"


# ------------------------------------------------- 2. elle décide de l'e-mail


@pytest.mark.django_db
def test_une_reservation_en_anglais_produit_un_e_mail_en_anglais(
    tenant_a, salon_a, monkeypatch
):
    """Le chemin réel : la tâche Celery, pas un contexte recopié."""
    monkeypatch.setattr(tasks, "_salon_recipients", lambda tenant: [])

    with as_tenant(tenant_a):
        booking = _reservation(salon_a, langue="en")
        mail.outbox.clear()
        tasks.send_booking_notifications(str(booking.id), str(tenant_a.id))

    assert mail.outbox, "aucun e-mail n'est parti"
    message = mail.outbox[0]

    assert message.subject == f"Your appointment at {tenant_a.name}"
    assert "Your appointment at" in message.body
    assert "Bonjour" not in message.body
    assert "Votre rendez-vous" not in message.body

    html = message.alternatives[0][0]
    assert 'lang="en"' in html
    assert "Your appointment is booked" in html
    # Les intitulés de la grille suivent aussi.
    assert ">SERVICE<" in html.upper()


@pytest.mark.django_db
def test_une_reservation_en_francais_reste_en_francais(
    tenant_a, salon_a, monkeypatch
):
    monkeypatch.setattr(tasks, "_salon_recipients", lambda tenant: [])

    with as_tenant(tenant_a):
        booking = _reservation(salon_a, langue="fr")
        mail.outbox.clear()
        tasks.send_booking_notifications(str(booking.id), str(tenant_a.id))

    message = mail.outbox[0]
    assert message.subject == f"Votre rendez-vous chez {tenant_a.name}"
    assert 'lang="fr"' in message.alternatives[0][0]


# ------------------------------------------- la grille à deux colonnes


def test_la_grille_groupe_deux_faits_par_rangee():
    faits = [
        {"label": "a", "value": "1"},
        {"label": "b", "value": "2"},
        {"label": "c", "value": "3"},
    ]
    assert grouper(faits) == [
        [{"label": "a", "value": "1"}, {"label": "b", "value": "2"}],
        [{"label": "c", "value": "3"}],
    ]


def test_un_fait_large_ferme_la_rangee_en_cours():
    """Sinon il s'insère à côté d'un autre et déborde de la grille."""
    faits = [
        {"label": "a", "value": "1"},
        {"label": "long", "value": "…", "wide": True},
        {"label": "b", "value": "2"},
    ]
    rangees = grouper(faits)
    assert [len(r) for r in rangees] == [1, 1, 1]
    assert rangees[1][0]["wide"] is True


def test_une_grille_vide_ne_rend_aucune_rangee():
    assert grouper([]) == []


# ------------------------------------------------ les phrases à variables


def test_une_phrase_a_variables_se_resout():
    t = textes("en")
    assert t.dire("confirmation_objet", salon="Blond Rose") == (
        "Your appointment at Blond Rose"
    )


def test_une_variable_manquante_ne_leve_pas():
    """Rendre le modèle brut vaut mieux qu'une pile d'appels dans les journaux.

    Un e-mail qui part avec « {salon} » visible se remarque et se corrige ; un
    envoi qui échoue au milieu d'une tâche Celery, moins.
    """
    t = textes("fr")
    assert t.dire("confirmation_objet") == "Votre rendez-vous chez {salon}"


def test_une_langue_inconnue_rend_le_francais():
    assert textes("xx")["total"] == FR["total"]
    assert textes(None)["total"] == FR["total"]


# ----------------------------------------- 1 bis. le mini-site la transmet


def _creneau_libre():
    """Un lundi à 10 h, suffisamment loin pour être ouvert et disponible."""
    from datetime import date, datetime, time
    from zoneinfo import ZoneInfo

    brazza = ZoneInfo("Africa/Brazzaville")
    aujourdhui = datetime.now(brazza).date()
    avance = (0 - aujourdhui.weekday()) % 7 or 7
    jour: date = aujourdhui + timedelta(days=avance + 7)
    return datetime.combine(jour, time(10, 0), tzinfo=brazza)


@pytest.mark.django_db
def test_le_mini_site_transmet_la_langue_de_lecture(api_client, salon_a):
    """Le contrat entre le parcours de réservation et l'API.

    C'est le maillon qu'aucun autre test ne couvre : le reste vérifie qu'une
    réservation *portant* une langue produit le bon e-mail, mais pas qu'elle
    la porte. Sans ce maillon, tout le reste marche et chaque e-mail part
    quand même en français.
    """
    from apps.scheduling.models import Booking

    reponse = api_client.post(
        "/api/v1/public/bookings",
        {
            "service": str(salon_a.service.id),
            "starts_at": _creneau_libre().isoformat(),
            "full_name": "Awa Diallo",
            "phone": "+242066112233",
            "accepts_policy": True,
            "language": "en",
        },
        format="json",
        headers={"Host": salon_host(salon_a.tenant.slug)},
    )
    assert reponse.status_code == 201, reponse.data

    with as_tenant(salon_a.tenant):
        booking = Booking.objects.order_by("-created_at").first()
    assert booking.language == "en"


@pytest.mark.django_db
def test_une_langue_inconnue_est_refusee(api_client, salon_a):
    """Cette valeur finit dans un nom de gabarit : elle ne peut pas être libre.

    Une chaîne arbitraire chercherait `emails/booking_confirmation.xx.html`,
    ou pire, servirait de clé à un catalogue qui n'existe pas.
    """
    reponse = api_client.post(
        "/api/v1/public/bookings",
        {
            "service": str(salon_a.service.id),
            "starts_at": _creneau_libre().isoformat(),
            "full_name": "Awa Diallo",
            "phone": "+242066112233",
            "accepts_policy": True,
            "language": "../../etc",
        },
        format="json",
        headers={"Host": salon_host(salon_a.tenant.slug)},
    )
    assert reponse.status_code == 400
    # L API enveloppe ses erreurs de champ dans `detail`.
    assert "language" in reponse.data["detail"]
