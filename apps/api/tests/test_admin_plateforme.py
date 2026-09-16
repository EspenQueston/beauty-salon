"""L'administration plateforme, et ce qu'elle laissait dans le noir.

---------------------------------------------------------------------------
Ce que ces tests protègent
---------------------------------------------------------------------------

Quatorze modèles métier n'avaient aucun écran. Trois applications entières
— `payments`, `store`, `clients` — étaient absentes du menu : tout ce que le
produit a gagné ces dernières semaines, la boutique, les preuves de
versement, les comptes clientes, était invisible depuis la supervision. Une
cliente qui écrivait « supprimez mon compte » était littéralement
introuvable.

Il en reste quatre, et ce sont des choix : une option de prestation, un
besoin de ressource, une compétence, un article proposé ne veulent rien dire
seuls. Ils vivent en `inline` sur la fiche de leur parent. Le dernier test du
fichier tient cette liste, et échoue dès qu'un modèle arrive sans écran ni
décision.

Deux familles d'assertions, et la seconde est la plus importante :

  1. **Chaque écran s'ouvre.** Une colonne calculée qui explose sur une
     valeur nulle ne se voit qu'à l'affichage : `manage.py check` la laisse
     passer. Un GET sur chaque liste et sur chaque fiche est le seul filet.

  2. **Rien n'est modifiable, et aucune capture ne fuit.** C'est la règle
     explicite de ces écrans : un acompte porte la comptabilité d'un salon,
     et une preuve de versement porte le solde bancaire d'une cliente.
"""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.clients.models import ClientProfile, ClientSalonLink
from apps.media.models import MediaAsset
from apps.payments.models import DepositProof, PaymentChannel
from apps.store.models import Product, Requirement, RequirementProduct
from conftest import as_tenant
from tests.factories import UserFactory
from tests.test_dashboard_api import make_booking

PASSWORD = "motdepasse-solide"

pytestmark = pytest.mark.django_db(databases=["default", "admin"], transaction=True)


@pytest.fixture
def admin_client(client):
    UserFactory(
        email="supervision@example.com",
        password=PASSWORD,
        is_staff=True,
        is_superuser=True,
        is_platform_admin=True,
    )
    client.login(username="supervision@example.com", password=PASSWORD)
    return client


# ---------------------------------------------------------------------------
# Chaque écran s'ouvre
# ---------------------------------------------------------------------------

ECRANS = [
    "admin:payments_paymentchannel_changelist",
    "admin:payments_depositproof_changelist",
    "admin:store_product_changelist",
    "admin:store_requirement_changelist",
    "admin:clients_clientprofile_changelist",
]


@pytest.mark.parametrize("route", ECRANS)
def test_chaque_liste_s_affiche(admin_client, route):
    reponse = admin_client.get(reverse(route))

    assert reponse.status_code == 200


def test_les_listes_tiennent_avec_des_donnees_reelles(admin_client, salon_a):
    """Une colonne calculée n'échoue jamais sur une liste vide.

    C'est sur la première ligne réelle — un stock nul, une preuve sans
    capture, un compte sans salon favori — qu'elle explose.
    """
    with as_tenant(salon_a.tenant):
        PaymentChannel.objects.create(
            tenant=salon_a.tenant, kind=PaymentChannel.Kind.WECHAT, active=True
        )
        Product.objects.create(
            tenant=salon_a.tenant, name="Mèches", price="12000", stock=0
        )
        Product.objects.create(
            tenant=salon_a.tenant, name="Shampooing", price="3000", stock=None
        )
        exigence = Requirement.objects.create(
            tenant=salon_a.tenant, service=salon_a.service, label="3 paquets"
        )
        RequirementProduct.objects.create(
            tenant=salon_a.tenant,
            requirement=exigence,
            product=Product.objects.first(),
        )
        DepositProof.objects.create(
            tenant=salon_a.tenant,
            booking=make_booking(salon_a),
            channel=PaymentChannel.Kind.WECHAT,
        )

    ClientProfile.objects.create(user=UserFactory())

    for route in ECRANS:
        reponse = admin_client.get(reverse(route))
        assert reponse.status_code == 200, route


def test_la_fiche_d_une_preuve_s_ouvre(admin_client, salon_a):
    with as_tenant(salon_a.tenant):
        preuve = DepositProof.objects.create(
            tenant=salon_a.tenant,
            booking=make_booking(salon_a),
            channel=PaymentChannel.Kind.ALIPAY,
            reference="4200002145",
        )

    reponse = admin_client.get(
        reverse("admin:payments_depositproof_change", args=[preuve.id])
    )

    assert reponse.status_code == 200
    contenu = reponse.content.decode()
    assert "4200002145" in contenu


