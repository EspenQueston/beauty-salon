"""Suppression definitive d'un salon ou d'un compte, et changement d'offre.

Ce que ces tests tiennent :

  - un salon supprime ne laisse rien derriere lui (tables, fichiers,
    adresses), et son voisin n'est pas touche ;
  - rien ne part sans le bon identifiant, le bon mot de passe, un motif ;
  - un salon en ligne, un compte d'administration, le dernier proprietaire
    d'un salon et son propre compte sont refuses ;
  - la trace d'audit survit a ce qu'elle decrit ;
  - « Changer l'offre » donne vraiment les droits Pro.
"""

import pathlib
from datetime import timedelta

import pytest
from django.core.files.base import ContentFile
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Membership, User
from apps.audit.models import AuditLog
from apps.billing import services
from apps.billing.droits import fonctions_du_salon, groupe_effectif
from apps.billing.models import Subscription
from apps.billing.services import PaiementRefuse
from apps.clients.models import ClientSalonLink
from apps.common.suppression import SuppressionRefusee, supprimer_compte, supprimer_salon
from apps.customers.models import Customer
from apps.domains.models import Domain
from apps.media.models import MediaAsset
from apps.scheduling.models import Booking
from apps.tenants.models import Tenant
from conftest import as_tenant
from tests.factories import MembershipFactory, UserFactory
from tests.test_abonnements import abonnement_de, medias_temporaires, moyens, offres
from tests.test_admin_suppression import un_rendez_vous
from tests.test_offres_pro import declarer_et_approuver, pro

FIXTURES_PARTAGEES = (medias_temporaires, moyens, offres, pro)
PASSWORD = "motdepasse-solide"

pytestmark = pytest.mark.django_db(databases=["default", "admin"], transaction=True)


@pytest.fixture(autouse=True)
def _offres(offres):
    """Les tests transactionnels vident les offres creees par migration."""
    return offres


@pytest.fixture
def admin_plateforme():
    return UserFactory(
        email="supervision@example.com",
        password=PASSWORD,
        is_staff=True,
        is_superuser=True,
        is_platform_admin=True,
    )


@pytest.fixture
def admin_client(client, admin_plateforme):
    client.force_login(admin_plateforme)
    return client


def suspendu(salon):
    Tenant.objects.filter(pk=salon.tenant.pk).update(status=Tenant.Status.SUSPENDED)
    salon.tenant.refresh_from_db()
    return salon.tenant


def salon_rempli(salon, moyens):
    """Un salon avec de tout : rendez-vous et recette, fichier, paiement, cliente."""
    abonnement_de(salon)
    declarer_et_approuver(salon, moyens["momo"], "monthly")
    un_rendez_vous(salon)
    with as_tenant(salon.tenant):
        media = MediaAsset(tenant=salon.tenant, kind=MediaAsset.Kind.GALLERY)
        media.file.save("photo.txt", ContentFile(b"une photo"), save=True)
        chemin = pathlib.Path(media.file.path)
    cliente = UserFactory(email="cliente@example.com")
    ClientSalonLink.objects.create(user=cliente, tenant=salon.tenant, customer_id=salon.customer.pk)
    return chemin, cliente


def rien_ne_reste(tenant_id) -> bool:
    from apps.common.suppression import _modeles_du_salon

    return all(
        not m.all_tenants.using("admin").filter(tenant_id=tenant_id).exists()
        for m in _modeles_du_salon()
    )


# ---------------------------------------------------------------------------
# Le salon
# ---------------------------------------------------------------------------


def test_un_salon_supprime_ne_laisse_rien_et_epargne_son_voisin(
    salon_a, salon_b, moyens, admin_plateforme
):
    chemin, cliente = salon_rempli(salon_a, moyens)
    un_rendez_vous(salon_b)
    tenant_id, proprietaire = salon_a.tenant.pk, salon_a.owner.pk

    supprimer_salon(
        suspendu(salon_a),
        administrateur=admin_plateforme,
        motif="Demande de suppression du salon",
        avec_comptes=True,
    )

    assert not Tenant.objects.filter(pk=tenant_id).exists()
    assert rien_ne_reste(tenant_id)
    assert not Domain.objects.using("admin").filter(tenant_id=tenant_id).exists()
    assert not Membership.objects.using("admin").filter(tenant_id=tenant_id).exists()
    assert not chemin.exists(), "le fichier doit quitter le disque"
    # Les comptes qui n'etaient qu'a ce salon sont partis, sur demande.
    assert not User.objects.filter(pk__in=[proprietaire, cliente.pk]).exists()
    assert User.objects.filter(pk=admin_plateforme.pk).exists()
    # Le voisin est intact.
    with as_tenant(salon_b.tenant):
        assert Booking.objects.count() == 1
        assert Customer.objects.exists()
    # La trace survit, sans lien vers le salon disparu.
    trace = AuditLog.objects.get(action=AuditLog.Action.TENANT_DELETED)
    assert trace.resource_id == str(tenant_id) and trace.tenant_id is None
    assert trace.metadata["identifiant"] == "blondrose"
    assert trace.actor_user_id == admin_plateforme.pk


