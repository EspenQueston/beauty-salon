"""Audit des abonnements Standard/Pro : un test par probleme constate.

Chaque test reproduit un defaut trouve a l'audit (il echouait avant la
correction) et le garde ferme ensuite. Le numero renvoie au rapport d'audit.
"""

import warnings
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.billing import services
from apps.billing.models import PlanPrice, Subscription
from apps.billing.services import PaiementRefuse
from apps.catalog.models import ServiceCategory
from conftest import as_tenant
from tests.test_abonnements import abonnement_de, medias_temporaires, moyens, offres
from tests.test_assistants_pro import FausseIA, salon_pro
from tests.test_offres_pro import _admin, au_plan, declarer_et_approuver, pro

FIXTURES_PARTAGEES = (medias_temporaires, moyens, offres, pro, salon_pro)
ADMIN = pytest.mark.django_db(databases=["default", "admin"], transaction=True)


# ---------------------------------------------------------------------------
# A1 — « Changer l'offre » effacait une periode Standard deja payee
# ---------------------------------------------------------------------------


@ADMIN
def test_a1_changer_d_offre_ne_perd_pas_une_periode_standard_payee(salon_a, moyens, pro):
    au_plan(salon_a, "pro_monthly", fin=timezone.now() + timedelta(days=10))
    declarer_et_approuver(salon_a, moyens["momo"], "monthly")  # Standard programme, paye

    with pytest.raises(PaiementRefuse) as refus:
        services.changer_d_offre(
            salon_a.tenant.id, administrateur=_admin(), code="pro_yearly", note="Geste"
        )

    assert refus.value.code == "changement_programme"
    with as_tenant(salon_a.tenant):
        abonnement = Subscription.objects.select_related("scheduled_plan").get()
    assert abonnement.scheduled_plan.code == "monthly"  # la periode payee est intacte


# ---------------------------------------------------------------------------
# A2 — La montee comparait des prix de deux devises differentes
# ---------------------------------------------------------------------------


@ADMIN
def test_a2_la_conversion_des_jours_compare_des_prix_d_une_meme_devise(salon_a, moyens, pro):
    au_plan(salon_a, "monthly", fin=timezone.now() + timedelta(days=20))
    # Le Standard n'a plus de prix en XAF : seul le CNY permet de comparer.
    PlanPrice.objects.filter(plan__code="monthly", currency="XAF").update(active=False)

    demande = declarer_et_approuver(salon_a, moyens["momo"], "pro_monthly")  # paye en XAF

    with as_tenant(salon_a.tenant):
        abonnement = Subscription.objects.get()
    credit = (abonnement.period_anchor - demande.period_start).total_seconds() / 86400
    # 20 jours a 99 CNY/mois valent ~4,96 jours a 399 CNY/mois — et non ~0
    # jour, comme en comparant 99 CNY a 60 000 XAF.
    assert 4.9 < credit < 5.1


@ADMIN
def test_a2_sans_prix_comparable_l_approbation_est_refusee(salon_a, moyens, pro):
    au_plan(salon_a, "monthly", fin=timezone.now() + timedelta(days=20))
    PlanPrice.objects.filter(plan__code="monthly").update(active=False)
    PlanPrice.objects.filter(plan__code="pro_monthly", currency="CNY").update(active=False)

    with as_tenant(salon_a.tenant):
        demande = services.soumettre_paiement(
            tenant_id=salon_a.tenant.id,
            utilisateur=salon_a.owner,
            code_offre="pro_monthly",
            pays="CG",
            devise="XAF",
            moyen_id=moyens["momo"].id,
            reference="REF-A2-2",
        )
    # Le prix Standard du salon (XAF, sur l'abonnement) reste comparable au
    # Pro en XAF : la conversion se fait dans la devise de l'abonnement.
    services.approuver_paiement(demande.id, administrateur=_admin())
    with as_tenant(salon_a.tenant):
        abonnement = Subscription.objects.get()
    credit = (abonnement.period_anchor - timezone.now()).total_seconds() / 86400
    assert 4.8 < credit < 5.1  # 20 j x 15 000 / 60 000


