"""Domaines personnalises (offre Pro) : preuve, connexion, unicite, pause.

Le DNS est simule : `FauxDNS` repond ce que le test lui dit, pour chaque
cas — TXT absent, TXT present mais domaine pas encore pointe, tout en place.
"""

from datetime import timedelta

import pytest
from django.core.cache import cache
from django.utils import timezone

from apps.accounts.models import Membership
from apps.audit.models import AuditLog
from apps.domains import personnalises
from apps.domains.models import Domain, DomainClaim
from apps.domains.services import resolve_tenant_id
from conftest import as_tenant, salon_host
from tests.factories import MembershipFactory, UserFactory
from tests.test_abonnements import abonnement_de, medias_temporaires, offres
from tests.test_offres_pro import au_plan, pro

FIXTURES_PARTAGEES = (medias_temporaires, offres, pro)
IP_SERVEUR = "65.21.157.38"


class FauxDNS(personnalises.Lecteur):
    def __init__(self):
        self.enregistrements_txt: dict[str, list[str]] = {}
        self.enregistrements_a: dict[str, set[str]] = {}

    def txt(self, nom):
        return self.enregistrements_txt.get(nom, [])

    def adresses(self, nom):
        return self.enregistrements_a.get(nom, set())


@pytest.fixture
def dns(monkeypatch, settings):
    faux = FauxDNS()
    monkeypatch.setattr(personnalises, "LECTEUR", faux)
    settings.PLATFORM_PUBLIC_IPS = [IP_SERVEUR]
    return faux


@pytest.fixture
def salon_pro(salon_a, pro):
    au_plan(salon_a, "pro_monthly", fin=timezone.now() + timedelta(days=20))
    return salon_a


def demander(client, salon, nom="monsalon.com"):
    client.force_login(salon.owner)
    return client.post("/api/v1/domaines", {"hostname": nom}, format="json")


def prouver(dns, reponse):
    """Pose chez le « registraire » ce que les consignes demandent."""
    donnees = reponse.json()
    dns.enregistrements_txt[donnees["consignes"]["txt"]["nom"]] = [
        donnees["consignes"]["txt"]["valeur"]
    ]
    dns.enregistrements_a[donnees["hostname"]] = {IP_SERVEUR}


# ---------------------------------------------------------------------------
# Le nom
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("saisie", "attendu"),
    [
        ("https://Www.MonSalon.com/accueil", "www.monsalon.com"),
        ("monsalon.com.", "monsalon.com"),
        ("salon-élégance.fr", "xn--salon-lgance-gebb.fr"),
    ],
)
def test_le_nom_est_normalise(saisie, attendu, settings):
    settings.PLATFORM_DOMAIN = "beauty.example.com"
    assert personnalises.normaliser(saisie) == attendu


@pytest.mark.parametrize(
    "saisie", ["", "monsalon", "mon salon.com", "-x.com", "a.b.c:8080", "x@y.com", "a.123"]
)
def test_un_nom_invalide_est_refuse(saisie, settings):
    settings.PLATFORM_DOMAIN = "beauty.example.com"
    with pytest.raises(personnalises.DomaineRefuse):
        personnalises.normaliser(saisie)


def test_le_domaine_de_la_plateforme_ne_se_reclame_pas(settings):
    settings.PLATFORM_DOMAIN = "beauty.example.com"
    for nom in ("beauty.example.com", "autre.beauty.example.com"):
        with pytest.raises(personnalises.DomaineRefuse) as refus:
            personnalises.normaliser(nom)
        assert refus.value.code == "domaine_plateforme"


# ---------------------------------------------------------------------------
# Droits
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_standard_ne_peut_pas_demander_de_domaine(api_client, salon_a, pro, dns):
    abonnement_de(salon_a)

    reponse = demander(api_client, salon_a)

    assert reponse.status_code == 403
    assert reponse.json()["code"] == "offre_pro_requise"


@pytest.mark.django_db
def test_seul_le_proprietaire_gere_le_domaine(api_client, salon_pro, dns):
    gerante = UserFactory()
    MembershipFactory(tenant=salon_pro.tenant, user=gerante, role=Membership.Role.MANAGER)
    api_client.force_login(gerante)

    assert (
        api_client.post("/api/v1/domaines", {"hostname": "x.com"}, format="json").status_code == 403
    )
    assert api_client.get("/api/v1/domaines").status_code == 403


# ---------------------------------------------------------------------------
# Preuve et connexion
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_demander_ne_route_rien(api_client, salon_pro, dns):
    reponse = demander(api_client, salon_pro)

    assert reponse.status_code == 201
    consignes = reponse.json()["consignes"]
    assert consignes["txt"]["nom"] == "_beauty-salon.monsalon.com"
    assert consignes["txt"]["valeur"].startswith("bs-")
    assert consignes["routage"] == {"type": "A", "nom": "monsalon.com", "valeur": IP_SERVEUR}
    assert not Domain.objects.filter(hostname="monsalon.com").exists()
    assert resolve_tenant_id("monsalon.com") is None


@pytest.mark.django_db
def test_un_sous_domaine_se_pointe_par_cname(api_client, salon_pro, dns):
    consignes = demander(api_client, salon_pro, "www.monsalon.com").json()["consignes"]

    assert consignes["routage"]["type"] == "CNAME"
    assert consignes["routage"]["valeur"] == salon_host("blondrose")


