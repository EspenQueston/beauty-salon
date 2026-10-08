"""Règles A/B validées et contrôles du paiement intégré, fournisseurs simulés."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.billing import kkiapay
from apps.billing import services as billing
from apps.billing.encaissements import constater
from apps.billing.models import (
    Invoice,
    KkiapayIntent,
    Plan,
    PlanPrice,
    PlatformPaymentMethod,
    SubscriptionPaymentRequest,
)
from apps.clients.models import ClientProfile
from apps.parrainage import clients, cycles, services
from apps.parrainage.models import (
    EvenementParrainage,
    PolitiquePlateforme,
    PolitiqueSalon,
    RecompenseClient,
    Remise,
)
from apps.scheduling.models import Booking
from apps.scheduling.services.booking import BookingRefused
from conftest import as_tenant
from tests.factories import BookingFactory, CustomerFactory, UserFactory
from tests.test_abonnements import ADMIN, _admin, abonnement_de, medias_temporaires, moyens, offres
from tests.test_parrainage import declarer, remise_pour

FIXTURES = (medias_temporaires, moyens, offres)
pytestmark = ADMIN


@pytest.fixture(autouse=True)
def politique_b():
    return PolitiquePlateforme.objects.update_or_create(
        pk=1,
        defaults={
            "active": True,
            "cooling_mode": "demi_periode",
            "validite_jours": 90,
            "validite_depuis_disponibilite": True,
            "recompenses_max_par_parrain": 100,
            "remises_max_par_echeance": 1,
            "reservation_heures": 24,
            "apres_remboursement": "maintenir",
        },
    )[0]


def cliente():
    user = UserFactory()
    ClientProfile.objects.create(user=user)
    return user


def politique_a(salon):
    return PolitiqueSalon.objects.create(
        tenant=salon.tenant,
        active=True,
        taux=10,
        validite_jours=30,
        plafond_montant=500,
        devise="XAF",
        nature_plafond="montant_par_reservation",
        reservations_annulees_excluent=True,
        attribution="premier_code",
        formule="apres_promotions_prestation",
        recompenses_par_reservation=1,
        annulation_declencheur="maintenir",
        annulation_utilisation="restituer",
    )


def rdv(salon, user=None, *, index=0, email=None, status="requested"):
    debut = timezone.now() + timedelta(days=2 + index)
    return BookingFactory(
        tenant=salon.tenant,
        service=salon.service,
        staff_member=salon.staff,
        customer=CustomerFactory(tenant=salon.tenant),
        starts_at=debut,
        ends_at=debut + timedelta(hours=2),
        compte=user,
        contact_email=email or (user.email if user else "guest@example.com"),
        total_amount=Decimal(15000),
        prix_initial=Decimal(15000),
        currency="XAF",
        status=status,
    )


def attribution(salon, parrain=None, filleul=None):
    parrain, filleul = parrain or cliente(), filleul or cliente()
    politique_a(salon)
    code = clients.code_client(parrain, salon.tenant.pk)
    b = rdv(salon, filleul)
    clients.capturer(b, code.code)
    return parrain, filleul, b, RecompenseClient.objects.get(declencheur=b)


def confirmer(b):
    b.status = Booking.Status.CONFIRMED
    b.save(update_fields=["status"])


def premier_paiement(salon_a, salon_b, moyens, code="monthly"):
    abonnement_de(salon_b)
    services.detecter(salon_b.tenant, salon_b.owner, services.code_du_salon(salon_a.tenant).code)
    demande = declarer(salon_b, moyens["momo"], code=code)
    billing.approuver_paiement(demande.pk, administrateur=_admin())
    with as_tenant(salon_b.tenant):
        demande.refresh_from_db()
    return demande, Remise.objects.get(paiement_declencheur_id=demande.pk)


def test_a_compte_existant_nouveau_dans_salon_et_declenchement_unique(salon_a, salon_b):
    filleul = cliente()
    with as_tenant(salon_b.tenant):
        rdv(salon_b, filleul)
    with as_tenant(salon_a.tenant):
        parrain, _, b, r = attribution(salon_a, filleul=filleul)
        assert r.statut == "en_attente" and r.expire_le is None
        confirmer(b)
        r.refresh_from_db()
        assert r.statut == "disponible"
        assert r.parrain == parrain and r.filleul == filleul
        b.save(update_fields=["status"])
        assert RecompenseClient.objects.count() == 1
        assert (
            EvenementParrainage.objects.filter(ressource=r.pk, action="disponibilite").count() == 1
        )
        b.status = "cancelled"
        b.save(update_fields=["status"])
        r.refresh_from_db()
        assert r.statut == "disponible"


@pytest.mark.parametrize("ancien_statut", ["requested", "confirmed", "cancelled", "completed"])
def test_a_ancienne_reservation_meme_annulee_exclut(salon_a, ancien_statut):
    with as_tenant(salon_a.tenant):
        p, f = cliente(), cliente()
        politique_a(salon_a)
        code = clients.code_client(p, salon_a.tenant.pk)
        rdv(salon_a, f, status=ancien_statut)
        b = rdv(salon_a, f, index=1)
        with pytest.raises(BookingRefused):
            clients.capturer(b, code.code)


def test_a_auto_parrainage_et_autre_salon_refuses(salon_a, salon_b):
    p = cliente()
    with as_tenant(salon_a.tenant):
        politique_a(salon_a)
        code = clients.code_client(p, salon_a.tenant.pk)
        with pytest.raises(BookingRefused):
            clients.capturer(rdv(salon_a, p), code.code)
    with as_tenant(salon_b.tenant):
        politique_a(salon_b)
        with pytest.raises(BookingRefused):
            clients.capturer(rdv(salon_b, cliente()), code.code)


def test_a_remise_integrale_ne_demande_pas_un_acompte_nul(salon_a, settings):
    with as_tenant(salon_a.tenant):
        p, _, b, r = attribution(salon_a)
        confirmer(b)
        r.taux, r.plafond_montant = 100, 30000
        r.save(update_fields=["taux", "plafond_montant"])
        salon_a.service.requires_deposit = True
        salon_a.service.save(update_fields=["requires_deposit"])
        salon_a.profile.deposit_rate = 50
        salon_a.profile.save(update_fields=["deposit_rate"])
        usage = rdv(salon_a, p, index=1, status="pending_payment")
        clients.reserver(usage, p)
        assert usage.total_amount == 0 and usage.deposit_amount == 0
        assert usage.status == "requested"
        settings.PARRAINAGE_ACTIF = False
        assert clients.politique() is None


def test_a_promotion_et_parrainage_sans_double_deduction(salon_a):
    with as_tenant(salon_a.tenant):
        p, _, b, r = attribution(salon_a)
        confirmer(b)
        usage = rdv(salon_a, p, index=1)
        usage.promotion_montant, usage.total_amount = Decimal(2000), Decimal(13000)
        usage.save(update_fields=["promotion_montant", "total_amount"])
        clients.reserver(usage, p)
        assert usage.prix_initial == 15000
        assert usage.promotion_montant == 2000 and usage.reduction_parrainage == 500
        assert usage.total_amount == 12500


def test_a_minimum_configuration_complete_et_snapshot(salon_a):
    with as_tenant(salon_a.tenant):
        p, f, b, r = attribution(salon_a)
        politique = PolitiqueSalon.objects.get()
        politique.taux = 9
        with pytest.raises(ValidationError):
            politique.full_clean()
        politique.taux, politique.plafond_montant, politique.validite_jours = 50, 3000, 80
        politique.save()
        confirmer(b)
        r.refresh_from_db()
        assert r.taux == 10 and r.plafond_montant == 500
        assert abs((r.expire_le - timezone.now()).total_seconds() - 30 * 86400) < 5
        politique.validite_jours = None
        with pytest.raises(ValidationError):
            politique.full_clean()


def test_a_formule_promotions_plafond_arrondi_et_zero():
    assert clients.prix(Decimal(10000), Decimal(2000), Decimal(10), Decimal(700), "XAF") == (
        Decimal(700),
        Decimal(7300),
    )
    assert clients.prix(Decimal("19.95"), Decimal(0), Decimal(10), Decimal(100), "CNY")[
        0
    ] == Decimal("2.00")
    assert clients.prix(Decimal(100), Decimal(150), Decimal(20), Decimal(80), "XOF") == (0, 0)


def test_a_consommation_unique_restitution_et_expiration(salon_a, salon_b):
    with as_tenant(salon_a.tenant):
        p, _, b, r = attribution(salon_a)
        confirmer(b)
        usage = rdv(salon_a, p, index=1)
        clients.reserver(usage, p)
        assert usage.total_amount == 14500
        deux = rdv(salon_a, p, index=2)
        clients.reserver(deux, p)
        assert deux.total_amount == 15000
        confirmer(usage)
        r.refresh_from_db()
        assert r.statut == "utilisee"
        usage.status = "cancelled"
        usage.save(update_fields=["status"])
        r.refresh_from_db()
        assert r.statut == "disponible" and not r.utilisation_id
        r.expire_le = timezone.now() - timedelta(seconds=1)
        r.save(update_fields=["expire_le"])
        clients.reserver(deux, p)
        r.refresh_from_db()
        assert r.statut == "expiree"
    with as_tenant(salon_b.tenant):
        other = rdv(salon_b, p)
        clients.reserver(other, p)
        assert other.total_amount == 15000 and not RecompenseClient.objects.exists()


def test_a_api_configuration_et_historique_isoles(api_client, salon_a, salon_b):
    with as_tenant(salon_b.tenant):
        attribution(salon_b)
    api_client.force_login(salon_a.owner)
    assert api_client.get("/api/v1/parrainage/clients").json()["historique"] == []
    assert (
        api_client.patch(
            "/api/v1/parrainage/clients", {"active": True, "taux": 9}, format="json"
        ).status_code
        == 400
    )
    p = cliente()
    api_client.force_login(p)
    assert api_client.patch("/api/v1/parrainage/clients", {}, format="json").status_code == 403


def test_a_une_note_modifiee_ne_confirme_pas_une_reservation(salon_a):
    with as_tenant(salon_a.tenant):
        _, _, b, r = attribution(salon_a)
        b.status = "confirmed"  # Objet en mémoire obsolète, seul le champ note est écrit.
        b.internal_note = "Note de suivi"
        b.save(update_fields=["internal_note"])
        r.refresh_from_db()
        b.refresh_from_db()
        assert r.statut == "en_attente" and b.status == "requested"


def test_a_suppression_rdv_et_reutilisation_directe_refusees(api_client, salon_a):
    with as_tenant(salon_a.tenant):
        p, _, b, r = attribution(salon_a)
        confirmer(b)
        usage = rdv(salon_a, p, index=1)
        clients.reserver(usage, p)
        usage.status = "cancelled"
        usage.save(update_fields=["status"])
    api_client.force_login(salon_a.owner)
    assert api_client.delete(f"/api/v1/bookings/{b.pk}/").status_code == 400
    assert (
        api_client.patch(
            f"/api/v1/bookings/{usage.pk}/", {"status": "confirmed"}, format="json"
        ).status_code
        == 400
    )
    assert (
        api_client.patch(
            f"/api/v1/bookings/{usage.pk}/", {"total_amount": 1}, format="json"
        ).status_code
        == 400
    )


@pytest.mark.parametrize("code", ["monthly", "yearly", "pro_monthly", "pro_yearly"])
def test_b_premier_paiement_toutes_offres_cooling_et_idempotence(salon_a, salon_b, moyens, code):
    if code.startswith("pro_"):
        plan = Plan.objects.create(
            code=code, name=code, group="pro", billing_months=12 if code.endswith("yearly") else 1
        )
        PlanPrice.objects.create(plan=plan, currency="XAF", amount=20000)
    d, r = premier_paiement(salon_a, salon_b, moyens, code)
    assert r.statut == "en_attente"
    assert (
        abs((r.disponible_le - d.reviewed_at - (d.period_end - d.period_start) / 2).total_seconds())
        < 1
    )
    assert not cycles.avancer(r.pk, r.disponible_le - timedelta(seconds=1))
    assert cycles.avancer(r.pk, r.disponible_le)
    assert not cycles.avancer(r.pk, timezone.now() + timedelta(days=400))
    with as_tenant(salon_b.tenant):
        cycles.paiement_confirme(d)
    assert Remise.objects.filter(paiement_declencheur_id=d.pk).count() == 1
    r.refresh_from_db()
    assert r.pourcentage == 10 and r.expire_le - r.disponible_le == timedelta(days=90)


@pytest.mark.parametrize("etat", ["annule", "rembourse", "conteste"])
def test_b_refund_ou_contestation_avant_disponibilite(salon_a, salon_b, moyens, etat):
    d, r = premier_paiement(salon_a, salon_b, moyens)
    constater(
        d.pk, administrateur=_admin(), etat=etat, motif="Constat vérifié auprès du fournisseur."
    )
    r.refresh_from_db()
    assert r.statut == ("suspendue" if etat == "conteste" else "annulee")
    assert not cycles.avancer(r.pk, timezone.now() + timedelta(days=500))
    if etat == "conteste":
        constater(
            d.pk,
            administrateur=_admin(),
            etat="confirme",
            motif="Contestation résolue et débit conservé.",
        )
        assert cycles.avancer(r.pk, r.disponible_le)


def test_b_remboursement_apres_disponibilite_maintient_droit(salon_a, salon_b, moyens):
    d, r = premier_paiement(salon_a, salon_b, moyens)
    cycles.avancer(r.pk, r.disponible_le)
    constater(
        d.pk,
        administrateur=_admin(),
        etat="rembourse",
        motif="Remboursement après disponibilité du droit.",
    )
    r.refresh_from_db()
    assert r.statut == "disponible"
    with pytest.raises(SubscriptionPaymentRequest.DoesNotExist), as_tenant(salon_a.tenant):
        SubscriptionPaymentRequest.objects.get(pk=d.pk)
    with pytest.raises(Exception) as exc:
        constater(
            d.pk,
            administrateur=salon_a.owner,
            etat="annule",
            motif="Aucune permission de plateforme ici.",
        )
    assert exc.value.code == "permission_refusee"


def test_b_droit_historique_conserve_sans_seconde_recompense(salon_a, salon_b, moyens):
    abonnement_de(salon_b)
    p = services.detecter(
        salon_b.tenant, salon_b.owner, services.code_du_salon(salon_a.tenant).code
    )
    r = remise_pour(salon_a.tenant)
    r.parrainage = p
    r.save(update_fields=["parrainage"])
    d = declarer(salon_b, moyens["momo"])
    billing.approuver_paiement(d.pk, administrateur=_admin())
    assert Remise.objects.filter(parrainage=p).count() == 1
    r.refresh_from_db()
    assert r.statut == "disponible"


def test_b_abandon_libere_et_approbation_tardive_refusee(salon_a, moyens):
    from apps.parrainage.maintenance import entretenir

    abonnement_de(salon_a)
    r = remise_pour(salon_a.tenant)
    d = declarer(salon_a, moyens["momo"])
    r.refresh_from_db()
    r.conditions["reservation_fin"] = (timezone.now() - timedelta(seconds=1)).isoformat()
    r.save(update_fields=["conditions"])
    with pytest.raises(billing.PaiementRefuse) as exc:
        billing.approuver_paiement(d.pk, administrateur=_admin())
    assert exc.value.code == "remise_expiree"
    entretenir()
    r.refresh_from_db()
    assert r.statut == "disponible" and not r.demande_id
    assert EvenementParrainage.objects.filter(ressource=r.pk, action="liberation").count() == 1
    entretenir()
    assert EvenementParrainage.objects.filter(ressource=r.pk, action="liberation").count() == 1


@pytest.fixture
def kki_config(settings, salon_a, offres, request):
    pays = getattr(request, "param", "BJ")
    settings.DEBUG = True
    settings.KKIAPAY_ENABLED = True
    settings.KKIAPAY_SANDBOX = True
    settings.KKIAPAY_ALLOWED_COUNTRIES = [pays]
    for suffix in ("PUBLIC_KEY", "PRIVATE_KEY", "SECRET_KEY", "WEBHOOK_SECRET"):
        setattr(settings, "KKIAPAY_TEST_" + suffix, "test-" + suffix)
    salon_a.tenant.country, salon_a.tenant.currency = pays, "XOF"
    salon_a.tenant.save(update_fields=["country", "currency"])
    abonnement_de(salon_a)
    PlanPrice.objects.create(plan=offres["mensuel"], currency="XOF", amount=15000)
    moyen = PlatformPaymentMethod.objects.create(kind="kkiapay", country=pays, currency="XOF")
    body = {"plan": "monthly", "country": pays, "currency": "XOF", "method": moyen.pk}
    with as_tenant(salon_a.tenant):
        i = kkiapay.preparer(salon_a.tenant.pk, salon_a.owner, body)
    return i, body


@pytest.mark.parametrize(
    "mutation",
    [
        {"status": "FAILED"},
        {"amount": 14999},
        {"currency": "XAF"},
        {"transactionId": "other"},
        {"partnerId": "other"},
    ],
)
def test_kkiapay_reponse_serveur_incorrecte_n_active_rien(
    salon_a, kki_config, monkeypatch, mutation
):
    i, _ = kki_config
    response = {
        "transactionId": "TX001",
        "status": "SUCCESS",
        "amount": 15000,
        "currency": "XOF",
        "partnerId": i["id"],
        **mutation,
    }
    monkeypatch.setattr(kkiapay, "verifier_transaction", lambda *a: response)
    with pytest.raises(billing.PaiementRefuse):
        kkiapay.confirmer(i["id"], "TX001")
    with as_tenant(salon_a.tenant):
        assert SubscriptionPaymentRequest.objects.get().status == "pending"
        assert not Invoice.objects.exists()


def test_kkiapay_confirmation_rejouee_et_webhook_signee(
    api_client, salon_a, kki_config, monkeypatch
):
    i, body = kki_config
    monkeypatch.setattr(
        kkiapay,
        "verifier_transaction",
        lambda *a: {"transactionId": "TX001", "status": "SUCCESS", "amount": 15000},
    )
    with as_tenant(salon_a.tenant):
        assert kkiapay.preparer(salon_a.tenant.pk, salon_a.owner, body)["id"] == i["id"]
    with pytest.raises(billing.PaiementRefuse):
        kkiapay.confirmer(i["id"], "TX001")  # Le navigateur ne fournit aucune liaison fiable.
    payload = {"event": "transaction.success", "transactionId": "TX001", "partnerId": i["id"]}
    url = "/api/v1/webhooks/kkiapay/test"
    assert api_client.post(url, payload, format="json").status_code == 403
    assert (
        api_client.post(
            url, payload, format="json", HTTP_X_KKIAPAY_SECRET="incorrect-é"
        ).status_code
        == 403
    )
    for _ in range(2):
        reponse = api_client.post(
            url, payload, format="json", HTTP_X_KKIAPAY_SECRET="test-WEBHOOK_SECRET"
        )
        assert reponse.status_code == 200, reponse.content
    with as_tenant(salon_a.tenant):
        assert SubscriptionPaymentRequest.objects.get().status == "approved"
        assert Invoice.objects.count() == 1


def test_kkiapay_isolement_pays_et_sandbox_en_production(
    api_client, salon_a, salon_b, kki_config, settings
):
    i, body = kki_config
    api_client.force_login(salon_b.owner)
    response = api_client.post(
        "/api/v1/billing/kkiapay/confirm",
        {"intention": i["id"], "transaction_id": "TX001"},
        format="json",
    )
    assert response.status_code == 404
    with as_tenant(salon_b.tenant), pytest.raises(billing.PaiementRefuse):
        kkiapay.preparer(salon_b.tenant.pk, salon_b.owner, body)
    settings.DEBUG = False
    assert not kkiapay.disponible()


def test_kkiapay_intention_expiree_et_verification_http(kki_config, salon_a, monkeypatch):
    i, _ = kki_config
    calls = []

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "transactionId": "TX001",
                "status": "SUCCESS",
                "amount": 15000,
                "partnerId": i["id"],
            }

    monkeypatch.setattr(
        kkiapay.httpx, "post", lambda url, **kw: calls.append((url, kw)) or Response()
    )
    KkiapayIntent.objects.filter(pk=i["id"]).update(expire_le=timezone.now() - timedelta(seconds=1))
    with pytest.raises(billing.PaiementRefuse) as exc:
        kkiapay.confirmer(i["id"], "TX001")
    assert exc.value.code == "intention_expiree"
    assert calls[0][0] == "https://api-sandbox.kkiapay.me/api/v1/transactions/status"
    assert calls[0][1]["headers"]["X-PRIVATE-KEY"] == "test-PRIVATE_KEY"
    kkiapay.expirer(i["id"])
    with as_tenant(salon_a.tenant):
        assert SubscriptionPaymentRequest.objects.get().status == "rejected"


def test_a_deux_reservations_simultanees_une_seule_reduction(salon_a, monkeypatch):
    import threading

    from django.db import connections

    from apps.scheduling.services import booking as parcours

    with as_tenant(salon_a.tenant):
        p, _, b, r = attribution(salon_a)
        confirmer(b)
    monkeypatch.setattr(parcours, "is_slot_available", lambda **kwargs: True)
    barriere = threading.Barrier(2)
    resultats, erreurs = [], []

    def reserver(index):
        try:
            barriere.wait(timeout=10)
            with as_tenant(salon_a.tenant):
                obj = parcours.create_booking(
                    tenant=salon_a.tenant,
                    service=salon_a.service,
                    staff_member=salon_a.staff,
                    starts_at=timezone.now() + timedelta(days=4 + index),
                    customer=parcours.CustomerDetails(
                        full_name=p.display_name, phone=f"+24206555555{index}", email=p.email
                    ),
                    compte=p,
                )
                resultats.append(obj.reduction_parrainage)
        except Exception as exc:
            erreurs.append(exc)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=reserver, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)
    assert not any(t.is_alive() for t in threads)
    assert not erreurs, erreurs
    assert sorted(resultats) == [0, 500]


def test_finances_anciennes_ecritures_lecture_seule(api_client, salon_a):
    from apps.finance.models import Transaction

    with as_tenant(salon_a.tenant):
        t = Transaction.objects.create(
            tenant=salon_a.tenant,
            kind="expense",
            category="supplies",
            label="Ancienne écriture conservée",
            amount=12000,
            currency="XAF",
            occurred_on=timezone.now().date(),
            source="manual",
        )
    api_client.force_login(salon_a.owner)
    assert api_client.get(f"/api/v1/transactions/{t.pk}/").status_code == 200
    assert (
        api_client.patch(f"/api/v1/transactions/{t.pk}/", {"amount": 1}, format="json").status_code
        == 405
    )
    assert api_client.delete(f"/api/v1/transactions/{t.pk}/").status_code == 405
    with as_tenant(salon_a.tenant):
        t.refresh_from_db()
        assert t.amount == 12000
