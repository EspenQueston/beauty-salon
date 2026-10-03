"""Le parrainage : codes, admissibilite, remises, application aux paiements.

Regles decidees avec le produit (voir apps/parrainage/models.py) : un parrain
par filleul, fige a l'inscription ; admissible 14 jours apres publication ou
au premier paiement approuve ; 10 % par filleul admissible, et 10 % par
paiement approuve du filleul pour un salon parrain (12 au plus) ; 30 % au plus
par paiement ; 12 mois de validite ; jamais de l'argent.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.admin import helpers
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.billing import services as facturation
from apps.billing.models import Invoice, Subscription, SubscriptionPaymentRequest
from apps.billing.services import PaiementRefuse
from apps.clients.models import ClientProfile
from apps.parrainage import services
from apps.parrainage.models import CodeParrainage, Parrainage, Remise
from apps.tenants.models import Tenant
from conftest import as_tenant
from tests.factories import MembershipFactory, TenantFactory, UserFactory
from tests.test_abonnements import (
    ADMIN,
    _admin,
    abonnement_de,
    medias_temporaires,
    moyens,
    offres,
)
from tests.test_auth_flows import signup_payload

FIXTURES_PARTAGEES = (medias_temporaires, moyens, offres)


# ---------------------------------------------------------------------------
# Outils
# ---------------------------------------------------------------------------


def filleul_de(code, *, nom="Filleul", publie_il_y_a=None, statut=Tenant.Status.ACTIVE, phone=""):
    """Un salon filleul inscrit avec `code`, et son proprietaire."""
    tenant = TenantFactory(name=nom, status=statut)
    proprietaire = UserFactory(phone=phone)
    MembershipFactory(tenant=tenant, user=proprietaire)
    parrainage = services.detecter(tenant, proprietaire, code.code)
    if publie_il_y_a is not None:
        Parrainage.objects.filter(pk=parrainage.pk).update(publie_le=timezone.now() - publie_il_y_a)
    parrainage.refresh_from_db()
    return parrainage


def remise_pour(tenant, *, pourcentage="10", jours=365, reference=None):
    return Remise.objects.create(
        beneficiaire_tenant=tenant,
        filleul_nom="Un filleul",
        declencheur=Remise.Declencheur.INSCRIPTION,
        reference=reference or f"test:{Remise.objects.count()}:{tenant.pk}",
        pourcentage=Decimal(pourcentage),
        expire_le=timezone.now() + timedelta(days=jours),
    )


def declarer(salon, moyen, *, code="monthly", reference="REF-PARR-1", montant_attendu=None):
    with as_tenant(salon.tenant):
        return facturation.soumettre_paiement(
            tenant_id=salon.tenant.id,
            utilisateur=salon.owner,
            code_offre=code,
            pays=moyen.country,
            devise=moyen.currency,
            moyen_id=moyen.id,
            reference=reference,
            montant_attendu=montant_attendu,
        )


# ---------------------------------------------------------------------------
# Codes
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_chaque_salon_a_son_code_stable_et_non_devinable(salon_a, salon_b):
    code_a = services.code_du_salon(salon_a.tenant)
    code_b = services.code_du_salon(salon_b.tenant)

    assert code_a.code != code_b.code
    assert len(code_a.code) == services.LONGUEUR_CODE
    assert set(code_a.code) <= set(services.ALPHABET)
    # Stable : le meme code a chaque lecture.
    assert services.code_du_salon(salon_a.tenant).pk == code_a.pk


@pytest.mark.django_db
def test_un_code_se_saisit_sans_souci_de_casse_ni_d_espaces(salon_a):
    code = services.code_du_salon(salon_a.tenant)
    saisie = f" {code.code[:5].lower()} {code.code[5:]} "

    assert services.resoudre(saisie).pk == code.pk


@pytest.mark.django_db
def test_un_code_desactive_n_est_plus_accepte(salon_a):
    code = services.code_du_salon(salon_a.tenant)
    CodeParrainage.objects.filter(pk=code.pk).update(actif=False)

    assert services.resoudre(code.code) is None


# ---------------------------------------------------------------------------
# Inscription du filleul
# ---------------------------------------------------------------------------


@ADMIN
def test_l_inscription_avec_un_code_enregistre_le_parrain(api_client, salon_a, offres):
    code = services.code_du_salon(salon_a.tenant)

    reponse = api_client.post(
        "/api/v1/account/signup",
        signup_payload(code_parrainage=code.code.lower()),
        format="json",
    )

    assert reponse.status_code == 201, reponse.data
    parrainage = Parrainage.objects.get(filleul__slug="studio-kine")
    assert parrainage.parrain_tenant_id == salon_a.tenant.id
    assert parrainage.type_parrain == Parrainage.TypeParrain.SALON
    assert parrainage.statut == Parrainage.Statut.EN_VERIFICATION
    with as_tenant(parrainage.filleul):
        abonnement = Subscription.objects.get(tenant=parrainage.filleul)
        assert abonnement.trial_ends_at - abonnement.current_period_start == timedelta(days=30)
    # Aucune remise avant l'admissibilite.
    assert not Remise.objects.exists()
    assert AuditLog.objects.filter(action=AuditLog.Action.REFERRAL_DETECTED).exists()


@ADMIN
def test_un_code_inconnu_bloque_l_inscription(api_client, offres):
    reponse = api_client.post(
        "/api/v1/account/signup", signup_payload(code_parrainage="ZZZZZZZZZZ"), format="json"
    )

    assert reponse.status_code == 400
    assert not Tenant.objects.filter(slug="studio-kine").exists()


@ADMIN
def test_sans_code_l_inscription_ne_change_pas(api_client, offres):
    reponse = api_client.post("/api/v1/account/signup", signup_payload(), format="json")

    assert reponse.status_code == 201
    assert not Parrainage.objects.exists()
    tenant = Tenant.objects.get(slug="studio-kine")
    with as_tenant(tenant):
        abonnement = Subscription.objects.get(tenant=tenant)
        assert abonnement.trial_ends_at - abonnement.current_period_start == timedelta(days=14)


@ADMIN
def test_un_parrainage_refuse_ne_prolonge_pas_l_essai(api_client, salon_a, offres):
    salon_a.owner.phone = "+242 06 123 4567"
    salon_a.owner.save(update_fields=["phone"])
    code = services.code_du_salon(salon_a.tenant)

    reponse = api_client.post(
        "/api/v1/account/signup",
        signup_payload(code_parrainage=code.code, phone="242061234567"),
        format="json",
    )

    assert reponse.status_code == 201, reponse.data
    tenant = Tenant.objects.get(slug="studio-kine")
    assert Parrainage.objects.get(filleul=tenant).statut == Parrainage.Statut.REFUSE
    with as_tenant(tenant):
        abonnement = Subscription.objects.get(tenant=tenant)
        assert abonnement.trial_ends_at - abonnement.current_period_start == timedelta(days=14)


@pytest.mark.django_db
def test_un_seul_parrain_par_filleul(salon_a, salon_b):
    parrainage = filleul_de(services.code_du_salon(salon_a.tenant))

    # La contrainte d'unicite en base tranche, meme si deux inscriptions se croisent.
    with pytest.raises(IntegrityError), transaction.atomic():
        services.detecter(
            parrainage.filleul, UserFactory(), services.code_du_salon(salon_b.tenant).code
        )


@pytest.mark.django_db
def test_se_parrainer_avec_le_telephone_d_un_membre_est_refuse(salon_a):
    salon_a.owner.phone = "+242 06 123 4567"
    salon_a.owner.save()

    parrainage = filleul_de(services.code_du_salon(salon_a.tenant), phone="242061234567")

    assert parrainage.statut == Parrainage.Statut.REFUSE
    assert "membre" in parrainage.motif


@pytest.mark.django_db
def test_une_cliente_ne_se_parraine_pas_elle_meme():
    cliente = UserFactory(phone="+86 136 1234 5678")
    code = services.code_de_l_utilisateur(cliente)
    tenant = TenantFactory()
    MembershipFactory(tenant=tenant, user=cliente)

    parrainage = services.detecter(tenant, cliente, code.code)

    assert parrainage.statut == Parrainage.Statut.REFUSE


# ---------------------------------------------------------------------------
# Admissibilite
# ---------------------------------------------------------------------------


@ADMIN
def test_admissible_apres_14_jours_de_publication(salon_a, offres):
    code = services.code_du_salon(salon_a.tenant)
    parrainage = filleul_de(code, publie_il_y_a=timedelta(days=15))
    abonnement_de_tenant(parrainage.filleul)

    resultat = services.evaluer()

    parrainage.refresh_from_db()
    assert resultat["admissibles"] == 1
    assert parrainage.statut == Parrainage.Statut.ADMISSIBLE
    remise = Remise.objects.get()
    assert remise.beneficiaire_tenant_id == salon_a.tenant.id
    assert remise.pourcentage == Decimal("10")
    assert remise.declencheur == Remise.Declencheur.INSCRIPTION
    assert abs((remise.expire_le - timezone.now() - timedelta(days=365)).total_seconds()) < 60


@ADMIN
def test_l_evaluation_rejouee_ne_cree_pas_de_seconde_remise(salon_a, offres):
    parrainage = filleul_de(
        services.code_du_salon(salon_a.tenant), publie_il_y_a=timedelta(days=20)
    )
    abonnement_de_tenant(parrainage.filleul)

    services.evaluer()
    services.evaluer()
    services.rendre_admissible(parrainage.pk)

    assert Remise.objects.count() == 1


@ADMIN
def test_pas_admissible_avant_14_jours_ni_sans_publication(salon_a, offres):
    code = services.code_du_salon(salon_a.tenant)
    recent = filleul_de(code, nom="Récent", publie_il_y_a=timedelta(days=3))
    en_attente = filleul_de(code, nom="En attente", statut=Tenant.Status.PENDING)
    for p in (recent, en_attente):
        abonnement_de_tenant(p.filleul)

    services.evaluer()

    assert set(Parrainage.objects.values_list("statut", flat=True)) == {
        Parrainage.Statut.EN_VERIFICATION
    }
    assert not Remise.objects.exists()


@ADMIN
def test_un_filleul_suspendu_n_est_pas_admissible(salon_a, offres):
    parrainage = filleul_de(
        services.code_du_salon(salon_a.tenant), publie_il_y_a=timedelta(days=20)
    )
    abonnement_de_tenant(parrainage.filleul, statut=Subscription.Status.SUSPENDED)

    services.evaluer()

    parrainage.refresh_from_db()
    assert parrainage.statut == Parrainage.Statut.EN_VERIFICATION


@ADMIN
def test_au_dela_de_10_filleuls_en_30_jours_une_revue_est_exigee(salon_a, offres):
    code = services.code_du_salon(salon_a.tenant)
    for i in range(services.ADMISSIBLES_PAR_MOIS):
        p = filleul_de(code, nom=f"Filleul {i}")
        services.rendre_admissible(p.pk)
    suivant = filleul_de(code, nom="Onzième", publie_il_y_a=timedelta(days=20))
    abonnement_de_tenant(suivant.filleul)

    resultat = services.evaluer()

    suivant.refresh_from_db()
    assert resultat["revues"] == 1
    assert suivant.revue_requise is True
    assert suivant.statut == Parrainage.Statut.EN_VERIFICATION
    # Validation humaine : motivee, puis admissible.
    services.valider_manuellement(suivant, _admin(), "Salons vérifiés un par un par téléphone.")
    suivant.refresh_from_db()
    assert suivant.statut == Parrainage.Statut.ADMISSIBLE


def abonnement_de_tenant(tenant, *, statut=Subscription.Status.ACTIVE):
    class _Salon:
        pass

    salon = _Salon()
    salon.tenant = tenant
    return abonnement_de(salon, statut=statut, fin=timezone.now() + timedelta(days=20), essai=False)


# ---------------------------------------------------------------------------
# Remises sur un paiement du parrain
# ---------------------------------------------------------------------------


@ADMIN
def test_la_remise_reduit_le_paiement_puis_est_consommee(salon_a, moyens):
    abonnement_de(salon_a)
    remise = remise_pour(salon_a.tenant)

    demande = declarer(salon_a, moyens["momo"])

    assert demande.montant_catalogue == Decimal("15000")
    assert demande.amount == Decimal("13500")
    assert demande.remise_montant == Decimal("1500")
    remise.refresh_from_db()
    assert remise.statut == Remise.Statut.RESERVEE
    assert remise.demande_id == demande.id

    facturation.approuver_paiement(demande.id, administrateur=_admin())

    remise.refresh_from_db()
    assert remise.statut == Remise.Statut.UTILISEE
    assert remise.montant_deduit == Decimal("1500")
    with as_tenant(salon_a.tenant):
        abonnement = Subscription.objects.get()
        facture = Invoice.objects.get()
    # L'abonnement garde le tarif (base des conversions), la facture le verse.
    assert abonnement.price_amount == Decimal("15000")
    assert facture.amount == Decimal("13500")
    assert "parrainage" in facture.label


@ADMIN
def test_un_paiement_refuse_rend_la_remise(salon_a, moyens):
    abonnement_de(salon_a)
    remise = remise_pour(salon_a.tenant)
    demande = declarer(salon_a, moyens["momo"])

    facturation.refuser_paiement(demande.id, administrateur=_admin(), motif="Référence introuvable")

    remise.refresh_from_db()
    assert remise.statut == Remise.Statut.DISPONIBLE
    assert remise.demande_id is None
    # Et elle resert au paiement suivant.
    suivante = declarer(salon_a, moyens["momo"], reference="REF-PARR-2")
    assert suivante.amount == Decimal("13500")


@ADMIN
def test_trente_pour_cent_au_plus_par_paiement(salon_a, moyens):
    abonnement_de(salon_a)
    remises = [remise_pour(salon_a.tenant, jours=100 + i) for i in range(4)]

    demande = declarer(salon_a, moyens["momo"])

    assert demande.remise_pourcentage == Decimal("30")
    assert demande.amount == Decimal("10500")
    # Les plus proches de l'expiration d'abord ; la quatrieme attend.
    statuts = [Remise.objects.get(pk=r.pk).statut for r in remises]
    assert statuts == [Remise.Statut.RESERVEE] * 3 + [Remise.Statut.DISPONIBLE]


@ADMIN
def test_une_remise_expiree_ne_s_applique_pas(salon_a, moyens):
    abonnement_de(salon_a)
    remise = remise_pour(salon_a.tenant, jours=-1)

    assert services.expirer() == 1
    demande = declarer(salon_a, moyens["momo"])

    assert demande.amount == Decimal("15000")
    remise.refresh_from_db()
    assert remise.statut == Remise.Statut.EXPIREE


@ADMIN
def test_le_montant_confirme_doit_etre_celui_remise_deduite(salon_a, moyens):
    abonnement_de(salon_a)
    remise_pour(salon_a.tenant)

    with pytest.raises(PaiementRefuse) as refus:
        declarer(salon_a, moyens["momo"], montant_attendu=Decimal("15000"))
    assert refus.value.code == "tarif_modifie"
    # Rien n'a ete reserve par la tentative refusee.
    assert Remise.objects.get().statut == Remise.Statut.DISPONIBLE

    demande = declarer(salon_a, moyens["momo"], montant_attendu=Decimal("13500"))
    assert demande.amount == Decimal("13500")


@ADMIN
def test_les_offres_annoncent_le_montant_remise(api_client, salon_a, moyens):
    abonnement_de(salon_a)
    remise_pour(salon_a.tenant)
    api_client.force_login(salon_a.owner)

    reponse = api_client.get("/api/v1/subscription/offres").json()

    devise = next(p for p in reponse["pays"] if p["code"] == "CG")["devises"][0]
    mensuel = next(p for p in devise["plans"] if p["code"] == "monthly")
    assert mensuel["montant"] == "15000.00"
    assert mensuel["montant_final"] == "13500.00"
    assert reponse["remise_parrainage"] == {"pourcentage": "10", "nombre": 1}


def test_arrondi_selon_la_devise():
    assert services.arrondir(Decimal("1234.5"), "XAF") == Decimal("1235")
    assert services.arrondir(Decimal("39.905"), "CNY") == Decimal("39.91")


# ---------------------------------------------------------------------------
# Remises nees des paiements du filleul
# ---------------------------------------------------------------------------


@ADMIN
def test_le_premier_paiement_du_filleul_le_rend_admissible_et_recompense(salon_a, salon_b, moyens):
    abonnement_de(salon_b)
    services.detecter(salon_b.tenant, salon_b.owner, services.code_du_salon(salon_a.tenant).code)

    demande = declarer(salon_b, moyens["momo"])
    facturation.approuver_paiement(demande.id, administrateur=_admin())

    parrainage = Parrainage.objects.get()
    assert parrainage.statut == Parrainage.Statut.ADMISSIBLE
    references = set(Remise.objects.values_list("reference", flat=True))
    assert references == {f"inscription:{parrainage.pk}", f"paiement:{demande.pk}"}
    assert set(Remise.objects.values_list("beneficiaire_tenant", flat=True)) == {salon_a.tenant.id}


@ADMIN
def test_la_recompense_d_un_paiement_est_idempotente(salon_a, salon_b, moyens):
    abonnement_de(salon_b)
    services.detecter(salon_b.tenant, salon_b.owner, services.code_du_salon(salon_a.tenant).code)
    demande = declarer(salon_b, moyens["momo"])
    facturation.approuver_paiement(demande.id, administrateur=_admin())

    services.recompenser_paiement(demande)
    with pytest.raises(PaiementRefuse):
        facturation.approuver_paiement(demande.id, administrateur=_admin())

    assert Remise.objects.filter(declencheur=Remise.Declencheur.PAIEMENT).count() == 1


@pytest.mark.django_db
def test_douze_remises_de_paiement_au_plus_par_filleul(salon_a):
    parrainage = filleul_de(services.code_du_salon(salon_a.tenant))
    services.rendre_admissible(parrainage.pk)

    class Demande:
        def __init__(self, pk):
            self.pk = pk
            self.tenant_id = parrainage.filleul_id

    for i in range(15):
        services.recompenser_paiement(Demande(f"d{i}"))

    assert Remise.objects.filter(declencheur=Remise.Declencheur.PAIEMENT).count() == 12


@pytest.mark.django_db
def test_une_cliente_marraine_n_est_recompensee_qu_une_fois():
    cliente = UserFactory()
    parrainage = filleul_de(services.code_de_l_utilisateur(cliente))

    class Demande:
        pk = "d1"
        tenant_id = parrainage.filleul_id

    services.recompenser_paiement(Demande())
    services.recompenser_paiement(Demande())

    remise = Remise.objects.get()
    assert remise.beneficiaire_user_id == cliente.pk
    assert remise.declencheur == Remise.Declencheur.INSCRIPTION


@ADMIN
def test_la_remise_d_une_cliente_sert_sur_le_salon_qu_elle_possede(salon_a, moyens):
    abonnement_de(salon_a)
    Remise.objects.create(
        beneficiaire_user=salon_a.owner,
        filleul_nom="Un filleul",
        declencheur=Remise.Declencheur.INSCRIPTION,
        reference="test:cliente",
        pourcentage=Decimal("10"),
        expire_le=timezone.now() + timedelta(days=30),
    )

    demande = declarer(salon_a, moyens["momo"])

    assert demande.amount == Decimal("13500")


@ADMIN
def test_un_parrainage_refuse_ne_recompense_rien(salon_a, salon_b, moyens):
    abonnement_de(salon_b)
    parrainage = services.detecter(
        salon_b.tenant, salon_b.owner, services.code_du_salon(salon_a.tenant).code
    )
    Parrainage.objects.filter(pk=parrainage.pk).update(statut=Parrainage.Statut.REFUSE)

    demande = declarer(salon_b, moyens["momo"])
    facturation.approuver_paiement(demande.id, administrateur=_admin())

    assert not Remise.objects.exists()


# ---------------------------------------------------------------------------
# Corrections de l'administration
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_invalider_annule_les_remises_disponibles_avec_un_motif(salon_a):
    parrainage = filleul_de(services.code_du_salon(salon_a.tenant))
    services.rendre_admissible(parrainage.pk)
    admin = _admin()

    with pytest.raises(ValueError):
        services.invalider(parrainage, admin, "court")

    assert services.invalider(parrainage, admin, "Même gérante derrière les deux salons.") == 1
    parrainage.refresh_from_db()
    assert parrainage.statut == Parrainage.Statut.INVALIDE
    assert Remise.objects.get().statut == Remise.Statut.ANNULEE
    trace = AuditLog.objects.filter(action=AuditLog.Action.REFERRAL_ADMIN).get()
    assert trace.actor_user == admin
    assert trace.metadata["geste"] == "invalidation"


@pytest.mark.django_db
def test_annuler_une_remise_deja_utilisee_est_refuse(salon_a):
    remise = remise_pour(salon_a.tenant)
    Remise.objects.filter(pk=remise.pk).update(statut=Remise.Statut.UTILISEE)
    remise.refresh_from_db()

    with pytest.raises(ValueError):
        services.annuler_remise(remise, _admin(), "Erreur de saisie constatée.")


# ---------------------------------------------------------------------------
# Acces aux ecrans
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_le_proprietaire_voit_son_code_ses_filleuls_et_ses_remises(api_client, salon_a):
    parrainage = filleul_de(services.code_du_salon(salon_a.tenant), nom="Salon Filleul")
    services.rendre_admissible(parrainage.pk)
    api_client.force_login(salon_a.owner)

    donnees = api_client.get("/api/v1/parrainage").json()

    assert donnees["code"] == services.code_du_salon(salon_a.tenant).code
    assert donnees["lien"].endswith(f"/inscription?parrain={donnees['code']}")
    # Du filleul : nom public, statut, dates. Rien d'autre.
    assert donnees["filleuls"] == [
        {
            "nom": "Salon Filleul",
            "statut": "admissible",
            "date": donnees["filleuls"][0]["date"],
            "admissible_le": donnees["filleuls"][0]["admissible_le"],
        }
    ]
    assert donnees["resume"]["pourcentage_prochain_paiement"] == "10"


@pytest.mark.django_db
def test_un_membre_non_proprietaire_ne_voit_pas_le_parrainage(api_client, salon_a):
    employee = UserFactory()
    MembershipFactory(tenant=salon_a.tenant, user=employee, role="staff")
    api_client.force_login(employee)

    assert api_client.get("/api/v1/parrainage").status_code == 403


@pytest.mark.django_db
def test_un_salon_ne_voit_pas_les_filleuls_d_un_autre(api_client, salon_a, salon_b):
    filleul_de(services.code_du_salon(salon_b.tenant), nom="Filleul de B")
    api_client.force_login(salon_a.owner)

    assert api_client.get("/api/v1/parrainage").json()["filleuls"] == []


@pytest.mark.django_db
def test_une_cliente_voit_son_code(api_client, salon_a):
    from conftest import salon_host

    cliente = UserFactory()
    ClientProfile.objects.create(user=cliente)
    api_client.force_login(cliente)

    reponse = api_client.get(
        "/api/v1/public/client/parrainage", headers={"Host": salon_host("blondrose")}
    )

    assert reponse.status_code == 200, reponse.content
    assert reponse.json()["code"] == services.code_de_l_utilisateur(cliente).code
    assert reponse.json()["possede_un_salon"] is False


@pytest.mark.django_db
def test_verifier_un_code_ne_revele_pas_le_nom_d_une_cliente(api_client, salon_a):
    cliente = UserFactory(display_name="Awa Diallo")
    code_cliente = services.code_de_l_utilisateur(cliente)
    code_salon = services.code_du_salon(salon_a.tenant)

    salon = api_client.get(f"/api/v1/account/parrainage/{code_salon.code}").json()
    personne = api_client.get(f"/api/v1/account/parrainage/{code_cliente.code}").json()
    inconnu = api_client.get("/api/v1/account/parrainage/ZZZZZZZZZZ").json()

    assert salon["valide"] is True and salon["salon"] == "Blond Rose"
    assert personne["valide"] is True and "Awa" not in str(personne)
    assert inconnu == {"valide": False}


@pytest.mark.django_db
def test_parrainage_coupe_par_l_interrupteur(api_client, salon_a, settings):
    settings.PARRAINAGE_ACTIF = False
    remise_pour(salon_a.tenant)
    api_client.force_login(salon_a.owner)

    assert api_client.get("/api/v1/parrainage").json() == {"actif": False}
    assert services.utilisables(salon_a.tenant.id, salon_a.owner) == []


@ADMIN
def test_une_seule_demande_en_attente_donc_pas_de_double_usage(salon_a, moyens):
    abonnement_de(salon_a)
    remise_pour(salon_a.tenant)
    declarer(salon_a, moyens["momo"])

    with pytest.raises(PaiementRefuse):
        declarer(salon_a, moyens["momo"], reference="REF-PARR-2")

    assert Remise.objects.filter(statut=Remise.Statut.RESERVEE).count() == 1
    assert SubscriptionPaymentRequest.all_tenants.using("admin").count() == 1


# ---------------------------------------------------------------------------
# Administration plateforme
# ---------------------------------------------------------------------------

MOT_DE_PASSE_ADMIN = "motdepasse-solide"


@pytest.fixture
def admin_client(client):
    UserFactory(
        email="supervision@example.com",
        password=MOT_DE_PASSE_ADMIN,
        is_staff=True,
        is_superuser=True,
        is_platform_admin=True,
    )
    client.login(username="supervision@example.com", password=MOT_DE_PASSE_ADMIN)
    return client


@ADMIN
@pytest.mark.parametrize(
    "route",
    [
        "admin:parrainage_codeparrainage_changelist",
        "admin:parrainage_parrainage_changelist",
        "admin:parrainage_remise_changelist",
    ],
)
def test_les_ecrans_du_parrainage_s_ouvrent_avec_des_donnees(admin_client, salon_a, route):
    parrainage = filleul_de(services.code_du_salon(salon_a.tenant), nom="Salon Filleul")
    services.rendre_admissible(parrainage.pk)

    reponse = admin_client.get(reverse(route))

    assert reponse.status_code == 200


@ADMIN
def test_la_fiche_d_un_parrainage_se_lit_sans_se_modifier(admin_client, salon_a):
    parrainage = filleul_de(services.code_du_salon(salon_a.tenant))
    services.rendre_admissible(parrainage.pk)

    reponse = admin_client.get(reverse("admin:parrainage_parrainage_change", args=[parrainage.pk]))

    assert reponse.status_code == 200
    assert 'name="_save"' not in reponse.content.decode()


@ADMIN
def test_invalider_depuis_l_admin_exige_un_motif(admin_client, salon_a):
    parrainage = filleul_de(services.code_du_salon(salon_a.tenant))
    services.rendre_admissible(parrainage.pk)
    url = reverse("admin:parrainage_parrainage_changelist")
    base = {"action": "action_invalider", helpers.ACTION_CHECKBOX_NAME: [str(parrainage.pk)]}

    # Premier passage : la page qui demande le motif, rien ne change.
    page = admin_client.post(url, base)
    assert page.status_code == 200
    assert "Motif" in page.content.decode()
    # Motif trop court : refuse, rien ne change.
    admin_client.post(url, {**base, "confirmer": "1", "motif": "court"})
    parrainage.refresh_from_db()
    assert parrainage.statut == Parrainage.Statut.ADMISSIBLE

    admin_client.post(url, {**base, "confirmer": "1", "motif": "Deux salons de la même gérante."})

    parrainage.refresh_from_db()
    assert parrainage.statut == Parrainage.Statut.INVALIDE
    assert Remise.objects.get().statut == Remise.Statut.ANNULEE
    assert AuditLog.objects.filter(action=AuditLog.Action.REFERRAL_ADMIN).count() == 1
