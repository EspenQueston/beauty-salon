"""Liste d'attente : les parcours complets, et ce qu'elle doit refuser.

Complète `test_waitlist.py` (ce qu'elle ne fait pas : réserver, fuir d'un
salon à l'autre). Ici : le parcours d'une cliente jusqu'au rappel, et les
saisies qui n'ont pas de sens — une période déjà passée, un prestataire qui
ne fait pas la prestation, une deuxième inscription identique.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.models import Membership
from apps.notifications.models import Genre, Notification
from apps.scheduling.models import WaitlistEntry
from conftest import as_tenant, salon_host
from tests.factories import MembershipFactory, ServiceFactory, StaffMemberFactory, UserFactory
from tests.test_waitlist import HOST, login, signup_payload

URL = "/api/v1/public/waitlist"


def inscrire(client, salon, **champs):
    hote = {"Host": salon_host(salon.tenant.slug)}
    return client.post(URL, signup_payload(salon, **champs), format="json", headers=hote)


def aujourd_hui(salon):
    """La date du jour dans le fuseau du salon : c'est celle que voit la cliente."""
    from zoneinfo import ZoneInfo

    return timezone.now().astimezone(ZoneInfo(salon.tenant.timezone)).date()


# ---------------------------------------------------------------------------
# Le parcours complet
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_parcours_complet_inscription_rappel_puis_classement(api_client, salon_a):
    """La cliente s'inscrit ; le salon est prévenu, la rappelle, puis classe."""
    reponse = inscrire(
        api_client, salon_a, staff_member=str(salon_a.staff.id), note="Plutôt le soir"
    )
    assert reponse.status_code == 201, reponse.data
    identifiant = reponse.data["id"]

    # Le salon est prévenu, avec un lien vers la liste.
    with as_tenant(salon_a.tenant):
        alerte = Notification.objects.filter(genre=Genre.LISTE_ATTENTE).first()
    assert alerte is not None and alerte.lien == "/liste-attente"

    login(api_client, salon_a.owner)
    tete = {"X-Tenant-Id": str(salon_a.tenant.id)}

    liste = api_client.get("/api/v1/waitlist/", headers=tete).data
    lignes = liste["results"] if isinstance(liste, dict) else liste
    (ligne,) = lignes
    assert ligne["staff_member_name"] == "Fatou"
    assert ligne["note"] == "Plutôt le soir"

    rappel = api_client.post(f"/api/v1/waitlist/{identifiant}/contacted/", headers=tete)
    assert rappel.status_code == 200 and rappel.data["status"] == "contacted"
    assert rappel.data["contacted_at"]

    classe = api_client.post(
        f"/api/v1/waitlist/{identifiant}/close/", {"booked": True}, format="json", headers=tete
    )
    assert classe.status_code == 200 and classe.data["status"] == "booked"

    # Classée : elle quitte la liste du jour, mais reste dans l'historique.
    par_defaut = api_client.get("/api/v1/waitlist/", headers=tete).data
    tout = api_client.get("/api/v1/waitlist/?status=all", headers=tete).data
    compter = lambda d: len(d["results"] if isinstance(d, dict) else d)  # noqa: E731
    assert compter(par_defaut) == 0 and compter(tout) == 1


@pytest.mark.django_db
def test_classer_sans_suite(api_client, salon_a):
    identifiant = inscrire(api_client, salon_a).data["id"]
    login(api_client, salon_a.owner)

    classe = api_client.post(
        f"/api/v1/waitlist/{identifiant}/close/",
        {},
        format="json",
        headers={"X-Tenant-Id": str(salon_a.tenant.id)},
    )

    assert classe.data["status"] == "closed"


# ---------------------------------------------------------------------------
# Les saisies qui n'ont pas de sens
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_une_periode_deja_passee_est_refusee(api_client, salon_a):
    jour = aujourd_hui(salon_a)
    reponse = inscrire(
        api_client,
        salon_a,
        preferred_from=(jour - timedelta(days=10)).isoformat(),
        preferred_to=(jour - timedelta(days=2)).isoformat(),
    )

    assert reponse.status_code == 400
    assert "preferred_to" in reponse.data["detail"]


@pytest.mark.django_db
def test_une_periode_commencee_hier_reste_acceptee_et_commence_aujourd_hui(api_client, salon_a):
    """Le formulaire du téléphone peut proposer « hier » (fuseau) : on ne
    refuse pas la cliente pour ça, on fait commencer la période aujourd'hui."""
    jour = aujourd_hui(salon_a)
    reponse = inscrire(
        api_client,
        salon_a,
        preferred_from=(jour - timedelta(days=1)).isoformat(),
        preferred_to=(jour + timedelta(days=7)).isoformat(),
    )

    assert reponse.status_code == 201, reponse.data
    with as_tenant(salon_a.tenant):
        entree = WaitlistEntry.objects.get(id=reponse.data["id"])
    assert entree.preferred_from == jour


@pytest.mark.django_db
def test_une_periode_trop_lointaine_est_refusee(api_client, salon_a):
    jour = aujourd_hui(salon_a)
    reponse = inscrire(
        api_client,
        salon_a,
        preferred_from=(jour + timedelta(days=500)).isoformat(),
        preferred_to=(jour + timedelta(days=520)).isoformat(),
    )

    assert reponse.status_code == 400