def test_la_fiche_d_un_compte_cliente_s_ouvre(admin_client, salon_a):
    """Et elle montre les salons rattachés : c'est la question qui précède
    toujours une demande de suppression."""
    utilisateur = UserFactory(email="cliente@exemple.test")
    ClientProfile.objects.create(user=utilisateur)
    ClientSalonLink.objects.create(
        user=utilisateur, tenant=salon_a.tenant, customer_id=salon_a.customer.id
    )

    reponse = admin_client.get(
        reverse("admin:clients_clientprofile_change", args=[utilisateur.pk])
    )

    assert reponse.status_code == 200
    assert salon_a.tenant.name in reponse.content.decode()


# ---------------------------------------------------------------------------
# Rien n'est modifiable
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "modele",
    ["payments_paymentchannel", "payments_depositproof", "store_product", "store_requirement"],
)
def test_aucun_ecran_n_offre_la_creation(admin_client, modele):
    """Créer un moyen de paiement ou un article depuis ici le ferait
    apparaître sur le mini-site d'un salon qui n'a rien demandé."""
    reponse = admin_client.get(reverse(f"admin:{modele}_add"))

    assert reponse.status_code == 403


def test_une_preuve_ne_se_modifie_pas(admin_client, salon_a):
    """Un acompte porte le chiffre d'affaires d'un salon. Une correction
    faite ici passerait sous ses yeux sans trace dans son agenda."""
    with as_tenant(salon_a.tenant):
        preuve = DepositProof.objects.create(
            tenant=salon_a.tenant,
            booking=make_booking(salon_a),
            status=DepositProof.Status.SUBMITTED,
        )

    admin_client.post(
        reverse("admin:payments_depositproof_change", args=[preuve.id]),
        {"status": DepositProof.Status.ACCEPTED},
    )

    with as_tenant(salon_a.tenant):
        preuve.refresh_from_db()
    assert preuve.status == DepositProof.Status.SUBMITTED


def test_un_compte_cliente_ne_se_cree_pas_ici(admin_client):
    """Un compte naît sur le mini-site d'un salon. Le forcer ici donnerait
    un compte sans mot de passe choisi et sans salon d'origine."""
    reponse = admin_client.get(reverse("admin:clients_clientprofile_add"))

    assert reponse.status_code == 403


def test_un_compte_cliente_se_supprime(admin_client):
    """C'est le seul geste d'écriture de ces écrans, et la raison d'être de
    la page : une cliente qui demande la suppression de son compte ne
    s'adresse à aucun salon, elle s'adresse à la plateforme."""
    utilisateur = UserFactory(email="a-supprimer@exemple.test")
    ClientProfile.objects.create(user=utilisateur)

    reponse = admin_client.post(
        reverse("admin:clients_clientprofile_delete", args=[utilisateur.pk]),
        {"post": "yes"},
    )

    assert reponse.status_code in (200, 302)
    assert not ClientProfile.objects.filter(user=utilisateur).exists()


# ---------------------------------------------------------------------------
# Aucune capture de paiement ne fuit
# ---------------------------------------------------------------------------


def test_la_fiche_d_une_preuve_ne_montre_jamais_l_image(admin_client, salon_a):
    """La règle explicite de cet écran.

    Une capture de paiement porte le nom de la cliente, l'heure du virement
    et parfois le solde de son compte. Le support a besoin de savoir qu'une
    capture existe — jamais de ce qu'on y voit.
    """
    from django.core.files.base import ContentFile

    with as_tenant(salon_a.tenant):
        capture = MediaAsset.objects.create(
            tenant=salon_a.tenant,
            file=ContentFile(b"pas-vraiment-une-image", name="capture.png"),
            content_type="image/png",
            kind=MediaAsset.Kind.PROOF,
            visibility=MediaAsset.Visibility.PRIVATE,
        )
        preuve = DepositProof.objects.create(
            tenant=salon_a.tenant, booking=make_booking(salon_a), image=capture
        )

    contenu = admin_client.get(
        reverse("admin:payments_depositproof_change", args=[preuve.id])
    ).content.decode()

    # Ni le chemin du fichier, ni une balise qui l'afficherait.
    assert capture.file.name not in contenu
    assert "/media/prive/" not in contenu
    assert f"/api/v1/media/{capture.id}/fichier" not in contenu
    # Mais l'existence de la capture, elle, est dite.
    assert "capture jointe" in contenu


