"""Le QR de contact WeChat et l'identifiant, ensemble.

---------------------------------------------------------------------------
Pourquoi les deux, et pourquoi c'est la seule chose qui compte ici
---------------------------------------------------------------------------

WeChat ne se rejoint pas par une adresse. On ajoute quelqu'un en scannant
son QR, ou en tapant son identifiant dans la barre de recherche. Ce sont
deux gestes exclusifs :

  - le QR ne sert a rien a qui lit la page *dans* WeChat, sur le telephone
    qui devrait scanner — on ne scanne pas son propre ecran ;
  - l'identifiant ne sert a rien a qui regarde une affichette collee au mur
    du salon.

Le mini-site doit donc pouvoir montrer les deux. Ces tests verifient que
rien ne casse cette paire en chemin : que les deux champs sortent bien de
l'API publique, que la gerante peut les ecrire, que la reception ne le peut
pas, et qu'un salon ne voit jamais le QR d'un autre.

Le dernier point n'est pas une precaution de principe : `wechat_qr` est une
cle etrangere vers `MediaAsset`, une table portant une politique RLS. Une
relation qui traverse les salons est exactement ce que cette couche existe
pour rendre impossible.
"""

import pytest

from apps.accounts.models import Membership
from apps.media.models import MediaAsset
from apps.salons.models import SalonProfile
from conftest import as_tenant, salon_host
from tests.factories import MembershipFactory, UserFactory

PASSWORD = "motdepasse-solide"
PROFIL = "/api/v1/salon-profile"
PUBLIC = "/api/v1/public/salon"


def login(client, user):
    assert client.login(email=user.email, password=PASSWORD)
    return client


def qr_du_salon(salon) -> MediaAsset:
    with as_tenant(salon.tenant):
        return MediaAsset.objects.create(
            tenant=salon.tenant,
            file="tenants/x/media/y/qr-wechat.png",
            content_type="image/png",
            byte_size=64,
            kind=MediaAsset.Kind.WECHAT,
            alt_text="QR WeChat",
        )


def profil(salon) -> SalonProfile:
    with as_tenant(salon.tenant):
        fiche, _ = SalonProfile.objects.get_or_create(tenant=salon.tenant)
        return fiche


# ---------------------------------------------------------------------------
# Ce que voit une cliente
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_public_page_gets_the_id_and_the_qr_together(api_client, salon_a):
    """Les deux, dans la meme reponse.

    Le mini-site ne fait qu'un appel pour dessiner sa page. Si l'un des deux
    manquait, il faudrait choisir lequel afficher — et ce choix ne peut pas
    se faire correctement sans savoir sur quel appareil on lit.
    """
    code = qr_du_salon(salon_a)
    fiche = profil(salon_a)
    with as_tenant(salon_a.tenant):
        fiche.wechat_id = "salon-beaute-gz"
        fiche.wechat_qr = code
        fiche.save(update_fields=["wechat_id", "wechat_qr"])

    response = api_client.get(
        PUBLIC, headers={"Host": salon_host(salon_a.tenant.slug)}
    )

    assert response.status_code == 200, response.data
    assert response.data["wechat_id"] == "salon-beaute-gz"
    assert response.data["wechat_qr"] is not None
    assert response.data["wechat_qr"]["url"].endswith("qr-wechat.png")


@pytest.mark.django_db
def test_a_salon_without_wechat_says_so_plainly(api_client, salon_a):
    """Vide et `null`, pas une cle absente.

    Le mini-site teste la presence pour decider s'il affiche le bouton. Une
    cle manquante et une cle vide se distinguent mal en JavaScript, et la
    difference se paie en bouton affiche qui n'ouvre rien.
    """
    profil(salon_a)

    response = api_client.get(
        PUBLIC, headers={"Host": salon_host(salon_a.tenant.slug)}
    )

    assert response.status_code == 200
    assert response.data["wechat_id"] == ""
    assert response.data["wechat_qr"] is None


