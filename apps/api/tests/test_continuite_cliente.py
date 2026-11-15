"""L'historique suit l'adresse e-mail, et un compte pro n'est jamais cliente.

Deux décisions du 2026-10-05 :

  - **la continuité** : réserver sans compte, puis créer un compte avec la
    même adresse, fait apparaître les anciens rendez-vous — mais seulement
    une fois l'adresse vérifiée, sinon il suffirait de s'inscrire avec
    l'adresse d'une autre pour lire les siens ;
  - **la séparation** : un compte de salon (propriétaire, gérante, équipe)
    n'est jamais aussi un compte cliente.
"""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from apps.accounts import verification
from apps.accounts.models import Membership
from apps.clients.models import ClientProfile, ClientSalonLink
from conftest import as_tenant, salon_host
from tests.factories import MembershipFactory, UserFactory
from tests.test_client_account import PASSWORD, signup

HOST_A = {"Host": salon_host("blondrose")}
EMAIL = "awa@example.com"


def reserver_sans_compte(
    client, salon, host, *, email=EMAIL, semaines=1, heure=11, telephone="+242066112233"
):
    """Une réservation anonyme, un lundi à venir."""
    fuseau = ZoneInfo(salon.tenant.timezone or "Africa/Brazzaville")
    aujourd_hui = datetime.now(fuseau).date()
    ecart = (0 - aujourd_hui.weekday()) % 7 or 7
    jour: date = aujourd_hui + timedelta(days=ecart + 7 * semaines)
    debut = datetime.combine(jour, time(heure, 0), tzinfo=fuseau)
    reponse = client.post(
        "/api/v1/public/bookings",
        {
            "service": str(salon.service.id),
            "starts_at": debut.isoformat(),
            "full_name": "Awa Diallo",
            "phone": telephone,
            "email": email,
            "accepts_policy": True,
        },
        format="json",
        headers=host,
    )
    assert reponse.status_code == 201, reponse.data
    return reponse.data


def verifier_adresse(user):
    user.refresh_from_db()
    return verification.verifier(verification.jeton(user))


def rendez_vous(client):
    reponse = client.get("/api/v1/public/client/bookings", headers=HOST_A)
    assert reponse.status_code == 200, reponse.data
    return reponse.data["bookings"]


# ---------------------------------------------------------------------------
# La continuité
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_les_rendez_vous_pris_sans_compte_apparaissent_une_fois_l_adresse_verifiee(
    api_client, salon_a
):
    reserver_sans_compte(api_client, salon_a, HOST_A)

    assert signup(api_client, HOST_A, email=EMAIL).status_code == 201
    from apps.accounts.models import User

    compte = User.objects.get(email=EMAIL)

    # Adresse non vérifiée : rien n'est rattaché — l'adresse n'est pas prouvée.
    assert rendez_vous(api_client) == []
    assert not ClientSalonLink.objects.filter(user=compte).exists()

    verifier_adresse(compte)

    lignes = rendez_vous(api_client)
    assert len(lignes) == 1
    assert lignes[0]["salon_slug"] == salon_a.tenant.slug


@pytest.mark.django_db
def test_l_historique_retrouve_couvre_tous_les_salons(api_client, salon_a, salon_b):
    hote_b = {"Host": salon_host(salon_b.tenant.slug)}
    reserver_sans_compte(api_client, salon_a, HOST_A)
    reserver_sans_compte(api_client, salon_b, hote_b)
    # L'adresse saisie avec d'autres majuscules reste la même adresse.
    reserver_sans_compte(api_client, salon_a, HOST_A, email="Awa@Example.com", semaines=2)

    signup(api_client, HOST_A, email=EMAIL)
    from apps.accounts.models import User

    verifier_adresse(User.objects.get(email=EMAIL))

    salons = {ligne["salon_slug"] for ligne in rendez_vous(api_client)}
    assert salons == {salon_a.tenant.slug, salon_b.tenant.slug}
    assert len(rendez_vous(api_client)) == 3


