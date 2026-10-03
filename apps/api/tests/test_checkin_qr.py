"""L'arrivee par QR, et le retrait d'une visite de l'historique.

Deux gestes, deux garde-fous differents :

  - le QR ne donne aucun droit a lui seul. C'est la session du salon qui
    autorise l'ecriture, et le rendez-vous doit lui appartenir ;
  - retirer une visite ne touche jamais les livres du salon.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.clients.models import ClientProfile, ClientSalonLink, HiddenBooking
from apps.payments.tokens import (
    CHECKIN_CODE_ALPHABET,
    CHECKIN_CODE_LENGTH,
    checkin_code,
    checkin_token,
)
from apps.scheduling.models import Booking
from conftest import as_tenant, salon_host

PASSWORD = "motdepasse-solide"

# Les routes de l'espace cliente resolvent le tenant par le hostname : sans
# cet en-tete, la requete n'atteint meme pas la vue.
HOST = {"Host": salon_host("blondrose")}


def login(client, user):
    assert client.login(email=user.email, password=PASSWORD)
    return client


def make_booking(salon, status=Booking.Status.CONFIRMED, when=None):
    starts_at = when or timezone.now() + timedelta(days=1)
    with as_tenant(salon.tenant):
        return Booking.objects.create(
            tenant=salon.tenant,
            customer=salon.customer,
            staff_member=salon.staff,
            service=salon.service,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(hours=2),
            status=status,
            service_name="Box braids",
            total_amount=Decimal("450"),
        )


# ---------------------------------------------------------------------------
# Le QR d'arrivee
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_scanning_the_code_marks_the_client_as_arrived(api_client, salon_a):
    booking = make_booking(salon_a)
    login(api_client, salon_a.owner)

    response = api_client.post(
        "/api/v1/bookings/check-in/",
        {"token": checkin_token(booking)},
        format="json",
    )

    assert response.status_code == 200, response.data
    with as_tenant(salon_a.tenant):
        booking.refresh_from_db()
    assert booking.status == Booking.Status.CHECKED_IN


@pytest.mark.django_db
def test_scanning_twice_says_so_instead_of_failing(api_client, salon_a):
    """Deux coups de scanner sur le meme code arrivent tout le temps."""
    booking = make_booking(salon_a, status=Booking.Status.CHECKED_IN)
    login(api_client, salon_a.owner)

    response = api_client.post(
        "/api/v1/bookings/check-in/",
        {"token": checkin_token(booking)},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["code"] == "already_checked_in"


@pytest.mark.django_db
def test_a_booking_that_is_not_confirmed_cannot_be_checked_in(api_client, salon_a):
    """Se presenter pour un creneau que le salon n'a pas accepte ne doit pas
    passer : c'est exactement ce que la confirmation existe pour eviter."""
    booking = make_booking(salon_a, status=Booking.Status.PENDING_PAYMENT)
    login(api_client, salon_a.owner)

    response = api_client.post(
        "/api/v1/bookings/check-in/",
        {"token": checkin_token(booking)},
        format="json",
    )

    assert response.status_code == 400
    assert response.data["code"] == "not_confirmed"


@pytest.mark.django_db
def test_another_salon_cannot_use_the_code(api_client, salon_a, salon_b):
    """Le QR d'une cliente d'un autre salon ne doit rien ouvrir ici."""
    booking = make_booking(salon_a)
    login(api_client, salon_b.owner)

    response = api_client.post(
        "/api/v1/bookings/check-in/",
        {"token": checkin_token(booking)},
        format="json",
    )

    assert response.status_code == 404
    assert response.data["code"] == "unknown_code"


@pytest.mark.django_db
@pytest.mark.parametrize("token", ["bricole", "eyJib29raW5nIjoieCJ9:faux"])
def test_a_forged_code_opens_nothing(api_client, salon_a, token):
    login(api_client, salon_a.owner)

    response = api_client.post(
        "/api/v1/bookings/check-in/", {"token": token}, format="json"
    )

    assert response.status_code == 404


