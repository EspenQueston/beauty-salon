"""Les groupes Standard et Pro : prix, montee, descente, droits.

Regles decidees avec le produit (voir services.effet_du_paiement) :

  - Pro : 399 CNY par mois, 4 000 CNY par an ;
  - Standard paye -> Pro : Pro commence a l'approbation, les jours Standard
    restants sont convertis en jours Pro au ratio des prix ;
  - Pro -> Standard : programme a la fin de la periode Pro ; les fonctions
    Pro se mettent en pause, sans rien effacer ;
  - un paiement declare n'ouvre rien tant qu'un administrateur ne l'a pas
    approuve, et l'approbation n'accorde qu'une fois.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.billing import services
from apps.billing.droits import fonctions_du_salon, groupe_effectif
from apps.billing.models import (
    Plan,
    PlanPrice,
    ProCapability,
    Subscription,
    SubscriptionEvent,
)
from apps.billing.services import PaiementRefuse, ajouter_mois
from conftest import as_tenant
from tests.test_abonnements import (
    ADMIN,
    _admin,
    abonnement_de,
    medias_temporaires,
    moyens,
    offres,
)

FIXTURES_PARTAGEES = (medias_temporaires, moyens, offres)


@pytest.fixture
def pro(offres):
    """Les offres Pro et leurs prix de test, et les cinq fonctions ouvertes."""
    plans = {}
    for code, nom, mois, cny, xaf in (
        ("pro_monthly", "Pro mensuel", 1, "399", "60000"),
        ("pro_yearly", "Pro annuel", 12, "4000", "600000"),
    ):
        plan, _ = Plan.objects.update_or_create(
            code=code,
            defaults={"name": nom, "billing_months": mois, "group": "pro", "active": True},
        )
        for devise, montant in (("CNY", cny), ("XAF", xaf)):
            PlanPrice.objects.update_or_create(
                plan=plan, currency=devise, defaults={"amount": Decimal(montant), "active": True}
            )
        plans[code] = plan
    for code, _ in ProCapability.Code.choices:
        ProCapability.objects.update_or_create(code=code, defaults={"active": True})
    return plans


def au_plan(salon, code, *, fin):
    """Un abonnement paye a l'offre `code`, qui finit a `fin`."""
    abonnement = abonnement_de(salon, statut=Subscription.Status.ACTIVE, fin=fin, essai=False)
    with as_tenant(salon.tenant):
        abonnement.plan = Plan.objects.get(code=code)
        abonnement.price_amount = PlanPrice.objects.get(plan=abonnement.plan, currency="XAF").amount
        abonnement.currency = "XAF"
        abonnement.save()
    return abonnement


def declarer_et_approuver(salon, moyen, code, reference="REF-PRO-1"):
    with as_tenant(salon.tenant):
        demande = services.soumettre_paiement(
            tenant_id=salon.tenant.id,
            utilisateur=salon.owner,
            code_offre=code,
            pays=moyen.country,
            devise=moyen.currency,
            moyen_id=moyen.id,
            reference=reference,
        )
    return services.approuver_paiement(demande.id, administrateur=_admin())


# ---------------------------------------------------------------------------
# Prix et catalogue
# ---------------------------------------------------------------------------


def test_l_annee_pro_fait_economiser_788_yuans():
    economie = services.economie_annuelle(Decimal("399"), Decimal("4000"))

    assert economie["montant"] == Decimal("788")
    assert economie["pourcentage"] == 16


@pytest.mark.django_db
def test_le_catalogue_presente_standard_et_pro(api_client, salon_a, moyens, pro):
    abonnement_de(salon_a)
    api_client.force_login(salon_a.owner)

    reponse = api_client.get("/api/v1/subscription/offres").json()

    devise = next(p for p in reponse["pays"] if p["code"] == "CN")["devises"][0]
    groupes = {plan["code"]: plan["groupe"] for plan in devise["plans"]}
    assert groupes == {
        "monthly": "standard",
        "yearly": "standard",
        "pro_monthly": "pro",
        "pro_yearly": "pro",
    }
    assert devise["economies"]["pro"]["montant"] == "788.00"
    assert {f["code"] for f in reponse["fonctions_pro"]} == set(ProCapability.Code.values)