@pytest.mark.django_db
def test_une_reservation_sans_session_rejoint_le_compte_verifie(api_client, salon_a, salon_b):
    """Elle a un compte mais réserve sans se connecter : le rendez-vous suit."""
    from apps.accounts.models import User

    signup(api_client, HOST_A, email=EMAIL)
    verifier_adresse(User.objects.get(email=EMAIL))
    api_client.logout()

    hote_b = {"Host": salon_host(salon_b.tenant.slug)}
    reponse = reserver_sans_compte(api_client, salon_b, hote_b)
    # La réponse publique ne trahit pas qu'un compte existe pour l'adresse.
    assert "compte" not in str(reponse).lower()

    api_client.login(email=EMAIL, password="Tresses-2026-Brazza")
    assert [ligne["salon_slug"] for ligne in rendez_vous(api_client)] == [salon_b.tenant.slug]


@pytest.mark.django_db
def test_une_adresse_non_verifiee_ne_capte_aucune_reservation(api_client, salon_a):
    from apps.accounts.models import User

    signup(api_client, HOST_A, email=EMAIL)
    api_client.logout()

    reserver_sans_compte(api_client, salon_a, HOST_A)

    assert not ClientSalonLink.objects.filter(user=User.objects.get(email=EMAIL)).exists()


# ---------------------------------------------------------------------------
# La séparation pro / cliente
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_une_proprietaire_ne_peut_pas_creer_de_compte_cliente(api_client, salon_a):
    reponse = signup(api_client, HOST_A, email=salon_a.owner.email)

    assert reponse.status_code == 400
    assert not ClientProfile.objects.filter(user=salon_a.owner).exists()


@pytest.mark.django_db
def test_un_ancien_profil_cliente_ne_rouvre_pas_l_espace_a_un_compte_pro(api_client, salon_a):
    """Données d'avant la séparation : le compte reste traité en pro."""
    ClientProfile.objects.create(user=salon_a.owner)
    api_client.login(email=salon_a.owner.email, password=PASSWORD)

    session = api_client.get("/api/v1/public/client/session", headers=HOST_A).data
    assert session["is_client"] is False
    assert api_client.get("/api/v1/public/client/bookings", headers=HOST_A).status_code == 403
    assert api_client.get("/api/v1/public/client/parrainage", headers=HOST_A).status_code == 403


@pytest.mark.django_db
def test_une_reservation_avec_l_adresse_d_une_proprietaire_ne_lui_ouvre_pas_d_espace(
    api_client, salon_a, salon_b
):
    from apps.accounts.models import User

    proprietaire = User.objects.get(pk=salon_a.owner.pk)
    User.objects.filter(pk=proprietaire.pk).update(email=EMAIL)
    hote_b = {"Host": salon_host(salon_b.tenant.slug)}

    reserver_sans_compte(api_client, salon_b, hote_b)

    assert not ClientSalonLink.objects.filter(user=proprietaire).exists()


# L'invitation se relit sur l'alias `admin` (aucun salon au moment du clic).
@pytest.mark.django_db(databases=["default", "admin"], transaction=True)
def test_un_compte_cliente_ne_peut_pas_rejoindre_une_equipe(api_client, salon_a):
    from apps.accounts.models import Invitation
    from apps.accounts.services import InvitationError, accept_invitation

    signup(api_client, HOST_A, email=EMAIL)
    api_client.logout()
    with as_tenant(salon_a.tenant):
        _, jeton = Invitation.issue(tenant=salon_a.tenant, email=EMAIL, role="staff")

    with pytest.raises(InvitationError):
        accept_invitation(token=jeton, password="Tresses-2026-Brazza")

    assert not Membership.objects.filter(user__email=EMAIL, status="active").exists()


@pytest.mark.django_db
def test_un_membre_d_equipe_existant_ne_devient_pas_cliente(api_client, salon_a):
    membre = UserFactory()
    MembershipFactory(tenant=salon_a.tenant, user=membre, role=Membership.Role.STAFF)

    assert signup(api_client, HOST_A, email=membre.email).status_code == 400


# ---------------------------------------------------------------------------
# Audit du 2026-10-05 : la fiche retrouvee par le telephone n'ouvre rien
# ---------------------------------------------------------------------------
#
# Une fiche cliente se retrouve par le numero de telephone, que n'importe qui
# peut saisir. Avant l'audit, un compte rattache a une fiche en voyait tous
# les rendez-vous : reserver une fois avec le numero d'une autre suffisait a
# lire son historique (QR d'arrivee et lien de paiement compris).