@pytest.mark.django_db
def test_sending_nothing_is_not_the_same_as_sending_a_wrong_code(
    api_client, salon_a
):
    """Requete vide : 400, et non 404.

    Les deux reponses s'adressent a des gens differents. « Ce code ne
    correspond a rien » parle au salon, qui doit verifier sa saisie ; « vous
    n'avez rien envoye » parle a l'interface, qui a laisse partir une requete
    vide. Les confondre ferait chercher une faute de frappe la ou il n'y a
    pas de frappe du tout.
    """
    login(api_client, salon_a.owner)

    response = api_client.post("/api/v1/bookings/check-in/", {}, format="json")

    assert response.status_code == 400
    assert response.data["code"] == "missing_code"


@pytest.mark.django_db
def test_the_code_alone_gives_no_right(api_client, salon_a):
    """Photographier l'ecran d'une cliente ne suffit pas : il faut un compte
    du salon."""
    booking = make_booking(salon_a)

    response = api_client.post(
        "/api/v1/bookings/check-in/",
        {"token": checkin_token(booking)},
        format="json",
    )

    assert response.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Ce que la cliente voit, et quand
# ---------------------------------------------------------------------------


def make_client(api_client, salon):
    """Inscrit une cliente et la rattache a la fiche du salon.

    Passe par la route publique plutot que par les modeles : elle ouvre la
    session au passage, ce que `client.login` ne ferait pas pour un compte
    cliente.
    """
    api_client.post(
        "/api/v1/public/client/signup",
        {
            "full_name": "Awa Diallo",
            "email": "awa@example.com",
            "phone": "+242066112233",
            "password": "Tresses-2026-Brazza",
        },
        format="json",
        headers=HOST,
    )
    user = ClientProfile.objects.get(user__email="awa@example.com").user
    ClientSalonLink.objects.create(
        user=user, tenant=salon.tenant, customer_id=salon.customer.id
    )
    return user


@pytest.mark.django_db
def test_the_qr_appears_only_once_the_salon_has_confirmed(api_client, salon_a):
    """Le montrer avant laisserait croire qu'il vaut confirmation, et une
    cliente se presenterait pour un creneau non accepte."""
    make_booking(salon_a, status=Booking.Status.REQUESTED)
    make_client(api_client, salon_a)

    rows = api_client.get("/api/v1/public/client/bookings", headers=HOST).data["bookings"]
    waiting = next(row for row in rows if row["status"] == "requested")
    assert waiting["checkin_token"] == ""

    with as_tenant(salon_a.tenant):
        Booking.objects.filter(status=Booking.Status.REQUESTED).update(
            status=Booking.Status.CONFIRMED
        )

    rows = api_client.get("/api/v1/public/client/bookings", headers=HOST).data["bookings"]
    confirmed = next(row for row in rows if row["status"] == "confirmed")
    assert confirmed["checkin_token"]


# ---------------------------------------------------------------------------
# Retirer une visite de son historique
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_finished_visit_can_be_removed_from_her_history(api_client, salon_a):
    booking = make_booking(
        salon_a,
        status=Booking.Status.COMPLETED,
        when=timezone.now() - timedelta(days=10),
    )
    make_client(api_client, salon_a)

    response = api_client.post(
        "/api/v1/public/client/bookings/forget",
        {"booking": str(booking.id)},
        format="json",
        headers=HOST,
    )

    assert response.status_code == 200
    rows = api_client.get("/api/v1/public/client/bookings", headers=HOST).data["bookings"]
    assert all(row["id"] != str(booking.id) for row in rows)


@pytest.mark.django_db
def test_removing_it_never_touches_the_salons_books(api_client, salon_a):
    """Le rendez-vous porte le chiffre d'affaires du salon : il reste."""
    booking = make_booking(
        salon_a,
        status=Booking.Status.COMPLETED,
        when=timezone.now() - timedelta(days=10),
    )
    make_client(api_client, salon_a)

    api_client.post(
        "/api/v1/public/client/bookings/forget",
        {"booking": str(booking.id)},
        format="json",
        headers=HOST,
    )

    with as_tenant(salon_a.tenant):
        assert Booking.objects.filter(id=booking.id).exists()


@pytest.mark.django_db
def test_an_upcoming_booking_cannot_be_removed(api_client, salon_a):
    """Elle le croirait annule alors que le salon l'attend toujours."""
    booking = make_booking(salon_a, status=Booking.Status.CONFIRMED)
    make_client(api_client, salon_a)

    response = api_client.post(
        "/api/v1/public/client/bookings/forget",
        {"booking": str(booking.id)},
        format="json",
        headers=HOST,
    )

    assert response.status_code == 400
    assert response.data["code"] == "still_upcoming"


