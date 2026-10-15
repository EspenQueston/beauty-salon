"""La facture d'abonnement en PDF.

Ce que ces tests tiennent :

  - la proprietaire telecharge un vrai PDF, nomme d'apres la facture, dans
    la langue de la page ;
  - le document porte le numero, le montant et le statut (texte lisible) ;
  - un autre salon ne voit pas la facture (404) ; une prestataire ne peut
    pas la telecharger.
"""

import re
import zlib
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.models import Membership
from apps.billing.facture_pdf import generer, largeur
from apps.billing.models import Invoice
from conftest import as_tenant
from tests.factories import MembershipFactory, UserFactory
from tests.test_abonnements import abonnement_de, offres

FIXTURES = (offres,)
PASSWORD = "motdepasse-solide"


@pytest.fixture
def facture(salon_a, offres):
    abonnement = abonnement_de(salon_a)
    maintenant = timezone.now()
    with as_tenant(salon_a.tenant):
        return Invoice.objects.create(
            tenant=salon_a.tenant,
            subscription=abonnement,
            number="BS-TEST-0042",
            period_start=maintenant,
            period_end=maintenant + timedelta(days=30),
            amount=15000,
            currency="XAF",
            label="Abonnement mensuel",
            status=Invoice.Status.PAID,
            due_at=maintenant,
            paid_at=maintenant,
            payment_method=Invoice.Method.MOBILE_MONEY,
            payment_reference="MP260915.1042",
        )


def texte_du_pdf(contenu: bytes) -> str:
    """Le texte des flux de la page, decompresses."""
    morceaux = []
    for flux in re.findall(rb"stream\n(.*?)\nendstream", contenu, re.S):
        try:
            morceaux.append(zlib.decompress(flux).decode("cp1252", "replace"))
        except zlib.error:
            continue
    return "\n".join(morceaux)


@pytest.mark.django_db
def test_la_proprietaire_telecharge_sa_facture(api_client, salon_a, facture):
    assert api_client.login(email=salon_a.owner.email, password=PASSWORD)

    reponse = api_client.get(
        f"/api/v1/invoices/{facture.pk}/pdf/", HTTP_X_TENANT_ID=str(salon_a.tenant.pk)
    )

    assert reponse.status_code == 200, reponse.content[:200]
    assert reponse["Content-Type"] == "application/pdf"
    assert 'filename="facture-BS-TEST-0042.pdf"' in reponse["Content-Disposition"]
    assert reponse.content.startswith(b"%PDF-1.4") and reponse.content.rstrip().endswith(b"%%EOF")
    texte = texte_du_pdf(reponse.content)
    assert "BS-TEST-0042" in texte
    assert "FACTURE" in texte and "PAYÉE" in texte
    assert "15\xa0000 XAF" in texte


@pytest.mark.django_db
def test_une_page_anglaise_recoit_une_facture_anglaise(api_client, salon_a, facture):
    assert api_client.login(email=salon_a.owner.email, password=PASSWORD)

    reponse = api_client.get(
        f"/api/v1/invoices/{facture.pk}/pdf/",
        HTTP_X_TENANT_ID=str(salon_a.tenant.pk),
        HTTP_ACCEPT_LANGUAGE="en",
    )

    assert 'filename="invoice-BS-TEST-0042.pdf"' in reponse["Content-Disposition"]
    texte = texte_du_pdf(reponse.content)
    assert "INVOICE" in texte and "PAID" in texte and "15,000 XAF" in texte


@pytest.mark.django_db
def test_un_autre_salon_ne_voit_pas_la_facture(api_client, salon_b, facture):
    assert api_client.login(email=salon_b.owner.email, password=PASSWORD)

    reponse = api_client.get(
        f"/api/v1/invoices/{facture.pk}/pdf/", HTTP_X_TENANT_ID=str(salon_b.tenant.pk)
    )

    assert reponse.status_code == 404


@pytest.mark.django_db
def test_une_prestataire_ne_telecharge_pas_les_factures(api_client, salon_a, facture):
    prestataire = UserFactory()
    MembershipFactory(tenant=salon_a.tenant, user=prestataire, role=Membership.Role.STAFF)
    assert api_client.login(email=prestataire.email, password=PASSWORD)

    reponse = api_client.get(
        f"/api/v1/invoices/{facture.pk}/pdf/", HTTP_X_TENANT_ID=str(salon_a.tenant.pk)
    )

    assert reponse.status_code == 403


@pytest.mark.django_db
def test_une_facture_a_regler_porte_son_statut(salon_a, facture):
    with as_tenant(salon_a.tenant):
        facture.status = Invoice.Status.ISSUED
        facture.paid_at = None
        assert "À RÉGLER" in texte_du_pdf(generer(facture, "fr"))


def test_les_largeurs_alignent_les_montants():
    # Une valeur de reference des metriques Helvetica : « 0 » = 556/1000 em.
    assert largeur("0", "F1", 10) == pytest.approx(5.56)
    assert largeur("é", "F1", 10) == largeur("e", "F1", 10)
    assert largeur("W", "F2", 10) > largeur("i", "F2", 10)
