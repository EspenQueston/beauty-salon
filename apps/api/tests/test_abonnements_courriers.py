"""E-mails d'abonnement : rappels, decisions, tarifs, et la proposition d'annuel.

Ce que ces tests tiennent :

  - un rappel part une fois, au bon seuil, aux proprietaires seulement, et
    jamais la nuit ni a qui a deja declare un paiement ;
  - chaque decision (paiement recu, valide, refuse ; prolongation,
    suspension) est ecrite au salon, et l'equipe apprend qu'un paiement
    attend ;
  - un tarif modifie est annonce aux salons de cette devise, et a eux seuls ;
  - un salon au mensuel se voit proposer l'annuel, chiffre a l'appui.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from django.core import mail
from django.urls import reverse

from apps.accounts.models import Membership
from apps.billing import services
from apps.billing.models import Plan, PlanPrice, Subscription, SubscriptionReminder
from apps.billing.rappels import envoyer_rappels, genre_du_rappel
from conftest import as_tenant
from tests.factories import MembershipFactory, UserFactory
from tests.test_abonnements import (
    ADMIN,
    _admin,
    _demande,
    abonnement_de,
    medias_temporaires,
    moyens,
    offres,
)

# Les fixtures de tarifs et de moyens viennent du module voisin : les nommer
# ici les rend visibles a pytest dans ce fichier.
FIXTURES_PARTAGEES = (medias_temporaires, moyens, offres)

# 11 h UTC : midi a Brazzaville, dans les heures ouvrees du salon.
MIDI = datetime(2027, 3, 10, 11, 0, tzinfo=UTC)


def au_mensuel(salon, *, fin, plan_code="monthly"):
    """Un abonnement paye, au mensuel ou a l'annuel, qui finit a `fin`."""
    abonnement = abonnement_de(salon, statut=Subscription.Status.ACTIVE, fin=fin, essai=False)
    with as_tenant(salon.tenant):
        abonnement.plan = Plan.objects.get(code=plan_code)
        abonnement.save(update_fields=["plan"])
    return abonnement


def sujets(adresse=None):
    return [m.subject for m in mail.outbox if adresse is None or adresse in m.to]


# ---------------------------------------------------------------------------
# Rappels
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_le_rappel_de_fin_d_essai_part_une_seule_fois(salon_a, offres):
    abonnement_de(salon_a, fin=MIDI + timedelta(days=6, hours=20))

    envoyer_rappels(MIDI)
    envoyer_rappels(MIDI + timedelta(hours=1))

    assert sujets() == ["Votre essai Beauty Salon se termine dans 7 jours"]
    assert mail.outbox[0].to == [salon_a.owner.email]
    with as_tenant(salon_a.tenant):
        assert SubscriptionReminder.objects.get().kind == "trial_7"


@pytest.mark.django_db
def test_seuls_les_proprietaires_recoivent_les_rappels(salon_a, offres):
    gerante = UserFactory()
    MembershipFactory(tenant=salon_a.tenant, user=gerante, role=Membership.Role.MANAGER)
    abonnement_de(salon_a, fin=MIDI + timedelta(days=2))

    envoyer_rappels(MIDI)

    assert sujets(gerante.email) == []
    assert len(sujets(salon_a.owner.email)) == 1


@pytest.mark.django_db
def test_on_envoie_le_seuil_le_plus_proche_sans_rattraper_les_autres(salon_a, offres):
    abonnement_de(salon_a, fin=MIDI + timedelta(days=2))

    envoyer_rappels(MIDI)  # J-2 : le J-3, pas le J-7
    envoyer_rappels(MIDI + timedelta(days=1, hours=6))  # la veille, 18 h

    with as_tenant(salon_a.tenant):
        genres = sorted(SubscriptionReminder.objects.values_list("kind", flat=True))
    assert genres == ["trial_1", "trial_3"]
    assert sujets()[-1] == "Votre essai Beauty Salon se termine demain"


@pytest.mark.django_db
def test_rien_ne_part_la_nuit(salon_a, offres):
    abonnement_de(salon_a, fin=MIDI + timedelta(days=2))

    envoyer_rappels(MIDI.replace(hour=22))  # 23 h a Brazzaville

    assert mail.outbox == []


@pytest.mark.django_db
def test_un_paiement_en_attente_fait_taire_les_rappels(salon_a, moyens):
    abonnement = abonnement_de(salon_a, fin=MIDI + timedelta(days=2))
    _demande(salon_a, moyens["momo"])

    with as_tenant(salon_a.tenant):
        assert genre_du_rappel(abonnement, MIDI) is None


@pytest.mark.django_db
def test_grace_puis_fermeture_puis_silence(salon_a, offres):
    abonnement = abonnement_de(salon_a, fin=MIDI - timedelta(days=1))
    assert genre_du_rappel(abonnement, MIDI) == "grace"
    assert genre_du_rappel(abonnement, MIDI + timedelta(days=3)) == "closed"
    # Fermé depuis plus d'une semaine : déjà prévenu, on ne relance pas.
    assert genre_du_rappel(abonnement, MIDI + timedelta(days=12)) is None


@pytest.mark.django_db
def test_une_suspension_fait_taire_les_rappels(salon_a, offres):
    abonnement = abonnement_de(
        salon_a, statut=Subscription.Status.SUSPENDED, fin=MIDI + timedelta(days=2)
    )

    assert genre_du_rappel(abonnement, MIDI) is None


@pytest.mark.django_db
def test_l_annuel_est_prevenu_un_mois_avant(salon_a, offres):
    annuel = au_mensuel(salon_a, fin=MIDI + timedelta(days=25), plan_code="yearly")
    assert genre_du_rappel(annuel, MIDI) == "renewal_30"

    mensuel = au_mensuel(salon_a, fin=MIDI + timedelta(days=25))
    assert genre_du_rappel(mensuel, MIDI) is None