@pytest.mark.django_db
def test_she_cannot_hide_someone_elses_booking(api_client, salon_a, salon_b):
    other = make_booking(
        salon_b,
        status=Booking.Status.COMPLETED,
        when=timezone.now() - timedelta(days=3),
    )
    make_client(api_client, salon_a)

    response = api_client.post(
        "/api/v1/public/client/bookings/forget",
        {"booking": str(other.id)},
        format="json",
        headers=HOST,
    )

    assert response.status_code == 404
    assert not HiddenBooking.objects.filter(booking_id=other.id).exists()


# ---------------------------------------------------------------------------
# Le code court : le meme droit, quand la camera ne repond pas
# ---------------------------------------------------------------------------
#
# Ce chemin existe parce que l'appareil photo manque les jours ou il
# faudrait qu'il marche. Il doit donc aboutir exactement au meme endroit que
# le QR - memes controles, meme trace - sans jamais devenir plus permissif.


@pytest.mark.django_db
def test_typing_the_short_code_marks_the_client_as_arrived(api_client, salon_a):
    booking = make_booking(salon_a, when=timezone.now() + timedelta(hours=3))
    login(api_client, salon_a.owner)

    response = api_client.post(
        "/api/v1/bookings/check-in/",
        {"code": checkin_code(booking)},
        format="json",
    )

    assert response.status_code == 200
    with as_tenant(salon_a.tenant):
        booking.refresh_from_db()
    assert booking.status == Booking.Status.CHECKED_IN


@pytest.mark.django_db
@pytest.mark.parametrize("typed", ["{code}", " {code} ", "{code_lower}", "{code_spaced}"])
def test_the_saisie_tolerates_spacing_and_case(api_client, salon_a, typed):
    """Les espaces, les tirets et la casse sont du bruit de saisie.

    « a4k-nm3 » et « A4KNM3 » designent le meme rendez-vous ; refuser le
    premier n'apprendrait rien a personne.
    """
    booking = make_booking(salon_a, when=timezone.now() + timedelta(hours=3))
    login(api_client, salon_a.owner)

    code = checkin_code(booking)
    rendered = typed.format(
        code=code,
        code_lower=code.lower(),
        code_spaced=f"{code[:3]}-{code[3:]}",
    )

    response = api_client.post(
        "/api/v1/bookings/check-in/", {"code": rendered}, format="json"
    )

    assert response.status_code == 200, rendered
    with as_tenant(salon_a.tenant):
        booking.refresh_from_db()
    assert booking.status == Booking.Status.CHECKED_IN


@pytest.mark.django_db
def test_a_code_from_another_salon_opens_nothing(api_client, salon_a, salon_b):
    """Le code d'une cliente d'un autre salon ne doit rien ouvrir ici.

    La recherche est bornee au salon connecte : ce n'est pas un filtre
    d'affichage, c'est la meme frontiere que pour le QR.
    """
    booking = make_booking(salon_a, when=timezone.now() + timedelta(hours=3))
    login(api_client, salon_b.owner)

    response = api_client.post(
        "/api/v1/bookings/check-in/",
        {"code": checkin_code(booking)},
        format="json",
    )

    assert response.status_code == 404
    with as_tenant(salon_a.tenant):
        booking.refresh_from_db()
    assert booking.status == Booking.Status.CONFIRMED


@pytest.mark.django_db
def test_a_far_off_booking_is_not_found_by_code(api_client, salon_a):
    """Un rendez-vous dans trois semaines ne se note pas arrive aujourd'hui.

    La fenetre de recherche n'est pas qu'une optimisation : elle empeche de
    noter arrivee, par une faute de frappe heureuse, une cliente attendue le
    mois prochain.
    """
    booking = make_booking(salon_a, when=timezone.now() + timedelta(days=21))
    login(api_client, salon_a.owner)

    response = api_client.post(
        "/api/v1/bookings/check-in/",
        {"code": checkin_code(booking)},
        format="json",
    )

    assert response.status_code == 404
    assert response.data["code"] == "unknown_code"