def test_une_preuve_sans_capture_le_dit(admin_client, salon_a):
    """« Aucune capture jointe » est une réponse au support ; une case vide
    ressemble à un défaut de chargement."""
    with as_tenant(salon_a.tenant):
        preuve = DepositProof.objects.create(
            tenant=salon_a.tenant, booking=make_booking(salon_a)
        )

    contenu = admin_client.get(
        reverse("admin:payments_depositproof_change", args=[preuve.id])
    ).content.decode()

    assert "aucune capture jointe" in contenu


# ---------------------------------------------------------------------------
# La colonne qui fait l'intérêt de l'écran
# ---------------------------------------------------------------------------


def test_une_preuve_en_attente_affiche_depuis_combien_de_temps(admin_client, salon_a):
    """Une preuve envoyée il y a vingt minutes est une file normale ; la
    même trois jours plus tard est une cliente sans réponse et un créneau
    qui va se libérer tout seul."""
    with as_tenant(salon_a.tenant):
        preuve = DepositProof.objects.create(
            tenant=salon_a.tenant, booking=make_booking(salon_a)
        )
        DepositProof.objects.filter(id=preuve.id).update(
            submitted_at=timezone.now() - timedelta(days=3)
        )

    contenu = admin_client.get(
        reverse("admin:payments_depositproof_changelist")
    ).content.decode()

    assert "attend depuis 3 j" in contenu


def test_une_preuve_traitee_affiche_le_temps_de_reponse(admin_client, salon_a):
    with as_tenant(salon_a.tenant):
        preuve = DepositProof.objects.create(
            tenant=salon_a.tenant,
            booking=make_booking(salon_a),
            status=DepositProof.Status.ACCEPTED,
        )
        DepositProof.objects.filter(id=preuve.id).update(
            submitted_at=timezone.now() - timedelta(hours=5),
            reviewed_at=timezone.now() - timedelta(hours=3),
        )

    contenu = admin_client.get(
        reverse("admin:payments_depositproof_changelist")
    ).content.decode()

    assert "répondu en 2 h" in contenu


def test_un_moyen_de_paiement_sans_qr_dit_pourquoi_il_est_inutilisable(
    admin_client, salon_a
):
    """« Actif » ne suffit pas : un moyen actif sans QR téléversé est tout
    aussi inutilisable, et c'est le cas le plus fréquent."""
    with as_tenant(salon_a.tenant):
        PaymentChannel.objects.create(
            tenant=salon_a.tenant, kind=PaymentChannel.Kind.WECHAT, active=True
        )

    contenu = admin_client.get(
        reverse("admin:payments_paymentchannel_changelist")
    ).content.decode()

    assert "aucun QR téléversé" in contenu


# ---------------------------------------------------------------------------
# Le filet qui empêche le prochain module d'arriver invisible
# ---------------------------------------------------------------------------

# Modèles volontairement absents de l'administration, et pourquoi.
#
# Ce ne sont pas des oublis : ce sont les lots B et C du plan, et les tables
# de liaison qui n'ont de sens qu'en `inline` sur leur parent. Retirer une
# ligne d'ici est la façon de dire « celui-là, maintenant, doit avoir son
# écran ».
ABSENCES_ASSUMEES = {
    # Ce qui se lit sur la fiche de son parent, jamais seul.
    "catalog.ServiceOption",  # inline sur Service
    "catalog.ServiceResource",  # inline sur Service
    "staff.StaffService",  # inline sur StaffMember
    "store.RequirementProduct",  # inline sur Requirement
}


def test_aucun_modele_de_salon_n_arrive_invisible():
    """Ces trois applications ont existé des semaines sans écran.

    Personne ne l'a vu, parce que rien ne le signalait. Ce test est le
    pendant de `test_rls.py` : celui-là vérifie qu'un nouveau modèle a sa
    politique d'isolation, celui-ci qu'il a sa fenêtre de supervision — ou
    que son absence a été décidée.
    """
    from django.apps import apps as registre
    from django.contrib import admin

    from apps.common.models import TenantOwnedModel

    enregistres = set(admin.site._registry)
    oublies = sorted(
        f"{m._meta.app_label}.{m.__name__}"
        for m in registre.get_models()
        if issubclass(m, TenantOwnedModel)
        and m not in enregistres
        and f"{m._meta.app_label}.{m.__name__}" not in ABSENCES_ASSUMEES
    )

    assert not oublies, (
        "Ces modèles de salon n'ont aucun écran d'administration. Ajoutez-les, "
        f"ou inscrivez-les dans ABSENCES_ASSUMEES avec la raison : {oublies}"
    )