@pytest.mark.django_db
def test_une_fonction_coupee_n_est_pas_promise(api_client, salon_a, moyens, pro):
    abonnement_de(salon_a)
    ProCapability.objects.filter(code="whatsapp_assistant").update(active=False)
    api_client.force_login(salon_a.owner)

    promises = {
        f["code"] for f in api_client.get("/api/v1/subscription/offres").json()["fonctions_pro"]
    }

    assert "whatsapp_assistant" not in promises


# ---------------------------------------------------------------------------
# Montee et descente
# ---------------------------------------------------------------------------


@ADMIN
def test_passer_a_pro_convertit_les_jours_standard_restants(salon_a, moyens, pro):
    au_plan(salon_a, "monthly", fin=timezone.now() + timedelta(days=20))

    demande = declarer_et_approuver(salon_a, moyens["momo"], "pro_monthly")

    with as_tenant(salon_a.tenant):
        abonnement = Subscription.objects.get()
        assert abonnement.plan.code == "pro_monthly"
        assert abonnement.status == Subscription.Status.ACTIVE
        # 20 jours a 15 000 XAF/mois valent ~5 jours a 60 000 XAF/mois.
        debut = demande.period_start
        assert abs((debut - timezone.now()).total_seconds()) < 60
        credit = (abonnement.period_anchor - debut).total_seconds() / 86400
        assert 4.9 < credit < 5.1
        assert abonnement.current_period_end == ajouter_mois(
            abonnement.period_anchor, 1, salon_a.tenant.timezone
        )
        assert SubscriptionEvent.objects.filter(kind="upgraded").count() == 1
        assert groupe_effectif(abonnement) == "pro"


@ADMIN
def test_payer_pro_pendant_l_essai_ouvre_pro_tout_de_suite_et_garde_l_essai(
    salon_a, moyens, pro
):
    """Decide avec le produit : Pro demarre a l'approbation, et les jours
    d'essai restants s'ajoutent en entier a la periode Pro."""
    fin_essai = timezone.now() + timedelta(days=6)
    abonnement_de(salon_a, fin=fin_essai)

    demande = declarer_et_approuver(salon_a, moyens["momo"], "pro_monthly")

    with as_tenant(salon_a.tenant):
        abonnement = Subscription.objects.select_related("plan", "tenant").get()
        assert fonctions_du_salon(salon_a.tenant.id)["platform_assistant"] is True
        journal = SubscriptionEvent.objects.filter(kind="upgraded", note__contains="essai")
        assert journal.exists()
    assert abs((demande.period_start - timezone.now()).total_seconds()) < 60  # tout de suite
    assert abonnement.status == Subscription.Status.ACTIVE
    assert groupe_effectif(abonnement) == "pro"
    # Six jours d'essai + un mois : la fin tombe un mois apres la fin d'essai.
    assert abonnement.period_anchor == fin_essai
    assert abonnement.current_period_end == ajouter_mois(fin_essai, 1, salon_a.tenant.timezone)


@ADMIN
def test_payer_standard_pendant_l_essai_commence_a_la_fin_de_l_essai(salon_a, moyens, pro):
    fin_essai = timezone.now() + timedelta(days=6)
    abonnement_de(salon_a, fin=fin_essai)

    demande = declarer_et_approuver(salon_a, moyens["momo"], "monthly")

    assert demande.period_start == fin_essai
    with as_tenant(salon_a.tenant):
        abonnement = Subscription.objects.get()
    assert abonnement.current_period_end == ajouter_mois(fin_essai, 1, salon_a.tenant.timezone)