def test_sans_la_case_les_comptes_restent(salon_a, moyens, admin_plateforme):
    _, cliente = salon_rempli(salon_a, moyens)

    supprimer_salon(
        suspendu(salon_a),
        administrateur=admin_plateforme,
        motif="Salon de test à retirer",
        avec_comptes=False,
    )

    assert User.objects.filter(pk__in=[salon_a.owner.pk, cliente.pk]).count() == 2


def test_un_compte_qui_a_un_autre_salon_n_est_jamais_efface(salon_a, salon_b, admin_plateforme):
    abonnement_de(salon_a)
    MembershipFactory(tenant=salon_b.tenant, user=salon_a.owner, role=Membership.Role.MANAGER)

    supprimer_salon(
        suspendu(salon_a),
        administrateur=admin_plateforme,
        motif="Salon de test à retirer",
        avec_comptes=True,
    )

    assert User.objects.filter(pk=salon_a.owner.pk).exists()


def test_un_salon_en_ligne_ne_se_supprime_pas(salon_a, admin_plateforme):
    with pytest.raises(SuppressionRefusee, match="en ligne"):
        supprimer_salon(
            salon_a.tenant,
            administrateur=admin_plateforme,
            motif="Motif assez long ici",
            avec_comptes=False,
        )
    assert Tenant.objects.filter(pk=salon_a.tenant.pk).exists()


def test_l_ecran_exige_l_identifiant_le_mot_de_passe_et_un_motif(admin_client, salon_a):
    abonnement_de(salon_a)
    tenant = suspendu(salon_a)
    url = reverse("admin:tenants_tenant_suppression", args=[tenant.pk])

    page = admin_client.get(url)
    assert page.status_code == 200 and "blondrose" in page.content.decode()

    for donnees in (
        {"confirmation": "autre", "motif": "Motif suffisant", "mot_de_passe": PASSWORD},
        {"confirmation": "blondrose", "motif": "Motif suffisant", "mot_de_passe": "faux"},
        {"confirmation": "blondrose", "motif": "court", "mot_de_passe": PASSWORD},
    ):
        assert admin_client.post(url, donnees).status_code == 200
        assert Tenant.objects.filter(pk=tenant.pk).exists(), donnees

    fin = admin_client.post(
        url, {"confirmation": "blondrose", "motif": "Motif suffisant", "mot_de_passe": PASSWORD}
    )
    assert fin.status_code == 302
    assert not Tenant.objects.filter(pk=tenant.pk).exists()


def test_cinq_essais_au_plus(admin_client, salon_a):
    abonnement_de(salon_a)
    tenant = suspendu(salon_a)
    url = reverse("admin:tenants_tenant_suppression", args=[tenant.pk])
    mauvais = {"confirmation": "blondrose", "motif": "Motif suffisant", "mot_de_passe": "faux"}
    for _ in range(5):
        admin_client.post(url, mauvais)

    bon = {"confirmation": "blondrose", "motif": "Motif suffisant", "mot_de_passe": PASSWORD}
    reponse = admin_client.post(url, bon)

    assert "Trop d&#x27;essais" in reponse.content.decode()
    assert Tenant.objects.filter(pk=tenant.pk).exists()


def test_reserve_aux_administrateurs_plateforme(client, salon_a):
    simple = UserFactory(email="staff@example.com", password=PASSWORD, is_staff=True)
    client.force_login(simple)
    url = reverse("admin:tenants_tenant_suppression", args=[salon_a.tenant.pk])

    assert client.get(url).status_code in (302, 403)


def test_le_bouton_supprimer_de_django_est_retire(admin_client, salon_a):
    tenant_url = reverse("admin:tenants_tenant_delete", args=[salon_a.tenant.pk])
    user_url = reverse("admin:accounts_user_delete", args=[salon_a.owner.pk])

    assert admin_client.post(tenant_url, {"post": "yes"}).status_code == 403
    assert admin_client.post(user_url, {"post": "yes"}).status_code == 403
    assert Tenant.objects.filter(pk=salon_a.tenant.pk).exists()


# ---------------------------------------------------------------------------
# Le compte
# ---------------------------------------------------------------------------