@pytest.mark.django_db
def test_the_wechat_qr_never_lands_in_the_gallery(api_client, salon_a):
    """Un code de contact n'est pas une realisation.

    Les deux sont des `MediaAsset` du meme salon. Sans genre distinct, le QR
    serait apparu entre deux photos de coiffures sur la page
    « Realisations » — ce qui est arrive par le passe avec les QR de
    paiement, et c'est pourquoi le genre existe.
    """
    qr_du_salon(salon_a)

    response = api_client.get(
        PUBLIC, headers={"Host": salon_host(salon_a.tenant.slug)}
    )

    assert response.status_code == 200
    assert response.data["gallery"] == []


# ---------------------------------------------------------------------------
# Ce qu'ecrit le salon
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_owner_writes_her_wechat_id(api_client, salon_a):
    login(api_client, salon_a.owner)

    response = api_client.patch(
        PROFIL, {"wechat_id": "byfaty-gz"}, format="json"
    )

    assert response.status_code == 200, response.data
    assert response.data["wechat_id"] == "byfaty-gz"


@pytest.mark.django_db
def test_the_owner_attaches_her_own_qr(api_client, salon_a):
    code = qr_du_salon(salon_a)
    login(api_client, salon_a.owner)

    response = api_client.patch(
        PROFIL, {"wechat_qr": str(code.id)}, format="json"
    )

    assert response.status_code == 200, response.data
    assert response.data["wechat_qr"] == code.id


@pytest.mark.django_db
def test_the_qr_can_be_detached_again(api_client, salon_a):
    """Retirer le code doit etre aussi simple que le poser.

    Un salon qui change de compte WeChat laisse sinon en ligne un QR qui
    ajoute un contact qu'il ne lit plus — pire qu'un bouton absent.
    """
    code = qr_du_salon(salon_a)
    fiche = profil(salon_a)
    with as_tenant(salon_a.tenant):
        fiche.wechat_qr = code
        fiche.save(update_fields=["wechat_qr"])

    login(api_client, salon_a.owner)
    response = api_client.patch(PROFIL, {"wechat_qr": None}, format="json")

    assert response.status_code == 200, response.data
    assert response.data["wechat_qr"] is None


@pytest.mark.django_db
def test_the_receptionist_cannot_change_it(api_client, salon_a):
    """La vitrine appartient a la gerance.

    Une reception qui peut changer le QR de contact peut rediriger les
    nouvelles clientes vers n'importe quel compte, sans laisser de trace
    visible sur la page.
    """
    hote = UserFactory()
    MembershipFactory(
        tenant=salon_a.tenant, user=hote, role=Membership.Role.RECEPTIONIST
    )
    login(api_client, hote)

    response = api_client.patch(
        PROFIL, {"wechat_id": "compte-pirate"}, format="json"
    )

    assert response.status_code == 403
    with as_tenant(salon_a.tenant):
        assert SalonProfile.objects.get(tenant=salon_a.tenant).wechat_id == ""


# ---------------------------------------------------------------------------
# La frontiere entre salons
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_salon_cannot_borrow_the_qr_of_another(api_client, salon_a, salon_b):
    """Le code du voisin n'existe pas, de ce cote de la cloison.

    Ce n'est pas la vue qui le refuse : c'est la politique RLS, qui rend la
    ligne invisible. Le serialiseur cherche une cle etrangere qu'il ne
    trouve pas, et repond une erreur de validation — jamais un 500, et
    jamais un succes.
    """
    code_voisin = qr_du_salon(salon_b)
    login(api_client, salon_a.owner)

    response = api_client.patch(
        PROFIL, {"wechat_qr": str(code_voisin.id)}, format="json"
    )

    assert response.status_code == 400, response.data
    # Le refus porte bien sur ce champ, et pas sur un autre : sans cette
    # ligne, le test passerait le jour ou la requete echouerait pour une
    # raison sans rapport.
    assert "wechat_qr" in str(response.data), response.data
    with as_tenant(salon_a.tenant):
        assert SalonProfile.objects.get(tenant=salon_a.tenant).wechat_qr_id is None