@ADMIN
def test_revenir_a_standard_est_programme_a_la_fin_de_pro(salon_a, moyens, pro):
    fin_pro = timezone.now() + timedelta(days=10)
    au_plan(salon_a, "pro_monthly", fin=fin_pro)

    demande = declarer_et_approuver(salon_a, moyens["momo"], "monthly")

    with as_tenant(salon_a.tenant):
        abonnement = Subscription.objects.select_related("plan", "scheduled_plan").get()
        # Pro court jusqu'a son terme ; Standard est programme derriere.
        assert abonnement.plan.code == "pro_monthly"
        assert abonnement.current_period_end == fin_pro
        assert abonnement.scheduled_plan.code == "monthly"
        assert abonnement.scheduled_period_end == ajouter_mois(fin_pro, 1, salon_a.tenant.timezone)
        assert demande.period_start == fin_pro
        assert groupe_effectif(abonnement) == "pro"
        # Apres la fin de Pro : Standard, et l'acces reste ouvert.
        plus_tard = fin_pro + timedelta(days=1)
        assert groupe_effectif(abonnement, plus_tard) == "standard"
        assert services.acces_de(abonnement, plus_tard).ouvert

        # La tache quotidienne fait la bascule.
        services.run_billing_cycle(now=plus_tard)
        abonnement.refresh_from_db()
        assert abonnement.plan.code == "monthly"
        assert abonnement.scheduled_plan is None
        assert SubscriptionEvent.objects.filter(kind="plan_changed").count() == 1


@ADMIN
def test_pro_ne_se_reprend_pas_par_dessus_une_descente_programmee(salon_a, moyens, pro):
    au_plan(salon_a, "pro_monthly", fin=timezone.now() + timedelta(days=10))
    declarer_et_approuver(salon_a, moyens["momo"], "monthly")

    with pytest.raises(PaiementRefuse) as refus, as_tenant(salon_a.tenant):
        services.soumettre_paiement(
            tenant_id=salon_a.tenant.id,
            utilisateur=salon_a.owner,
            code_offre="pro_monthly",
            pays="CG",
            devise="XAF",
            moyen_id=moyens["momo"].id,
            reference="REF-PRO-2",
        )

    assert refus.value.code == "changement_programme"


@ADMIN
def test_un_paiement_pro_declare_n_ouvre_rien_et_ne_s_approuve_qu_une_fois(salon_a, moyens, pro):
    au_plan(salon_a, "monthly", fin=timezone.now() + timedelta(days=20))
    with as_tenant(salon_a.tenant):
        demande = services.soumettre_paiement(
            tenant_id=salon_a.tenant.id,
            utilisateur=salon_a.owner,
            code_offre="pro_monthly",
            pays="CG",
            devise="XAF",
            moyen_id=moyens["momo"].id,
            reference="REF-PRO-9",
        )
        assert not fonctions_du_salon(salon_a.tenant.id)["custom_domain"]

    admin = _admin()
    services.approuver_paiement(demande.id, administrateur=admin)
    with pytest.raises(PaiementRefuse):
        services.approuver_paiement(demande.id, administrateur=admin)

    with as_tenant(salon_a.tenant):
        assert fonctions_du_salon(salon_a.tenant.id)["custom_domain"]
        assert SubscriptionEvent.objects.filter(kind="upgraded").count() == 1


@ADMIN
def test_un_prix_change_n_altere_pas_une_demande_pro(salon_a, moyens, pro):
    au_plan(salon_a, "monthly", fin=timezone.now() + timedelta(days=20))
    with as_tenant(salon_a.tenant):
        demande = services.soumettre_paiement(
            tenant_id=salon_a.tenant.id,
            utilisateur=salon_a.owner,
            code_offre="pro_monthly",
            pays="CG",
            devise="XAF",
            moyen_id=moyens["momo"].id,
            reference="REF-PRO-5",
        )
    PlanPrice.objects.filter(plan=pro["pro_monthly"], currency="XAF").update(
        amount=Decimal("99999")
    )

    with as_tenant(salon_a.tenant):
        demande.refresh_from_db()
        assert demande.amount == Decimal("60000")
        assert demande.plan.code == "pro_monthly"


# ---------------------------------------------------------------------------
# Droits
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_l_essai_et_standard_n_ont_aucune_fonction_pro(salon_a, pro):
    abonnement_de(salon_a)
    with as_tenant(salon_a.tenant):
        assert not any(fonctions_du_salon(salon_a.tenant.id).values())

    au_plan(salon_a, "yearly", fin=timezone.now() + timedelta(days=200))
    with as_tenant(salon_a.tenant):
        assert not any(fonctions_du_salon(salon_a.tenant.id).values())