def test_le_dernier_proprietaire_ne_se_supprime_pas(salon_a, admin_plateforme):
    with pytest.raises(SuppressionRefusee, match="Seul propriétaire"):
        supprimer_compte(salon_a.owner, administrateur=admin_plateforme, motif="Demande RGPD reçue")


def test_ni_un_administrateur_ni_soi_meme(admin_plateforme):
    autre_admin = UserFactory(email="autre@example.com", is_staff=True, is_superuser=True)
    with pytest.raises(SuppressionRefusee, match="administration"):
        supprimer_compte(autre_admin, administrateur=admin_plateforme, motif="Motif assez long")
    with pytest.raises(SuppressionRefusee, match="propre compte"):
        supprimer_compte(admin_plateforme, administrateur=admin_plateforme, motif="Motif long")


def test_un_compte_part_mais_ce_qu_il_a_fait_reste(salon_a, admin_plateforme):
    gerante = UserFactory(email="gerante@example.com")
    MembershipFactory(tenant=salon_a.tenant, user=gerante, role=Membership.Role.MANAGER)
    booking = un_rendez_vous(salon_a)

    supprimer_compte(gerante, administrateur=admin_plateforme, motif="Demande de suppression")

    assert not User.objects.filter(pk=gerante.pk).exists()
    with as_tenant(salon_a.tenant):
        assert Booking.objects.filter(pk=booking.pk).exists()
    trace = AuditLog.objects.get(action=AuditLog.Action.USER_DELETED)
    assert trace.metadata["compte"] == "g***@example.com"
    assert "gerante" not in str(trace.metadata)


def test_l_ecran_du_compte_montre_ce_qui_bloque(admin_client, salon_a):
    page = admin_client.get(reverse("admin:accounts_user_suppression", args=[salon_a.owner.pk]))

    assert page.status_code == 200
    assert "Seul propriétaire" in page.content.decode()


# ---------------------------------------------------------------------------
# Changer l'offre
# ---------------------------------------------------------------------------


def test_passer_a_pro_depuis_l_administration_ouvre_les_droits(salon_a, pro, admin_plateforme):
    abonnement_de(salon_a)  # essai : Standard
    with as_tenant(salon_a.tenant):
        assert fonctions_du_salon(salon_a.tenant.id)["platform_assistant"] is False

    services.changer_d_offre(
        salon_a.tenant.id,
        administrateur=admin_plateforme,
        code="pro_monthly",
        note="Geste commercial",
    )

    with as_tenant(salon_a.tenant):
        abonnement = Subscription.objects.select_related("plan").get()
        assert groupe_effectif(abonnement) == "pro"
        assert fonctions_du_salon(salon_a.tenant.id)["platform_assistant"] is True
        assert abonnement.status == Subscription.Status.ACTIVE


def test_changer_d_offre_peut_offrir_des_mois(salon_a, pro, admin_plateforme):
    fin = timezone.now() + timedelta(days=10)
    abonnement_de(salon_a, fin=fin)

    services.changer_d_offre(
        salon_a.tenant.id,
        administrateur=admin_plateforme,
        code="pro_yearly",
        mois=12,
        note="Partenariat",
    )

    with as_tenant(salon_a.tenant):
        abonnement = Subscription.objects.get()
    assert abonnement.current_period_end > fin + timedelta(days=360)


def test_changer_d_offre_exige_un_motif_et_refuse_un_salon_suspendu(salon_a, pro, admin_plateforme):
    abonnement_de(salon_a, statut=Subscription.Status.SUSPENDED)
    with pytest.raises(PaiementRefuse):
        services.changer_d_offre(
            salon_a.tenant.id, administrateur=admin_plateforme, code="pro_monthly", note=""
        )
    with pytest.raises(PaiementRefuse, match="suspendu"):
        services.changer_d_offre(
            salon_a.tenant.id, administrateur=admin_plateforme, code="pro_monthly", note="ok"
        )


def test_la_liste_des_salons_montre_l_offre_reelle(admin_client, salon_a, pro, admin_plateforme):
    abonnement_de(salon_a)
    liste = reverse("admin:tenants_tenant_changelist")
    assert "Essai" in admin_client.get(liste).content.decode()

    services.changer_d_offre(
        salon_a.tenant.id, administrateur=admin_plateforme, code="pro_monthly", note="Test admin"
    )
    page = admin_client.get(liste + "?offre=pro").content.decode()
    assert "Pro · Pro mensuel" in page and "blondrose" in page
    assert "blondrose" not in admin_client.get(liste + "?offre=standard").content.decode()
    fiche = admin_client.get(reverse("admin:tenants_tenant_change", args=[salon_a.tenant.pk]))
    assert "Changer l’offre" in fiche.content.decode()
    assert "Supprimer définitivement" in fiche.content.decode()