@pytest.mark.django_db
def test_sans_txt_ou_sans_pointage_rien_n_est_relie(api_client, salon_pro, dns):
    demande = demander(api_client, salon_pro).json()
    url = f"/api/v1/domaines/{demande['id']}/verifier"

    sans_txt = api_client.post(url)
    assert sans_txt.status_code == 400 and sans_txt.json()["code"] == "txt_absent"

    dns.enregistrements_txt["_beauty-salon.monsalon.com"] = [demande["consignes"]["txt"]["valeur"]]
    sans_pointage = api_client.post(url)
    assert sans_pointage.status_code == 400 and sans_pointage.json()["code"] == "routage"

    dns.enregistrements_txt["_beauty-salon.monsalon.com"] = ["bs-un-autre-jeton"]
    dns.enregistrements_a["monsalon.com"] = {IP_SERVEUR}
    mauvais = api_client.post(url)
    assert mauvais.status_code == 400 and mauvais.json()["code"] == "txt_incorrect"

    assert not Domain.objects.filter(hostname="monsalon.com").exists()


@pytest.mark.django_db
def test_la_preuve_relie_le_domaine_et_le_route(api_client, salon_pro, dns):
    from django.test import Client

    reponse = demander(api_client, salon_pro)
    prouver(dns, reponse)

    verifie = api_client.post(f"/api/v1/domaines/{reponse.json()['id']}/verifier")

    assert verifie.status_code == 200, verifie.json()
    assert verifie.json()["relie"] is True
    domaine = Domain.objects.get(hostname="monsalon.com")
    assert domaine.kind == Domain.Kind.CUSTOM_DOMAIN and domaine.verified_at
    assert resolve_tenant_id("monsalon.com") == str(salon_pro.tenant.id)
    # Caddy peut obtenir son certificat.
    assert Client().get("/interne/certificat", {"domain": "monsalon.com"}).status_code == 200
    assert AuditLog.objects.filter(action="domain.connected").exists()


@pytest.mark.django_db
def test_un_domaine_ne_se_relie_qu_a_un_seul_salon(api_client, salon_pro, salon_b, pro, dns):
    au_plan(salon_b, "pro_monthly", fin=timezone.now() + timedelta(days=20))
    premiere = demander(api_client, salon_pro)
    prouver(dns, premiere)
    api_client.post(f"/api/v1/domaines/{premiere.json()['id']}/verifier")
    api_client.logout()

    # Le second salon peut deposer une demande, mais pas relier le domaine.
    reponse = demander(api_client, salon_b)
    assert reponse.status_code == 409
    assert reponse.json()["code"] == "deja_pris"
    assert Domain.objects.get(hostname="monsalon.com").tenant_id == salon_pro.tenant.id


@pytest.mark.django_db
def test_un_salon_ne_voit_ni_ne_retire_le_domaine_d_un_autre(api_client, salon_pro, salon_b, dns):
    abonnement_de(salon_b)
    demande = demander(api_client, salon_pro).json()
    api_client.logout()
    api_client.force_login(salon_b.owner)

    assert api_client.get("/api/v1/domaines").json() == []
    assert api_client.delete(f"/api/v1/domaines/{demande['id']}").status_code == 404
    assert api_client.post(f"/api/v1/domaines/{demande['id']}/verifier").status_code in (403, 404)
    with as_tenant(salon_pro.tenant):
        assert DomainClaim.objects.filter(pk=demande["id"]).exists()


@pytest.mark.django_db
def test_retirer_coupe_le_routage(api_client, salon_pro, dns):
    reponse = demander(api_client, salon_pro)
    prouver(dns, reponse)
    api_client.post(f"/api/v1/domaines/{reponse.json()['id']}/verifier")

    assert api_client.delete(f"/api/v1/domaines/{reponse.json()['id']}").status_code == 204

    assert not Domain.objects.filter(hostname="monsalon.com").exists()
    assert resolve_tenant_id("monsalon.com") is None
    assert AuditLog.objects.filter(action="domain.removed").exists()


# ---------------------------------------------------------------------------
# Pause
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_sans_pro_le_domaine_se_met_en_pause_et_renvoie_au_sous_domaine(api_client, salon_pro, dns):
    reponse = demander(api_client, salon_pro)
    prouver(dns, reponse)
    api_client.post(f"/api/v1/domaines/{reponse.json()['id']}/verifier")
    assert resolve_tenant_id("monsalon.com") == str(salon_pro.tenant.id)

    # Pro echue depuis plus que le delai de grace.
    au_plan(salon_pro, "pro_monthly", fin=timezone.now() - timedelta(days=10))
    cache.clear()

    assert resolve_tenant_id("monsalon.com") is None
    public = api_client.get("/api/v1/public/salon", HTTP_X_TENANT_HOST="monsalon.com")
    assert public.status_code == 404
    assert public.json()["canonique"] == salon_host("blondrose")
    # Rien n'est efface : le domaine reste, en pause.
    assert Domain.objects.filter(hostname="monsalon.com").exists()
    liste = api_client.get("/api/v1/domaines").json()
    assert liste[0]["en_pause"] is True


@pytest.mark.django_db
def test_un_domaine_non_verifie_saisi_a_la_main_ne_route_pas(salon_a):
    Domain.objects.create(
        tenant=salon_a.tenant, hostname="saisi-a-la-main.com", kind=Domain.Kind.CUSTOM_DOMAIN
    )

    assert resolve_tenant_id("saisi-a-la-main.com") is None


@pytest.mark.django_db
def test_la_liste_pour_le_proxy_ne_contient_que_les_domaines_verifies(salon_a):
    from io import StringIO

    from django.core.management import call_command

    Domain.objects.create(
        tenant=salon_a.tenant,
        hostname="verifie.com",
        kind=Domain.Kind.CUSTOM_DOMAIN,
        verified_at=timezone.now(),
    )
    Domain.objects.create(
        tenant=salon_a.tenant, hostname="pas-verifie.com", kind=Domain.Kind.CUSTOM_DOMAIN
    )
    sortie = StringIO()

    call_command("domaines_personnalises", stdout=sortie)

    assert sortie.getvalue().split() == ["verifie.com"]