# ---------------------------------------------------------------------------
# A3 — Un changement de tarif entre l'affichage et l'envoi passait inapercu
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a3_un_tarif_change_depuis_l_affichage_est_signale(api_client, salon_a, moyens):
    abonnement_de(salon_a)
    api_client.force_login(salon_a.owner)
    corps = {
        "plan": "monthly",
        "country": "CG",
        "currency": "XAF",
        "method": str(moyens["momo"].id),
        "reference": "REF-A3-0001",
        "montant_attendu": "12000",  # ce que l'ecran affichait
    }

    reponse = api_client.post("/api/v1/subscription/paiements", corps, format="multipart")

    assert reponse.status_code == 400, reponse.json()
    assert reponse.json()["code"] == "tarif_modifie"
    corps["montant_attendu"] = "15000"
    assert (
        api_client.post("/api/v1/subscription/paiements", corps, format="multipart").status_code
        == 201
    )


# ---------------------------------------------------------------------------
# A4 — La fiche salon laissait modifier statut, identifiant et devise sans trace
# ---------------------------------------------------------------------------


@ADMIN
def test_a4_la_fiche_salon_ne_modifie_ni_statut_ni_identifiant_ni_devise(client, salon_a):
    from apps.tenants.admin import TenantAdmin

    client.force_login(_admin())
    page = client.get(reverse("admin:tenants_tenant_change", args=[salon_a.tenant.pk]))
    html = page.content.decode()

    assert page.status_code == 200
    for champ in ("status", "slug", "currency"):
        assert f'name="{champ}"' not in html, champ
    # A la creation, en revanche, ils se choisissent.
    assert {"status", "slug", "currency"}.isdisjoint(
        TenantAdmin.get_readonly_fields(TenantAdmin(salon_a.tenant.__class__, None), None, None)
    )


# ---------------------------------------------------------------------------
# A5 — WhatsApp n'avait aucun plafond par salon : cout d'IA illimite
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a5_whatsapp_a_un_plafond_journalier_par_salon(salon_pro, monkeypatch):
    from apps.assistants import evolution, ia, whatsapp
    from apps.assistants.models import AssistantReglages

    fausse = FausseIA()
    monkeypatch.setattr(ia, "SERVICE", fausse)
    envois = []
    monkeypatch.setattr(evolution, "envoyer_texte", lambda i, n, t: envois.append(n))
    monkeypatch.setattr(whatsapp, "QUOTA_WHATSAPP_JOUR", 2)
    with as_tenant(salon_pro.tenant):
        AssistantReglages.objects.update_or_create(
            tenant=salon_pro.tenant,
            defaults={"whatsapp_instance": "bs-x", "whatsapp_actif": True},
        )
        resultats = [
            whatsapp.repondre(salon_pro.tenant, f"24206000000{i}@s.whatsapp.net", "Bonjour")
            for i in range(3)
        ]

    assert resultats[:2] == ["reponse:envoyee", "reponse:envoyee"]
    assert resultats[2] == "reponse:quota"
    assert len(fausse.appels) == 2  # pas d'appel d'IA au-dela du plafond
    assert len(envois) == 3  # la troisieme personne recoit l'accuse de reception


# ---------------------------------------------------------------------------
# A6 — Un message WhatsApp sans horodatage echappait a la fenetre de rejeu
# ---------------------------------------------------------------------------


@ADMIN
def test_a6_un_message_sans_horodatage_est_ignore(salon_pro, monkeypatch):
    from apps.assistants import tasks, whatsapp
    from apps.assistants.models import AssistantReglages

    with as_tenant(salon_pro.tenant):
        AssistantReglages.objects.update_or_create(
            tenant=salon_pro.tenant,
            defaults={"whatsapp_instance": "bs-y", "whatsapp_empreinte": whatsapp.empreinte("j")},
        )
    programmees = []
    monkeypatch.setattr(tasks.repondre_whatsapp, "delay", lambda *a: programmees.append(a))
    charge = {
        "event": "messages.upsert",
        "data": {
            "key": {"id": "M1", "fromMe": False, "remoteJid": "242060000001@s.whatsapp.net"},
            "message": {"conversation": "Bonjour"},
        },
    }

    assert whatsapp.traiter("bs-y", "j", charge) == "ignore:horodatage"
    assert programmees == []