VICTIME = "victime@example.com"
PIRATE = "pirate@example.com"
TELEPHONE_VICTIME = "+242066000111"


def compte_verifie(client, email, mot_de_passe="Tresses-2026-Brazza"):
    from apps.accounts.models import User

    assert signup(client, HOST_A, email=email, password=mot_de_passe).status_code == 201
    verifier_adresse(User.objects.get(email=email))
    client.logout()


def se_connecter(client, email, mot_de_passe="Tresses-2026-Brazza"):
    client.logout()
    assert client.login(email=email, password=mot_de_passe)


@pytest.mark.django_db
def test_reserver_avec_le_numero_d_une_autre_ne_montre_pas_son_historique(api_client, salon_a):
    compte_verifie(api_client, VICTIME)
    compte_verifie(api_client, PIRATE)
    reserver_sans_compte(api_client, salon_a, HOST_A, email=VICTIME, telephone=TELEPHONE_VICTIME)

    # Sans session, avec le numero de la victime et sa propre adresse.
    reserver_sans_compte(
        api_client, salon_a, HOST_A, email=PIRATE, telephone=TELEPHONE_VICTIME, semaines=2
    )

    se_connecter(api_client, PIRATE)
    assert len(rendez_vous(api_client)) == 1  # le sien, et lui seul
    se_connecter(api_client, VICTIME)
    assert len(rendez_vous(api_client)) == 1


@pytest.mark.django_db
def test_meme_connecte_le_numero_d_une_autre_n_ouvre_pas_sa_fiche(api_client, salon_a):
    compte_verifie(api_client, VICTIME)
    compte_verifie(api_client, PIRATE)
    reserver_sans_compte(api_client, salon_a, HOST_A, email=VICTIME, telephone=TELEPHONE_VICTIME)

    se_connecter(api_client, PIRATE)
    reserver_sans_compte(
        api_client, salon_a, HOST_A, email=PIRATE, telephone=TELEPHONE_VICTIME, semaines=2
    )

    assert len(rendez_vous(api_client)) == 1


@pytest.mark.django_db
def test_une_reservation_n_ecrit_pas_son_adresse_sur_une_fiche_existante(api_client, salon_a):
    """La fiche du salon sans adresse ne devient pas celle de qui reserve."""
    from apps.customers.models import Customer

    with as_tenant(salon_a.tenant):
        fiche = Customer.objects.create(
            tenant=salon_a.tenant, full_name="Cliente du salon", phone=TELEPHONE_VICTIME
        )

    reserver_sans_compte(api_client, salon_a, HOST_A, email=PIRATE, telephone=TELEPHONE_VICTIME)

    with as_tenant(salon_a.tenant):
        fiche.refresh_from_db()
    assert fiche.email == ""


@pytest.mark.django_db
def test_qui_cree_la_fiche_en_premier_ne_capte_ni_les_rendez_vous_ni_les_e_mails(
    api_client, salon_a, mailoutbox
):
    """Le pirate reserve le premier avec le numero de sa cible ; elle reserve
    ensuite avec ce numero et sa propre adresse."""
    from apps.notifications.tasks import send_booking_notifications
    from apps.scheduling.models import Booking

    compte_verifie(api_client, PIRATE)
    reserver_sans_compte(api_client, salon_a, HOST_A, email=PIRATE, telephone=TELEPHONE_VICTIME)
    reponse = reserver_sans_compte(
        api_client, salon_a, HOST_A, email=VICTIME, telephone=TELEPHONE_VICTIME, semaines=2
    )

    with as_tenant(salon_a.tenant):
        sa_reservation = Booking.objects.get(pk=reponse["id"])
    assert sa_reservation.contact_email == VICTIME

    mailoutbox.clear()
    send_booking_notifications(str(sa_reservation.id), str(salon_a.tenant.id))
    destinataires = {adresse for courriel in mailoutbox for adresse in courriel.to}
    assert PIRATE not in destinataires

    se_connecter(api_client, PIRATE)
    assert len(rendez_vous(api_client)) == 1