# ---------------------------------------------------------------------------
# Lots B et C : ce qui a suivi
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "route",
    [
        "admin:accounts_invitation_changelist",
        "admin:scheduling_waitlistentry_changelist",
        "admin:catalog_resource_changelist",
    ],
)
def test_les_ecrans_du_lot_b_s_affichent(admin_client, route):
    reponse = admin_client.get(reverse(route))

    assert reponse.status_code == 200


def test_une_invitation_expiree_dit_quoi_faire(admin_client, salon_a):
    """« J'ai invité ma collègue, elle n'a rien reçu. » Trois causes
    possibles ; celle-ci est la plus fréquente, et la réponse tient en
    trois mots — le salon doit réinviter."""
    from apps.accounts.models import Invitation

    with as_tenant(salon_a.tenant):
        Invitation.objects.create(
            tenant=salon_a.tenant,
            email="collegue@exemple.test",
            role="staff",
            token_hash="a" * 64,
            expires_at=timezone.now() - timedelta(days=1),
        )

    contenu = admin_client.get(
        reverse("admin:accounts_invitation_changelist")
    ).content.decode()

    assert "le salon doit réinviter" in contenu


def test_l_empreinte_du_jeton_d_invitation_n_est_jamais_affichee(
    admin_client, salon_a
):
    """Seule l'empreinte SHA-256 est stockée — c'est ce qui fait qu'une fuite
    de la base ne donne accès à aucun compte. L'afficher annulerait le
    bénéfice."""
    from apps.accounts.models import Invitation

    empreinte = "b" * 64
    with as_tenant(salon_a.tenant):
        invitation = Invitation.objects.create(
            tenant=salon_a.tenant,
            email="collegue@exemple.test",
            role="staff",
            token_hash=empreinte,
            expires_at=timezone.now() + timedelta(days=3),
        )

    for route in (
        reverse("admin:accounts_invitation_changelist"),
        reverse("admin:accounts_invitation_change", args=[invitation.id]),
    ):
        assert empreinte not in admin_client.get(route).content.decode(), route


def test_une_attente_longue_se_voit(admin_client, salon_a):
    """Une inscription de la semaine est une file normale ; la même vieille
    d'un mois est une cliente partie ailleurs."""
    from apps.scheduling.waitlist import WaitlistEntry

    with as_tenant(salon_a.tenant):
        entree = WaitlistEntry.objects.create(
            tenant=salon_a.tenant,
            service=salon_a.service,
            full_name="Awa Diallo",
            phone="+242066112233",
            preferred_from=timezone.localdate(),
            preferred_to=timezone.localdate() + timedelta(days=30),
        )
        WaitlistEntry.objects.filter(id=entree.id).update(
            created_at=timezone.now() - timedelta(days=30)
        )

    contenu = admin_client.get(
        reverse("admin:scheduling_waitlistentry_changelist")
    ).content.decode()

    assert "30 jours sans réponse" in contenu


def test_la_fiche_d_une_prestation_porte_ses_options_et_ses_ressources(
    admin_client, salon_a
):
    """Lot C : une option et un besoin de ressource ne veulent rien dire
    seuls. Ils se lisent sur la fiche de la prestation, là où le salon les a
    saisis."""
    from apps.catalog.models import Resource, ServiceOption, ServiceResource

    with as_tenant(salon_a.tenant):
        ServiceOption.objects.create(
            tenant=salon_a.tenant,
            service=salon_a.service,
            name="Shampooing traitant",
            price_delta="2000",
        )
        bac = Resource.objects.create(tenant=salon_a.tenant, name="Bac 1", capacity=1)
        ServiceResource.objects.create(
            tenant=salon_a.tenant, service=salon_a.service, resource=bac
        )

    contenu = admin_client.get(
        reverse("admin:catalog_service_change", args=[salon_a.service.id])
    ).content.decode()

    assert "Shampooing traitant" in contenu
    assert "Bac 1" in contenu


def test_une_ressource_a_capacite_un_le_signale(admin_client, salon_a):
    """Une capacité à 1 posée par mégarde explique à elle seule un agenda qui
    paraît complet."""
    from apps.catalog.models import Resource

    with as_tenant(salon_a.tenant):
        Resource.objects.create(tenant=salon_a.tenant, name="Bac unique", capacity=1)

    contenu = admin_client.get(
        reverse("admin:catalog_resource_changelist")
    ).content.decode()

    assert "une seule cliente à la fois" in contenu