@pytest.mark.django_db
@pytest.mark.parametrize("typed", ["ABC", "ABCDEFG", "IOSB12", "A4KNM0"])
def test_a_malformed_code_says_so_rather_than_unknown(api_client, salon_a, typed):
    """Un caractere hors alphabet n'est pas un code inconnu.

    C'est une lecture erronee, et le dire evite de chercher une cliente qui
    n'existe pas. Surtout, rien n'est *devine* : rattraper le « O » tape en
    « Q » transformerait parfois une frappe erronee en un code valide - celui
    d'une autre cliente - et le salon noterait arrivee la mauvaise personne.
    """
    login(api_client, salon_a.owner)

    response = api_client.post(
        "/api/v1/bookings/check-in/", {"code": typed}, format="json"
    )

    assert response.status_code == 400
    assert response.data["code"] == "malformed_code"


@pytest.mark.django_db
def test_the_short_code_alone_gives_no_right(api_client, salon_a):
    """Sans session de salon, le code ne vaut rien - comme le QR."""
    booking = make_booking(salon_a, when=timezone.now() + timedelta(hours=3))

    response = api_client.post(
        "/api/v1/bookings/check-in/",
        {"code": checkin_code(booking)},
        format="json",
    )

    assert response.status_code in (401, 403)
    with as_tenant(salon_a.tenant):
        booking.refresh_from_db()
    assert booking.status == Booking.Status.CONFIRMED


@pytest.mark.django_db
def test_the_short_code_respects_the_booking_state(api_client, salon_a):
    """Un rendez-vous annule ne se note pas arrive, code ou QR.

    Et le refus porte le rendez-vous : savoir *lequel* est annule est ce qui
    permet de trancher au comptoir.
    """
    booking = make_booking(
        salon_a,
        status=Booking.Status.CANCELLED,
        when=timezone.now() + timedelta(hours=3),
    )
    login(api_client, salon_a.owner)

    response = api_client.post(
        "/api/v1/bookings/check-in/",
        {"code": checkin_code(booking)},
        format="json",
    )

    assert response.status_code == 400
    assert response.data["code"] == "not_confirmed"
    assert response.data["booking"]["id"] == str(booking.id)


@pytest.mark.django_db
def test_the_code_uses_an_unambiguous_alphabet(salon_a):
    """Aucun caractere confondable ne peut apparaitre dans un code.

    Le code se dicte au telephone autant qu'il se recopie d'un ecran : un
    « O » qu'on entend « zero » coute un aller-retour au comptoir.
    """
    # Trois heures d'ecart : les rendez-vous durent deux heures, et la
    # contrainte d'exclusion de la base refuse - a juste titre - deux
    # creneaux qui se chevauchent chez la meme prestataire.
    for offset in range(40):
        booking = make_booking(
            salon_a, when=timezone.now() + timedelta(hours=3 * offset)
        )
        code = checkin_code(booking)

        assert len(code) == CHECKIN_CODE_LENGTH
        assert set(code) <= set(CHECKIN_CODE_ALPHABET)
        assert not set(code) & set("BGILOQSUZ012568 9")


@pytest.mark.django_db
def test_a_code_for_another_client_is_refused_when_a_booking_is_targeted(
    api_client, salon_a
):
    """Scanner le QR de la voisine depuis la ligne d'Espoir ne doit rien noter.

    C'est la seule erreur que le QR existe pour empecher : quatre clientes
    dans le salon a midi, et l'arrivee marquee sur la mauvaise ligne. Le
    scanner ouvert depuis une ligne de l'agenda transmet donc le rendez-vous
    vise, et le serveur refuse tout code qui en designe un autre.

    La verification est cote serveur et non dans le navigateur : une
    comparaison faite par la page se contourne en rejouant la requete.
    """
    espoir = make_booking(salon_a, when=timezone.now() + timedelta(hours=3))
    voisine = make_booking(salon_a, when=timezone.now() + timedelta(hours=6))
    login(api_client, salon_a.owner)

    response = api_client.post(
        "/api/v1/bookings/check-in/",
        {"token": checkin_token(voisine), "booking": str(espoir.id)},
        format="json",
    )

    assert response.status_code == 409
    assert response.data["code"] == "wrong_booking"

    with as_tenant(salon_a.tenant):
        espoir.refresh_from_db()
        voisine.refresh_from_db()
    # Ni l'une ni l'autre : le refus ne doit surtout pas noter « la bonne »
    # par compensation.
    assert espoir.status == Booking.Status.CONFIRMED
    assert voisine.status == Booking.Status.CONFIRMED