@pytest.mark.django_db
def test_le_rappel_d_un_mensuel_propose_l_annuel(salon_a, offres):
    au_mensuel(salon_a, fin=MIDI + timedelta(days=5))

    envoyer_rappels(MIDI)

    message = mail.outbox[0]
    assert message.subject == "Votre abonnement arrive à échéance dans 5 jours"
    assert "Passez à l'offre annuelle" in message.body
    assert "150 000 XAF / an" in message.body
    html = message.alternatives[0][0]
    assert "Passer à l&#x27;annuel" in html or "Passer à l'annuel" in html


# ---------------------------------------------------------------------------
# Decisions
# ---------------------------------------------------------------------------


@ADMIN
def test_declarer_ecrit_au_salon_et_a_l_equipe(salon_a, moyens):
    admin = _admin()
    abonnement_de(salon_a)

    _demande(salon_a, moyens["momo"])

    assert sujets(salon_a.owner.email) == ["Paiement reçu — en cours de vérification"]
    assert sujets(admin.email) == ["Paiement d'abonnement à vérifier — Blond Rose"]
    assert "/billing/subscriptionpaymentrequest/" in mail.outbox[-1].body


@ADMIN
def test_valider_et_refuser_sont_ecrits_au_salon(salon_a, moyens):
    admin = _admin()
    abonnement_de(salon_a, fin=datetime.now(UTC) - timedelta(days=1))
    premiere = _demande(salon_a, moyens["momo"], reference="REF-0001")
    services.approuver_paiement(premiere.id, administrateur=admin)
    seconde = _demande(salon_a, moyens["momo"], reference="REF-0002")
    services.refuser_paiement(seconde.id, administrateur=admin, motif="Référence inconnue")

    recus = sujets(salon_a.owner.email)
    assert any(s.startswith("Paiement validé — abonnement actif jusqu'au") for s in recus)
    assert "Votre paiement n'a pas pu être validé" in recus
    refus = next(m for m in mail.outbox if "pas pu être validé" in m.subject)
    assert "Référence inconnue" in refus.body


@ADMIN
def test_les_gestes_de_l_administration_sont_ecrits_au_salon(salon_a, offres):
    admin = _admin()
    abonnement_de(salon_a)

    services.prolonger_manuellement(salon_a.tenant.id, administrateur=admin, mois=1, note="Geste")
    services.suspendre(salon_a.tenant.id, administrateur=admin, motif="Litige")
    services.reactiver(salon_a.tenant.id, administrateur=admin)

    recus = sujets(salon_a.owner.email)
    assert recus[0].startswith("Votre abonnement est prolongé jusqu'au")
    assert recus[1:] == [
        "Votre abonnement Beauty Salon est suspendu",
        "Votre abonnement Beauty Salon est réactivé",
    ]


# ---------------------------------------------------------------------------
# Tarifs
# ---------------------------------------------------------------------------


@ADMIN
def test_un_tarif_modifie_est_annonce_aux_salons_de_cette_devise(client, salon_a, salon_b, offres):
    abonnement_de(salon_a)  # XAF
    abonnement_de(salon_b)
    with as_tenant(salon_b.tenant):
        Subscription.objects.filter(tenant=salon_b.tenant).update(currency="CNY")
    prix = PlanPrice.objects.get(plan=offres["mensuel"], currency="XAF")
    client.force_login(_admin())

    reponse = client.post(
        reverse("admin:billing_planprice_change", args=[prix.pk]),
        {"plan": str(prix.plan_id), "currency": "XAF", "amount": "17500", "active": "on"},
    )

    assert reponse.status_code == 302
    assert sujets(salon_a.owner.email) == ["Évolution du tarif Mensuel (XAF)"]
    assert sujets(salon_b.owner.email) == []
    annonce = mail.outbox[0]
    assert "15 000 XAF" in annonce.body and "17 500 XAF" in annonce.body


@ADMIN
def test_un_tarif_inchange_n_est_pas_annonce(client, salon_a, offres):
    abonnement_de(salon_a)
    prix = PlanPrice.objects.get(plan=offres["mensuel"], currency="XAF")
    client.force_login(_admin())

    client.post(
        reverse("admin:billing_planprice_change", args=[prix.pk]),
        {"plan": str(prix.plan_id), "currency": "XAF", "amount": "15000", "active": ""},
    )

    assert mail.outbox == []


# ---------------------------------------------------------------------------
# Proposition de l'annuel
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_un_salon_au_mensuel_se_voit_proposer_l_annuel(api_client, salon_a, offres):
    au_mensuel(salon_a, fin=datetime.now(UTC) + timedelta(days=20))
    api_client.force_login(salon_a.owner)

    acces = api_client.get("/api/v1/subscription/acces").json()
    abonnement = api_client.get("/api/v1/subscription").json()

    assert acces["offre_code"] == "monthly"
    proposition = acces["montee_en_gamme"]
    assert proposition["vers"] == "yearly"
    assert proposition["devise"] == "XAF"
    assert Decimal(proposition["economie"]["montant"]) == Decimal("30000")
    assert abonnement["montee_en_gamme"] == proposition


@pytest.mark.django_db
def test_rien_a_proposer_a_l_annuel_ni_a_l_essai(api_client, salon_a, offres):
    au_mensuel(salon_a, fin=datetime.now(UTC) + timedelta(days=200), plan_code="yearly")
    api_client.force_login(salon_a.owner)
    assert api_client.get("/api/v1/subscription/acces").json()["montee_en_gamme"] is None

    abonnement_de(salon_a)
    assert api_client.get("/api/v1/subscription/acces").json()["montee_en_gamme"] is None