@pytest.mark.django_db
def test_un_prestataire_d_un_autre_salon_est_refuse(api_client, salon_a, salon_b):
    reponse = inscrire(api_client, salon_a, staff_member=str(salon_b.staff.id))

    assert reponse.status_code == 400
    assert "staff_member" in reponse.data["detail"]


@pytest.mark.django_db
def test_un_prestataire_qui_ne_fait_pas_la_prestation_est_refuse(api_client, salon_a):
    with as_tenant(salon_a.tenant):
        autre = StaffMemberFactory(tenant=salon_a.tenant, name="Grâce")

    reponse = inscrire(api_client, salon_a, staff_member=str(autre.id))

    assert reponse.status_code == 400
    assert "staff_member" in reponse.data["detail"]


@pytest.mark.django_db
def test_une_prestation_retiree_est_refusee(api_client, salon_a):
    with as_tenant(salon_a.tenant):
        retiree = ServiceFactory(
            tenant=salon_a.tenant, category=salon_a.service.category, active=False
        )

    reponse = inscrire(api_client, salon_a, service=str(retiree.id))

    assert reponse.status_code in (400, 404)
    with as_tenant(salon_a.tenant):
        assert not WaitlistEntry.objects.exists()


@pytest.mark.django_db
def test_une_seconde_inscription_identique_ne_cree_pas_de_doublon(api_client, salon_a):
    """Elle revient le lendemain et se réinscrit : une ligne, mise à jour."""
    jour = aujourd_hui(salon_a)
    premiere = inscrire(api_client, salon_a)
    seconde = inscrire(
        api_client,
        salon_a,
        phone="+242 06 611 22 33",  # mêmes chiffres, autre écriture
        preferred_to=(jour + timedelta(days=30)).isoformat(),
        note="Toujours dispo",
    )

    assert seconde.status_code == 201, seconde.data
    assert seconde.data["id"] == premiere.data["id"]
    with as_tenant(salon_a.tenant):
        (entree,) = WaitlistEntry.objects.all()
    assert entree.preferred_to == jour + timedelta(days=30)
    assert entree.note == "Toujours dispo"


@pytest.mark.django_db
def test_apres_classement_une_nouvelle_demande_cree_une_nouvelle_ligne(api_client, salon_a):
    premiere = inscrire(api_client, salon_a).data["id"]
    with as_tenant(salon_a.tenant):
        WaitlistEntry.objects.filter(id=premiere).update(status=WaitlistEntry.Status.CLOSED)

    seconde = inscrire(api_client, salon_a).data["id"]

    assert seconde != premiere


@pytest.mark.django_db
def test_la_note_trop_longue_est_refusee_proprement(api_client, salon_a):
    reponse = inscrire(api_client, salon_a, note="x" * 400)

    assert reponse.status_code == 400
    assert "note" in reponse.data["detail"]


@pytest.mark.django_db
def test_la_reponse_ne_renvoie_aucune_donnee_du_salon(api_client, salon_a):
    """Une inscription anonyme : la réponse ne dit rien d'autre qu'un accusé."""
    reponse = inscrire(api_client, salon_a)

    assert set(reponse.data) == {"id", "detail"}


# ---------------------------------------------------------------------------
# Côté salon
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_la_receptionniste_rappelle_et_classe(api_client, salon_a):
    identifiant = inscrire(api_client, salon_a).data["id"]
    accueil = UserFactory()
    MembershipFactory(tenant=salon_a.tenant, user=accueil, role=Membership.Role.RECEPTIONIST)
    login(api_client, accueil)
    tete = {"X-Tenant-Id": str(salon_a.tenant.id)}

    assert (
        api_client.post(f"/api/v1/waitlist/{identifiant}/contacted/", headers=tete).status_code
        == 200
    )
    assert (
        api_client.post(
            f"/api/v1/waitlist/{identifiant}/close/", {}, format="json", headers=tete
        ).status_code
        == 200
    )


@pytest.mark.django_db
def test_un_salon_ne_peut_pas_classer_la_demande_d_un_autre(api_client, salon_a, salon_b):
    identifiant = inscrire(api_client, salon_b).data["id"]
    login(api_client, salon_a.owner)

    reponse = api_client.post(
        f"/api/v1/waitlist/{identifiant}/close/",
        {},
        format="json",
        headers={"X-Tenant-Id": str(salon_a.tenant.id)},
    )

    assert reponse.status_code == 404
    with as_tenant(salon_b.tenant):
        assert WaitlistEntry.objects.get(id=identifiant).status == WaitlistEntry.Status.WAITING


@pytest.mark.django_db
def test_le_salon_ne_peut_pas_rattacher_une_demande_a_la_prestation_d_un_autre(
    api_client, salon_a, salon_b
):
    identifiant = inscrire(api_client, salon_a).data["id"]
    login(api_client, salon_a.owner)

    reponse = api_client.patch(
        f"/api/v1/waitlist/{identifiant}/",
        {"service": str(salon_b.service.id)},
        format="json",
        headers={"X-Tenant-Id": str(salon_a.tenant.id)},
    )

    assert reponse.status_code == 400


@pytest.mark.django_db
def test_sans_session_la_liste_du_salon_est_fermee(api_client, salon_a):
    inscrire(api_client, salon_a)

    assert api_client.get("/api/v1/waitlist/", headers=HOST).status_code in (401, 403)