@pytest.mark.django_db
def test_the_targeted_booking_accepts_its_own_code(api_client, salon_a):
    """Le cas normal : le code vise le rendez-vous ouvert, et il passe."""
    booking = make_booking(salon_a, when=timezone.now() + timedelta(hours=3))
    login(api_client, salon_a.owner)

    response = api_client.post(
        "/api/v1/bookings/check-in/",
        {"code": checkin_code(booking), "booking": str(booking.id)},
        format="json",
    )

    assert response.status_code == 200, response.data
    with as_tenant(salon_a.tenant):
        booking.refresh_from_db()
    assert booking.status == Booking.Status.CHECKED_IN


@pytest.mark.django_db
def test_a_malformed_target_does_not_crash(api_client, salon_a):
    """Un identifiant de rendez-vous illisible ne doit pas produire un 500.

    Il vient du navigateur : rien ne garantit sa forme, et une exception de
    validation d'UUID remonterait en erreur serveur.
    """
    booking = make_booking(salon_a, when=timezone.now() + timedelta(hours=3))
    login(api_client, salon_a.owner)

    response = api_client.post(
        "/api/v1/bookings/check-in/",
        {"token": checkin_token(booking), "booking": "pas-un-uuid"},
        format="json",
    )

    assert response.status_code == 409
    assert response.data["code"] == "wrong_booking"


# ---------------------------------------------------------------------------
# Un rendez-vous que l'on voit doit pouvoir être noté arrivé
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_le_code_fonctionne_au_dela_de_la_fenetre_quand_le_rendez_vous_est_vise(
    api_client, salon_a
):
    """Le défaut signalé.

    La recherche par code balaie une fenêtre de ±2 jours : elle existe pour
    que deux codes à six caractères ne puissent pas se croiser. Mais un
    rendez-vous ouvert depuis une ligne de l'agenda est déjà désigné — la
    précaution n'a plus d'objet, et elle refusait une cliente attendue dans
    deux jours et demi, affichée à l'écran et nommée dans le panneau.
    """
    booking = make_booking(salon_a, when=timezone.now() + timedelta(days=3))
    login(api_client, salon_a.owner)

    # Sans désigner le rendez-vous : la fenêtre s'applique, et elle refuse.
    aveugle = api_client.post(
        "/api/v1/bookings/check-in/",
        {"code": checkin_code(booking)},
        format="json",
    )
    assert aveugle.status_code == 404
    assert aveugle.data["code"] == "unknown_code"

    # En le désignant — ce que fait le panneau ouvert depuis l'agenda.
    reponse = api_client.post(
        "/api/v1/bookings/check-in/",
        {"code": checkin_code(booking), "booking": str(booking.id)},
        format="json",
    )

    assert reponse.status_code == 200, reponse.data
    with as_tenant(salon_a.tenant):
        booking.refresh_from_db()
    assert booking.status == Booking.Status.CHECKED_IN


@pytest.mark.django_db
def test_un_code_qui_n_est_pas_celui_du_rendez_vous_ouvert_nomme_l_autre_cliente(
    api_client, salon_a
):
    """Le repli sur la recherche par fenêtre a une raison d'être.

    Sans lui, comparer au seul rendez-vous visé rendrait « code inconnu » là
    où l'on peut dire « c'est celui de Madame X » — le message qui permet de
    comprendre, au comptoir, qu'on a scanné la voisine.
    """
    ouvert = make_booking(salon_a)
    voisine = make_booking(salon_a, when=timezone.now() + timedelta(hours=3))

    login(api_client, salon_a.owner)
    reponse = api_client.post(
        "/api/v1/bookings/check-in/",
        {"code": checkin_code(voisine), "booking": str(ouvert.id)},
        format="json",
    )

    assert reponse.status_code == 409
    assert reponse.data["code"] == "wrong_booking"


# ---------------------------------------------------------------------------
# Un acompte versé ne se perd pas en confirmant
# ---------------------------------------------------------------------------