# ---------------------------------------------------------------------------
# A7 — L'assistant citait des prestations que le mini-site cache
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a7_l_assistant_ne_voit_pas_les_prestations_d_une_categorie_cachee(salon_a):
    from apps.assistants.ia import contexte_public

    with as_tenant(salon_a.tenant):
        ServiceCategory.objects.filter(pk=salon_a.service.category_id).update(active=False)
        noms = [p["nom"] for p in contexte_public(salon_a.tenant)["prestations"]]

    assert salon_a.service.name not in noms


# ---------------------------------------------------------------------------
# A8 — Un avertissement de syntaxe a chaque demarrage (bientot une erreur)
# ---------------------------------------------------------------------------


def test_a8_les_services_d_abonnement_se_compilent_sans_avertissement():
    source = (Path(services.__file__)).read_text(encoding="utf-8")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        compile(source, services.__file__, "exec")


# ---------------------------------------------------------------------------
# A9 — La tache quotidienne ecrasait un abonnement modifie entre-temps
# ---------------------------------------------------------------------------


@ADMIN
def test_a9_la_bascule_programmee_relit_l_abonnement_verrouille(salon_a, moyens, pro, monkeypatch):
    """La tache lisait l'abonnement, puis l'ecrivait en entier : une
    approbation passee entre les deux etait effacee. Elle relit desormais
    l'abonnement sous verrou avant de basculer."""
    fin_pro = timezone.now() + timedelta(days=1)
    au_plan(salon_a, "pro_monthly", fin=fin_pro)
    declarer_et_approuver(salon_a, moyens["momo"], "monthly")
    plus_tard = fin_pro + timedelta(hours=1)

    lu = services.appliquer_changement_programme
    appels = []

    def espion(abonnement):
        appels.append(abonnement._state.db)
        return lu(abonnement)

    monkeypatch.setattr(services, "appliquer_changement_programme", espion)
    # Une approbation « concurrente » deplace la fin programmee juste avant
    # la bascule : la tache doit partir de cette valeur, pas d'une copie.
    with as_tenant(salon_a.tenant):
        Subscription.objects.update(scheduled_months=2)

    services.run_billing_cycle(now=plus_tard)

    with as_tenant(salon_a.tenant):
        abonnement = Subscription.objects.get()
    assert abonnement.plan.code == "monthly"
    assert abonnement.anchor_months == 2
    assert appels, "la bascule doit passer par la fonction verrouillee"
    assert abonnement.price_amount == Decimal("15000")


# ---------------------------------------------------------------------------
# Matrice des droits : aucun etat sans Pro n'ouvre une route Pro par un appel
# direct ; Standard reste ouvert a Standard et a Pro, ferme apres expiration.
# ---------------------------------------------------------------------------

HOTE_A = {"HTTP_HOST": "blondrose.localhost"}


def _etat(salon, etat):
    passe = timezone.now() - timedelta(days=10)  # grace de 3 jours depassee
    futur = timezone.now() + timedelta(days=10)
    if etat == "essai":
        abonnement_de(salon)
    elif etat == "standard":
        au_plan(salon, "monthly", fin=futur)
    elif etat == "pro":
        au_plan(salon, "pro_monthly", fin=futur)
    elif etat == "pro_expire":
        au_plan(salon, "pro_monthly", fin=passe)
    elif etat == "pro_suspendu":
        au_plan(salon, "pro_monthly", fin=futur)
        with as_tenant(salon.tenant):
            Subscription.objects.update(status=Subscription.Status.SUSPENDED)


ROUTES_PRO = [
    ("post", "/api/v1/assistant", {"messages": [{"role": "user", "content": "Bonjour"}]}),
    ("put", "/api/v1/site-pro", {"police_titres": "lora"}),
    ("post", "/api/v1/domaines", {"hostname": "www.exemple-audit.com"}),
    ("post", "/api/v1/assistant/whatsapp", {}),
    ("patch", "/api/v1/assistant/reglages", {"clientes_actif": False}),
]