@pytest.mark.django_db
def test_one_salon_wechat_never_shows_on_another_site(api_client, salon_a, salon_b):
    code = qr_du_salon(salon_a)
    fiche = profil(salon_a)
    with as_tenant(salon_a.tenant):
        fiche.wechat_id = "chez-a"
        fiche.wechat_qr = code
        fiche.save(update_fields=["wechat_id", "wechat_qr"])
    profil(salon_b)

    response = api_client.get(
        PUBLIC, headers={"Host": salon_host(salon_b.tenant.slug)}
    )

    assert response.status_code == 200
    assert response.data["wechat_id"] == ""
    assert response.data["wechat_qr"] is None


# ---------------------------------------------------------------------------
# L'administration plateforme
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_platform_admin_says_what_is_missing():
    """Trois etats, pas deux.

    « Ce salon est-il joignable sur WeChat ? » se repond par oui ou non,
    mais les deux facons de repondre non demandent des corrections
    differentes : sans QR, il est injoignable depuis une affichette ; sans
    identifiant, il l'est depuis WeChat lui-meme. Une colonne binaire aurait
    cache celui des deux qu'il faut reparer.
    """
    from apps.salons.admin import SalonProfileAdmin

    fiche = SalonProfile(wechat_id="byfaty", wechat_qr=None)
    colonne = SalonProfileAdmin.wechat

    complet = SalonProfile(wechat_id="byfaty")
    complet.wechat_qr_id = "00000000-0000-0000-0000-000000000001"

    vide = SalonProfile()
    qr_seul = SalonProfile()
    qr_seul.wechat_qr_id = "00000000-0000-0000-0000-000000000002"

    assert "QR" in colonne(None, complet)
    assert "sans QR" in colonne(None, fiche)
    assert "sans identifiant" in colonne(None, qr_seul)
    assert "—" in colonne(None, vide)


# ---------------------------------------------------------------------------
# L'ecran de supervision s'ouvre vraiment
# ---------------------------------------------------------------------------
#
# Le test unitaire au-dessus verifie la colonne ; il ne rend pas la page. Or
# une methode d'affichage qui explose sur une valeur nulle ne se voit qu'au
# rendu - `manage.py check` la laisse passer, et c'est exactement le genre de
# panne qu'on decouvre en production, un vendredi.

ADMIN = pytest.mark.django_db(databases=["default", "admin"], transaction=True)


@pytest.fixture
def admin_client(client):
    UserFactory(
        email="supervision-wechat@example.com",
        password=PASSWORD,
        is_staff=True,
        is_superuser=True,
        is_platform_admin=True,
    )
    client.login(username="supervision-wechat@example.com", password=PASSWORD)
    return client


@ADMIN
def test_the_platform_screen_opens_with_and_without_a_qr(admin_client, salon_a):
    """Les deux etats, sur une vraie ligne.

    Sans QR, `apercu_wechat` doit dire qu'il n'y en a pas au lieu de suivre
    une cle etrangere nulle ; avec QR, il doit lire le fichier. Les deux
    chemins passent ici.
    """
    from django.urls import reverse

    fiche = profil(salon_a)

    vide = admin_client.get(reverse("admin:salons_salonprofile_change", args=[fiche.pk]))
    assert vide.status_code == 200
    assert "Aucun code" in vide.content.decode()

    code = qr_du_salon(salon_a)
    with as_tenant(salon_a.tenant):
        fiche.wechat_id = "byfaty"
        fiche.wechat_qr = code
        fiche.save(update_fields=["wechat_id", "wechat_qr"])

    plein = admin_client.get(
        reverse("admin:salons_salonprofile_change", args=[fiche.pk])
    )
    assert plein.status_code == 200
    page = plein.content.decode()
    assert "qr-wechat.png" in page
    assert "byfaty" in page


@ADMIN
def test_the_platform_list_shows_the_wechat_column(admin_client, salon_a):
    from django.urls import reverse

    fiche = profil(salon_a)
    with as_tenant(salon_a.tenant):
        fiche.wechat_id = "byfaty"
        fiche.save(update_fields=["wechat_id"])

    reponse = admin_client.get(reverse("admin:salons_salonprofile_changelist"))

    assert reponse.status_code == 200
    page = reponse.content.decode()
    assert "byfaty" in page
    # Sans QR : la colonne doit le dire, pas se contenter d'un « oui ».
    assert "sans QR" in page
