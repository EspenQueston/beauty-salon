"""Les coordonnees exigees a la reservation sur le mini-site.

Regle decidee avec le produit : telephone et e-mail obligatoires ; le
telephone ne contient que des chiffres (6 au moins, 15 au plus, un « + »
admis en tete) ; l'e-mail a un « @ » et un domaine.
"""

import pytest

from apps.customers.coordonnees import TelephoneInvalide, memes_chiffres, normaliser_telephone
from apps.customers.models import Customer
from apps.scheduling.models import Booking
from conftest import as_tenant
from tests.test_public_booking_api import HOST, booking_payload, next_weekday_at


def reserver(api_client, salon, heure=10, **champs):
    return api_client.post(
        "/api/v1/public/bookings",
        booking_payload(salon, next_weekday_at(heure), **champs),
        format="json",
        headers=HOST,
    )


# ---------------------------------------------------------------------------
# La regle du telephone
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("saisi", "enregistre"),
    [
        ("0612345", "0612345"),
        ("+242066112233", "+242066112233"),
        ("+86 136 1234 5678", "+8613612345678"),  # espaces d'un numero colle
        ("123456", "123456"),  # 6 chiffres : le minimum
    ],
)
def test_un_numero_de_chiffres_est_accepte_et_normalise(saisi, enregistre):
    assert normaliser_telephone(saisi) == enregistre


@pytest.mark.parametrize(
    "saisi",
    [
        "",
        "12345",  # 5 chiffres
        "+12345",  # le « + » ne compte pas comme un chiffre
        "06-12-34-56",  # tirets
        "(06) 123456",  # parentheses
        "06.12.34.56",  # points
        "0612abc345",  # lettres
        "12+3456789",  # « + » ailleurs qu'en tete
        "1234567890123456",  # 16 chiffres
    ],
)
def test_un_numero_hors_regle_est_refuse(saisi):
    with pytest.raises(TelephoneInvalide):
        normaliser_telephone(saisi)


# ---------------------------------------------------------------------------
# De bout en bout, par l'API publique
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_sans_email_la_reservation_est_refusee(api_client, salon_a):
    for email in (None, ""):
        payload = {"email": email} if email is not None else {}
        corps = booking_payload(salon_a, next_weekday_at(10), **payload)
        if email is None:
            corps.pop("email")
        reponse = api_client.post("/api/v1/public/bookings", corps, format="json", headers=HOST)
        assert reponse.status_code == 400
        assert "email" in reponse.data["detail"]
    with as_tenant(salon_a.tenant):
        assert not Booking.objects.exists()


@pytest.mark.django_db
@pytest.mark.parametrize("email", ["ab", "awa.example.com", "a@b", "@example.com", "awa@"])
def test_un_email_sans_arobase_ou_sans_domaine_est_refuse(api_client, salon_a, email):
    reponse = reserver(api_client, salon_a, email=email)

    assert reponse.status_code == 400
    assert "email" in reponse.data["detail"]


@pytest.mark.django_db
@pytest.mark.parametrize("telephone", ["", "12345", "06-12-34-56", "0612abc345"])
def test_un_telephone_hors_regle_est_refuse_par_l_api(api_client, salon_a, telephone):
    reponse = reserver(api_client, salon_a, phone=telephone)

    assert reponse.status_code == 400
    assert "phone" in reponse.data["detail"]


@pytest.mark.django_db
def test_une_reservation_valide_enregistre_le_numero_normalise(api_client, salon_a):
    reponse = reserver(api_client, salon_a, phone="+242 06 611 22 44", email="awa@example.com")

    assert reponse.status_code == 201, reponse.data
    with as_tenant(salon_a.tenant):
        booking = Booking.objects.select_related("customer").get(id=reponse.data["id"])
        assert booking.customer.phone == "+242066112244"
        assert booking.customer.email == "awa@example.com"


@pytest.mark.django_db
def test_une_cliente_connue_est_retrouvee_par_ses_chiffres(api_client, salon_a):
    """Une fiche ancienne garde ses espaces : pas de seconde fiche pour elle."""
    with as_tenant(salon_a.tenant):
        ancienne = Customer.objects.create(
            tenant=salon_a.tenant, full_name="Mei Lin", phone="+86 136 1234 5678"
        )

    reponse = reserver(api_client, salon_a, phone="+8613612345678", email="mei@example.com")

    assert reponse.status_code == 201, reponse.data
    with as_tenant(salon_a.tenant):
        assert Booking.objects.get(id=reponse.data["id"]).customer_id == ancienne.id
        # Une seule fiche pour ce numero, quelle que soit son ecriture.
        assert memes_chiffres(Customer.objects.all(), "+86 136 1234 5678").count() == 1


# ---------------------------------------------------------------------------
# La liste d'attente du mini-site suit la meme regle
# ---------------------------------------------------------------------------


def inscrire(api_client, salon, **champs):
    from tests.test_waitlist import HOST as HOTE_ATTENTE
    from tests.test_waitlist import signup_payload

    return api_client.post(
        "/api/v1/public/waitlist",
        signup_payload(salon, **champs),
        format="json",
        headers=HOTE_ATTENTE,
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("champ", "valeur"),
    [
        ("email", ""),
        ("email", "ab"),
        ("email", "a@b"),
        ("phone", "12345"),
        ("phone", "06-12-34-56"),
        ("phone", "0612abc345"),
    ],
)
def test_la_liste_d_attente_refuse_des_coordonnees_hors_regle(api_client, salon_a, champ, valeur):
    from apps.scheduling.models import WaitlistEntry

    reponse = inscrire(api_client, salon_a, **{champ: valeur})

    assert reponse.status_code == 400
    assert champ in str(reponse.data)
    with as_tenant(salon_a.tenant):
        assert not WaitlistEntry.objects.exists()


@pytest.mark.django_db
def test_la_liste_d_attente_exige_un_email(api_client, salon_a):
    from tests.test_waitlist import HOST as HOTE_ATTENTE
    from tests.test_waitlist import signup_payload

    corps = signup_payload(salon_a)
    corps.pop("email")
    reponse = api_client.post("/api/v1/public/waitlist", corps, format="json", headers=HOTE_ATTENTE)

    assert reponse.status_code == 400


@pytest.mark.django_db
def test_la_liste_d_attente_enregistre_le_numero_normalise(api_client, salon_a):
    from apps.scheduling.models import WaitlistEntry

    reponse = inscrire(api_client, salon_a, phone="+242 06 611 22 55")

    assert reponse.status_code == 201, reponse.data
    with as_tenant(salon_a.tenant):
        entree = WaitlistEntry.objects.get()
    assert entree.phone == "+242066112255"
    assert entree.email == "awa@example.com"


@pytest.mark.django_db
def test_le_salon_garde_la_saisie_libre_depuis_son_espace(api_client, salon_a):
    """La regle vise le mini-site ; la reception note un rappel comme elle peut."""
    from apps.accounts.models import Membership
    from tests.factories import MembershipFactory, UserFactory

    gerante = UserFactory()
    MembershipFactory(tenant=salon_a.tenant, user=gerante, role=Membership.Role.MANAGER)
    api_client.force_login(gerante)
    from tests.test_waitlist import signup_payload

    corps = signup_payload(salon_a, phone="06 12 34 56 78")
    corps.pop("email")
    reponse = api_client.post("/api/v1/waitlist/", corps, format="json")

    assert reponse.status_code == 201, reponse.data