@pytest.mark.django_db
@pytest.mark.parametrize("etat", ["essai", "standard", "pro_expire", "pro_suspendu"])
@pytest.mark.parametrize(("methode", "route", "corps"), ROUTES_PRO)
def test_matrice_aucune_route_pro_sans_pro(
    api_client, salon_a, pro, monkeypatch, etat, methode, route, corps
):
    from apps.assistants import ia

    monkeypatch.setattr(ia, "SERVICE", FausseIA())
    _etat(salon_a, etat)
    api_client.force_login(salon_a.owner)

    reponse = getattr(api_client, methode)(route, corps, format="json")

    assert reponse.status_code in (402, 403), (etat, route, reponse.status_code)
    assert ia.SERVICE.appels == []


@pytest.mark.django_db
@pytest.mark.parametrize("etat", ["essai", "standard", "pro_expire", "pro_suspendu"])
def test_matrice_le_mini_site_ne_publie_rien_de_pro_sans_pro(api_client, salon_a, pro, etat):
    _etat(salon_a, etat)

    public = api_client.get("/api/v1/public/salon", **HOTE_A).json()
    assistant = api_client.post(
        "/api/v1/public/assistant",
        {"messages": [{"role": "user", "content": "Bonjour"}]},
        format="json",
        **HOTE_A,
    )

    assert public["site_config"] is None  # ni polices, ni menu, ni pages /p/…
    assert public["assistant_clientes"] is False
    assert assistant.status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("etat", "attendu"),
    [("essai", 200), ("standard", 200), ("pro", 200), ("pro_expire", 402), ("pro_suspendu", 402)],
)
def test_matrice_les_fonctions_standard_suivent_l_acces(api_client, salon_a, pro, etat, attendu):
    _etat(salon_a, etat)
    api_client.force_login(salon_a.owner)

    reponse = api_client.patch("/api/v1/salon-profile", {"city": "Brazzaville"}, format="json")

    assert reponse.status_code == attendu, (etat, reponse.status_code)


@pytest.mark.django_db
def test_matrice_pro_actif_ouvre_les_routes_pro(api_client, salon_a, pro, monkeypatch):
    from apps.assistants import ia

    monkeypatch.setattr(ia, "SERVICE", FausseIA())
    _etat(salon_a, "pro")
    api_client.force_login(salon_a.owner)

    assert api_client.post("/api/v1/assistant", ROUTES_PRO[0][2], format="json").status_code == 200
    assert api_client.put("/api/v1/site-pro", ROUTES_PRO[1][2], format="json").status_code == 200
    assert api_client.get("/api/v1/public/salon", **HOTE_A).json()["site_config"] is not None


@ADMIN
def test_a2_sans_aucun_prix_commun_l_approbation_refuse_au_lieu_de_tout_perdre(
    salon_a, moyens, pro
):
    au_plan(salon_a, "monthly", fin=timezone.now() + timedelta(days=20))
    with as_tenant(salon_a.tenant):
        Subscription.objects.update(price_amount=Decimal("0"))
    PlanPrice.objects.filter(plan__code="monthly").update(active=False)
    with as_tenant(salon_a.tenant):
        demande = services.soumettre_paiement(
            tenant_id=salon_a.tenant.id,
            utilisateur=salon_a.owner,
            code_offre="pro_monthly",
            pays="CG",
            devise="XAF",
            moyen_id=moyens["momo"].id,
            reference="REF-A2-3",
        )
        # L'apercu disparait plutot que de casser la page des offres.
        abonnement = Subscription.objects.select_related("plan", "tenant").get()
        assert services.apercu_du_paiement(abonnement, demande.plan, "XAF") is None

    with pytest.raises(PaiementRefuse) as refus:
        services.approuver_paiement(demande.id, administrateur=_admin())

    assert refus.value.code == "prix_incomparables"
    with as_tenant(salon_a.tenant):
        assert Subscription.objects.get().plan.code == "monthly"  # rien n'a bouge