@pytest.mark.django_db
def test_pro_ouvre_toutes_ses_fonctions_sauf_celles_coupees(salon_a, pro):
    au_plan(salon_a, "pro_yearly", fin=timezone.now() + timedelta(days=200))
    with as_tenant(salon_a.tenant):
        assert all(fonctions_du_salon(salon_a.tenant.id).values())

    ProCapability.objects.filter(code="custom_domain").update(active=False)
    with as_tenant(salon_a.tenant):
        fonctions = fonctions_du_salon(salon_a.tenant.id)
    assert fonctions["custom_domain"] is False
    assert fonctions["customization"] is True


@pytest.mark.django_db
def test_pro_expire_ou_suspendu_met_les_fonctions_en_pause(salon_a, pro):
    au_plan(salon_a, "pro_monthly", fin=timezone.now() - timedelta(days=5))
    with as_tenant(salon_a.tenant):
        assert not any(fonctions_du_salon(salon_a.tenant.id).values())

    abonnement = au_plan(salon_a, "pro_monthly", fin=timezone.now() + timedelta(days=5))
    with as_tenant(salon_a.tenant):
        abonnement.status = Subscription.Status.SUSPENDED
        abonnement.save(update_fields=["status"])
        assert not any(fonctions_du_salon(salon_a.tenant.id).values())


@pytest.mark.django_db
def test_l_acces_expose_le_groupe_et_les_fonctions(api_client, salon_a, pro):
    au_plan(salon_a, "pro_monthly", fin=timezone.now() + timedelta(days=5))
    api_client.force_login(salon_a.owner)

    acces = api_client.get("/api/v1/subscription/acces").json()

    assert acces["groupe"] == "pro"
    assert acces["fonctions"]["platform_assistant"] is True
    # Déjà en Pro : la barre du haut ne propose plus de passer à Pro.
    assert acces["pro_disponible"] is False


@pytest.mark.django_db
def test_passer_a_pro_n_est_propose_que_si_pro_se_vend_dans_la_devise(api_client, salon_a, pro):
    au_plan(salon_a, "monthly", fin=timezone.now() + timedelta(days=5))
    api_client.force_login(salon_a.owner)
    assert api_client.get("/api/v1/subscription/acces").json()["pro_disponible"] is True

    PlanPrice.objects.filter(plan__group="pro").update(active=False)
    assert api_client.get("/api/v1/subscription/acces").json()["pro_disponible"] is False


# ---------------------------------------------------------------------------
# Administration
# ---------------------------------------------------------------------------


@ADMIN
def test_l_administration_coupe_une_fonction_pro_et_le_trace(client, pro):
    from apps.audit.models import AuditLog

    client.force_login(_admin())
    capacite = ProCapability.objects.get(code="whatsapp_assistant")

    assert client.get(reverse("admin:billing_procapability_changelist")).status_code == 200
    client.post(
        reverse("admin:billing_procapability_change", args=[capacite.pk]),
        {"active": "", "description": "Coupée le temps de régler le fournisseur.", "position": "2"},
    )

    capacite.refresh_from_db()
    assert capacite.active is False
    assert AuditLog.objects.filter(
        action=AuditLog.Action.BILLING_SETTINGS_CHANGED, resource_id=str(capacite.pk)
    ).exists()


@ADMIN
def test_les_ecrans_d_offres_et_d_abonnements_s_ouvrent_avec_pro(client, salon_a, moyens, pro):
    au_plan(salon_a, "pro_monthly", fin=timezone.now() + timedelta(days=10))
    declarer_et_approuver(salon_a, moyens["momo"], "monthly")
    client.force_login(_admin())

    for nom in (
        "admin:billing_plan_changelist",
        "admin:billing_subscription_changelist",
        "admin:billing_subscriptionpaymentrequest_changelist",
        "admin:domains_domainclaim_changelist",
        "admin:assistants_assistantreglages_changelist",
    ):
        assert client.get(reverse(nom)).status_code == 200, nom
    with as_tenant(salon_a.tenant):
        abonnement = Subscription.objects.get()
    fiche = client.get(reverse("admin:billing_subscription_change", args=[abonnement.pk]))
    assert fiche.status_code == 200
    assert "Pro" in fiche.content.decode()