def _avec_preuve(salon, montant="112.00"):
    """Un rendez-vous demandé, dont la cliente a envoyé sa preuve."""
    from apps.payments.models import DepositProof

    booking = make_booking(salon, status=Booking.Status.REQUESTED)
    with as_tenant(salon.tenant):
        Booking.objects.filter(pk=booking.pk).update(deposit_amount=Decimal(montant))
        DepositProof.objects.create(
            tenant=salon.tenant,
            booking=booking,
            status=DepositProof.Status.SUBMITTED,
            channel="wechat",
        )
        booking.refresh_from_db()
    return booking


@pytest.mark.django_db
def test_confirmer_est_refuse_tant_que_l_acompte_n_est_pas_tranche(
    api_client, salon_a
):
    """Le trou par lequel 112 CNY ont disparu.

    Deux boutons menaient à « confirmée ». Celui-ci ne touchait ni la preuve
    ni la caisse : l'acompte restait « à vérifier » pour toujours, l'argent
    n'entrait dans aucun compte, et l'autre bouton — resté affiché —
    répondait « ce rendez-vous n'est plus en attente » à chaque clic.
    """
    booking = _avec_preuve(salon_a)
    login(api_client, salon_a.owner)

    reponse = api_client.post(
        f"/api/v1/bookings/{booking.id}/status/",
        {"status": "confirmed"},
        format="json",
    )

    assert reponse.status_code == 409
    assert reponse.data["code"] == "deposit_pending"

    with as_tenant(salon_a.tenant):
        booking.refresh_from_db()
    assert booking.status == Booking.Status.REQUESTED


@pytest.mark.django_db
def test_noter_arrivee_est_refuse_aussi(api_client, salon_a):
    """Le même trou, par l'autre transition.

    `requested` proposait aussi « Cliente arrivée » : elle sautait la
    décision sur l'acompte exactement de la même façon.
    """
    booking = _avec_preuve(salon_a)
    login(api_client, salon_a.owner)

    reponse = api_client.post(
        f"/api/v1/bookings/{booking.id}/status/",
        {"status": "checked_in"},
        format="json",
    )

    assert reponse.status_code == 409
    assert reponse.data["code"] == "deposit_pending"


@pytest.mark.django_db
def test_accepter_l_acompte_confirme_et_encaisse(api_client, salon_a):
    """Le chemin qui reste : il fait les trois choses d'un coup."""
    from apps.finance.models import Transaction

    booking = _avec_preuve(salon_a)
    login(api_client, salon_a.owner)

    reponse = api_client.post(
        f"/api/v1/bookings/{booking.id}/accept/",
        {"amount": "112.00"},
        format="json",
    )
    assert reponse.status_code == 200, reponse.data

    with as_tenant(salon_a.tenant):
        booking.refresh_from_db()
    assert booking.status == Booking.Status.CONFIRMED
    assert booking.deposit_paid is True

    with as_tenant(salon_a.tenant):
        booking.deposit_proof.refresh_from_db()
        assert booking.deposit_proof.status == "accepted"
        # L'argent est en caisse : c'est ce que la confirmation seule perdait.
        assert Transaction.objects.filter(
            kind=Transaction.Kind.INCOME, amount=Decimal("112.00")
        ).exists()


@pytest.mark.django_db
def test_une_preuve_deja_tranchee_ne_bloque_plus_rien(api_client, salon_a):
    """Le garde-fou ne doit gêner que ce qu'il protège."""
    from apps.payments.models import DepositProof

    booking = _avec_preuve(salon_a)
    with as_tenant(salon_a.tenant):
        DepositProof.objects.filter(booking=booking).update(
            status=DepositProof.Status.REJECTED
        )

    login(api_client, salon_a.owner)
    reponse = api_client.post(
        f"/api/v1/bookings/{booking.id}/status/",
        {"status": "confirmed"},
        format="json",
    )

    assert reponse.status_code == 200, reponse.data
    with as_tenant(salon_a.tenant):
        booking.refresh_from_db()
    assert booking.status == Booking.Status.CONFIRMED


@pytest.mark.django_db
def test_un_rendez_vous_sans_acompte_avance_librement(api_client, salon_a):
    booking = make_booking(salon_a, status=Booking.Status.REQUESTED)
    login(api_client, salon_a.owner)

    reponse = api_client.post(
        f"/api/v1/bookings/{booking.id}/status/",
        {"status": "confirmed"},
        format="json",
    )

    assert reponse.status_code == 200
