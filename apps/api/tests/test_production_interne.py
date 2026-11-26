"""Ce qui ne se voit qu'une fois en ligne, verifie avant d'y aller.

Deux mecanismes n'ont aucun effet en developpement, ou le navigateur, Next
et Django tournent sur la meme machine sans proxy devant eux :

  - la question que Caddy pose avant d'emettre le certificat d'un
    sous-domaine de salon ;
  - l'exemption du serveur de rendu dans les limites de debit.

Tous deux decident pourtant, en production, si un mini-site s'affiche.
"""

import pytest
from django.conf import settings
from django.test import override_settings
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from apps.common.throttling import ScopedRateThrottle
from apps.domains.models import Domain
from conftest import salon_host
from tests.factories import DomainFactory

URL = "/interne/certificat"


def autorise(client, hote: str) -> int:
    return client.get(URL, {"domain": hote}).status_code


# ---------------------------------------------------------------------------
# Certificats a la demande
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("prefixe", ["", "app.", "api.", "www."])
def test_les_hotes_de_la_plateforme_sont_certifies(client, prefixe):
    assert autorise(client, f"{prefixe}{settings.PLATFORM_DOMAIN}") == 200


@pytest.mark.django_db
def test_le_sous_domaine_d_un_salon_est_certifie(client, tenant_a):
    assert autorise(client, salon_host("blondrose")) == 200


@pytest.mark.django_db
def test_un_nom_invente_ne_l_est_pas(client, tenant_a):
    """Sinon mille visites sur des noms inventes epuiseraient le quota de
    Let's Encrypt, et plus aucun vrai salon n'obtiendrait de certificat."""
    assert autorise(client, salon_host("nexistepas")) == 404
    assert autorise(client, "exemple.com") == 404


@pytest.mark.django_db
def test_la_casse_et_le_point_final_ne_changent_rien(client, tenant_a):
    assert autorise(client, salon_host("BlondRose") + ".") == 200


@pytest.mark.django_db
def test_un_domaine_desactive_n_est_plus_certifie(client, tenant_a):
    Domain.objects.filter(tenant=tenant_a).update(active=False)

    assert autorise(client, salon_host("blondrose")) == 404


@pytest.mark.django_db
def test_un_domaine_personnalise_attend_la_preuve_de_propriete(client, tenant_a):
    """Enregistrer `exemple.com` sans le posseder ne doit pas suffire a
    faire travailler le serveur pour lui."""
    domaine = DomainFactory(
        tenant=tenant_a,
        hostname="salon-blondrose.com",
        kind=Domain.Kind.CUSTOM_DOMAIN,
        is_primary=False,
        verified_at=None,
    )
    assert autorise(client, "salon-blondrose.com") == 404

    domaine.verified_at = timezone.now()
    domaine.save()
    assert autorise(client, "salon-blondrose.com") == 200


@pytest.mark.django_db
def test_une_question_sans_nom_est_refusee(client):
    assert client.get(URL).status_code == 400


@pytest.mark.django_db
def test_la_route_ne_fait_que_lire(client):
    assert client.post(URL, {"domain": settings.PLATFORM_DOMAIN}).status_code == 405


# ---------------------------------------------------------------------------
# Limites de debit et serveur de rendu
# ---------------------------------------------------------------------------


class _VueLimitee(APIView):
    authentication_classes = []
    permission_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "public_read"

    def get(self, request):
        return Response({"ok": True})


@pytest.fixture
def une_requete_par_minute(monkeypatch):
    monkeypatch.setattr(ScopedRateThrottle, "THROTTLE_RATES", {"public_read": "1/min"})


def appeler(**entetes) -> int:
    requete = APIRequestFactory().get("/", **entetes)
    return _VueLimitee.as_view()(requete).status_code


def test_c_est_la_limite_de_l_application_qui_s_applique():
    (classe,) = api_settings.DEFAULT_THROTTLE_CLASSES
    assert classe is ScopedRateThrottle


@override_settings(INTERNAL_API_TOKEN="")
def test_un_visiteur_reste_limite(une_requete_par_minute):
    assert appeler() == 200
    assert appeler() == 429


@override_settings(INTERNAL_API_TOKEN="jeton-de-rendu")
def test_le_serveur_de_rendu_n_est_pas_compte(une_requete_par_minute):
    """Tous les rendus de mini-site partent de la meme adresse : comptes, ils
    partageraient un seul compteur pour toute la plateforme."""
    for _ in range(5):
        assert appeler(HTTP_X_INTERNAL_TOKEN="jeton-de-rendu") == 200


@override_settings(INTERNAL_API_TOKEN="jeton-de-rendu")
def test_un_faux_jeton_ne_contourne_rien(une_requete_par_minute):
    assert appeler(HTTP_X_INTERNAL_TOKEN="devine") == 200
    assert appeler(HTTP_X_INTERNAL_TOKEN="devine") == 429


@override_settings(INTERNAL_API_TOKEN="")
def test_sans_jeton_configure_personne_n_est_exempte(une_requete_par_minute):
    """Un reglage oublie doit retomber sur la limite, pas sur une porte
    ouverte : un en-tete vide ne vaut pas un jeton vide."""
    assert appeler(HTTP_X_INTERNAL_TOKEN="") == 200
    assert appeler(HTTP_X_INTERNAL_TOKEN="") == 429
