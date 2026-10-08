"""Interfaces A/B et KKIAPAY : données visibles, permissions et absence de secrets."""

import pytest
from django.contrib.auth.models import Permission
from django.urls import reverse
from django.utils import timezone

from apps.billing import kkiapay
from apps.billing.models import KkiapayIntent, PlatformPaymentMethod
from apps.parrainage import clients, services
from apps.parrainage.models import PolitiqueSalon
from conftest import as_tenant
from tests.factories import UserFactory
from tests.test_abonnements import ADMIN, moyens, offres
from tests.test_parrainage import filleul_de, remise_pour
from tests.test_parrainage_v2 import attribution, confirmer, kki_config, politique_b

pytestmark = ADMIN
FIXTURES = (moyens, offres, kki_config, politique_b)


@pytest.fixture
def admin_client(client):
    client.force_login(UserFactory(is_staff=True, is_superuser=True, is_platform_admin=True))
    return client


def test_accueil_propose_les_deux_programmes_et_kkiapay(admin_client):
    body = admin_client.get(reverse("admin:index")).content.decode()
    for modele in (
        "parrainage_politiquesalon",
        "parrainage_recompenseclient",
        "parrainage_politiqueplateforme",
        "parrainage_remise",
        "billing_kkiapayintent",
        "parrainage_evenementparrainage",
    ):
        assert reverse(f"admin:{modele}_changelist") in body


def test_raccourcis_respectent_les_permissions(client):
    user = UserFactory(is_staff=True)
    user.user_permissions.add(Permission.objects.get(codename="view_remise"))
    client.force_login(user)
    body = client.get(reverse("admin:index")).content.decode()
    assert reverse("admin:parrainage_remise_changelist") in body
    assert reverse("admin:billing_kkiapayintent_changelist") not in body
    assert reverse("admin:parrainage_recompenseclient_changelist") not in body


def test_kkiapay_diagnostic_ne_divulgue_aucune_cle(admin_client, settings):
    settings.KKIAPAY_ENABLED = False
    settings.KKIAPAY_SANDBOX = True
    settings.KKIAPAY_ALLOWED_COUNTRIES = []
    for suffix in ("PUBLIC_KEY", "PRIVATE_KEY", "SECRET_KEY", "WEBHOOK_SECRET"):
        setattr(settings, "KKIAPAY_TEST_" + suffix, "secret-ne-jamais-afficher-" + suffix)
    response = admin_client.get(reverse("admin:billing_kkiapayintent_changelist"))
    assert response.status_code == 200
    body = response.content.decode()
    assert "Indisponible" in body and "Aucun pays activé" in body
    assert "/api/v1/webhooks/kkiapay/test" in body
    assert "secret-ne-jamais-afficher" not in body


def test_paiement_kkiapay_explique_confirmation_automatique(admin_client, kki_config, politique_b):
    intention = KkiapayIntent.objects.get(pk=kki_config[0]["id"])
    response = admin_client.get(
        reverse("admin:billing_subscriptionpaymentrequest_change", args=[intention.demande_id])
    )
    assert response.status_code == 200
    body = response.content.decode()
    assert "En attente de confirmation du fournisseur" in body
    assert "Approuver le paiement" not in body
    assert "Vous pouvez consulter ce paiement, mais pas le valider" not in body


def test_fiches_b_affichent_les_dates_et_conditions(admin_client, salon_a):
    p = filleul_de(services.code_du_salon(salon_a.tenant))
    p.essai_debut, p.essai_fin = timezone.now(), timezone.now()
    p.save(update_fields=["essai_debut", "essai_fin"])
    r = remise_pour(salon_a.tenant)
    r.conditions = {"preuve": "conditions-figees-de-verification"}
    r.save(update_fields=["conditions"])
    pbody = admin_client.get(
        reverse("admin:parrainage_parrainage_change", args=[p.pk])
    ).content.decode()
    rbody = admin_client.get(
        reverse("admin:parrainage_remise_change", args=[r.pk])
    ).content.decode()
    assert "field-essai_debut" in pbody and "field-essai_fin" in pbody
    for champ in ("paiement_declencheur", "paiement_confirme_le", "disponible_le", "conditions"):
        assert f"field-{champ}" in rbody
    assert "conditions-figees-de-verification" in rbody


def test_historique_client_reste_accessible_apres_desactivation(salon_a, api_client):
    with as_tenant(salon_a.tenant):
        parrain, _, b, r = attribution(salon_a)
        confirmer(b)
        etat = clients.etat(parrain, salon_a.tenant.pk)
        assert etat["plafond"] == "500.00" and etat["validite_jours"] == 30
        PolitiqueSalon.objects.update(active=False)
    api_client.force_authenticate(parrain)
    response = api_client.get(
        "/api/v1/public/client/parrainage-salon", HTTP_HOST="blondrose.localhost"
    )
    assert response.status_code == 200
    assert response.data["actif"] is False and response.data["code"] == ""
    assert [v["id"] for v in response.data["recompenses"]] == [str(r.pk)]


def test_nouveaux_ecrans_a_et_journal_affichent_donnees_readonly(admin_client, salon_a):
    with as_tenant(salon_a.tenant):
        parrain, _, b, r = attribution(salon_a)
        confirmer(b)
    for modele in ("politiquesalon", "recompenseclient", "codeclientsalon", "evenementparrainage"):
        response = admin_client.get(reverse(f"admin:parrainage_{modele}_changelist"))
        assert response.status_code == 200
    response = admin_client.get(reverse("admin:parrainage_recompenseclient_change", args=[r.pk]))
    assert response.status_code == 200
    assert str(parrain) in response.content.decode()
    assert "field-parrain" in response.content.decode()
    assert "field-conditions" in response.content.decode()
    assert 'name="_save"' not in response.content.decode()


@pytest.mark.parametrize("kki_config", ["BJ", "BF", "CI", "TG", "SN", "NE"], indirect=True)
def test_six_pays_kkiapay_xof_et_controle_de_la_liste(salon_a, kki_config, settings):
    from apps.billing.services import PaiementRefuse

    intention, body = kki_config
    assert salon_a.tenant.country == body["country"] and body["currency"] == "XOF"
    moyen = PlatformPaymentMethod.objects.get(pk=body["method"])
    assert not moyen.problemes()
    with as_tenant(salon_a.tenant):
        assert kkiapay.preparer(salon_a.tenant.pk, salon_a.owner, body)["id"] == intention["id"]
        settings.KKIAPAY_ALLOWED_COUNTRIES = []
        with pytest.raises(PaiementRefuse):
            kkiapay.preparer(salon_a.tenant.pk, salon_a.owner, body)
