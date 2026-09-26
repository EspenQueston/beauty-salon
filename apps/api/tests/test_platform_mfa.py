"""Double authentification des administrateurs plateforme.

L'enjeu est precis : un compte d'administration ouvre l'alias de base qui
contourne les politiques RLS. Un mot de passe vole y donnerait acces aux
donnees de tous les salons a la fois.
"""

import time

import pytest
from django.urls import reverse
from django_otp.oath import TOTP
from django_otp.plugins.otp_static.models import StaticDevice
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.mfa import confirmed_device, pending_device
from tests.factories import UserFactory

PASSWORD = "motdepasse-solide"

# La page d'accueil de l'administration lit ses chiffres de supervision sur
# l'alias privilegie : les tests qui l'ouvrent doivent le declarer.
pytestmark = pytest.mark.django_db(databases=["default", "admin"])


@pytest.fixture(autouse=True)
def mfa_required(settings):
    """La MFA est desactivee dans les reglages de test pour ne pas alourdir
    les autres suites ; ici on la remet, c'est tout l'objet du fichier."""
    settings.PLATFORM_ADMIN_MFA_REQUIRED = True


@pytest.fixture
def admin_user():
    return UserFactory(
        email="admin@example.com",
        is_staff=True,
        is_superuser=True,
        is_platform_admin=True,
    )


def code_for(device: TOTPDevice, offset: float = 0) -> str:
    """Code TOTP pour cet appareil.

    `offset` decale l'instant de generation. django-otp refuse un jeton dont
    le pas de temps a deja servi : c'est sa protection anti-rejeu. Deux
    verifications successives dans la meme fenetre de 30 secondes doivent
    donc viser des pas differents, ce qu'un humain fait naturellement en
    attendant le code suivant.
    """
    totp = TOTP(device.bin_key, device.step, device.t0, device.digits)
    totp.time = time.time() + offset
    return format(totp.token(), f"0{device.digits}d")


# ---------------------------------------------------------------------------
# Verrouillage de l'administration
# ---------------------------------------------------------------------------


def test_the_admin_is_closed_without_verification(client, admin_user):
    assert client.login(email=admin_user.email, password=PASSWORD)

    response = client.get("/admin/")

    # Mot de passe correct, mais session non verifiee : on ne rentre pas.
    assert response.status_code == 302
    assert response["Location"].startswith(reverse("mfa"))


def test_the_admin_stays_closed_under_its_production_path(client, admin_user, settings):
    """En production, l'administration vit sous un chemin tire au hasard.

    Le middleware ne gardait que `/admin/` : sous `ADMIN_PATH`, un mot de
    passe suffisait. La garde doit suivre le chemin reel.
    """
    settings.ADMIN_PATH = "gestion-8bf2e7757220/"
    assert client.login(email=admin_user.email, password=PASSWORD)

    for path in ("/gestion-8bf2e7757220/", "/gestion-8bf2e7757220/tenants/tenant/"):
        response = client.get(path)
        assert response.status_code == 302, path
        assert response["Location"].startswith(reverse("mfa")), path

    # L'ecran de connexion, lui, reste exempte : c'est la porte d'entree.
    connexion = client.get("/gestion-8bf2e7757220/login/")
    assert not connexion.get("Location", "").startswith(reverse("mfa"))


def test_every_admin_page_is_closed_not_only_the_index(client, admin_user):
    assert client.login(email=admin_user.email, password=PASSWORD)

    for path in ("/admin/tenants/tenant/", "/admin/accounts/user/", "/admin/scheduling/booking/"):
        response = client.get(path)
        assert response.status_code == 302, path
        assert response["Location"].startswith(reverse("mfa")), path


def test_the_login_page_stays_reachable(client):
    """Sinon plus personne ne pourrait ouvrir de session."""
    assert client.get("/admin/login/").status_code == 200


def test_a_non_staff_account_is_not_sent_to_the_mfa_screen(client, salon_a):
    """Le middleware ne concerne que l'administration plateforme."""
    assert client.login(email=salon_a.owner.email, password=PASSWORD)

    response = client.get("/admin/")

    # L'admin renvoie vers sa propre page de connexion, pas vers la MFA.
    assert reverse("mfa") not in response.get("Location", "")


# ---------------------------------------------------------------------------
# Enrolement
# ---------------------------------------------------------------------------


def test_enrolment_shows_a_qr_code_and_activates_the_device(client, admin_user):
    assert client.login(email=admin_user.email, password=PASSWORD)

    page = client.get(reverse("mfa"))
    assert page.status_code == 200
    assert b"<svg" in page.content
    assert confirmed_device(admin_user) is None

    device = pending_device(admin_user)
    response = client.post(reverse("mfa"), {"token": code_for(device)})

    assert response.status_code == 200
    assert confirmed_device(admin_user) is not None
    # Les codes de secours sont affiches une seule fois, a cet instant.
    assert len(response.context["codes"]) == 8


def test_the_secret_does_not_change_between_two_loads(client, admin_user):
    """Recharger la page ne doit pas changer le QR sous les yeux de la
    personne en train de le scanner."""
    assert client.login(email=admin_user.email, password=PASSWORD)

    first = pending_device(admin_user).bin_key
    client.get(reverse("mfa"))
    client.get(reverse("mfa"))

    assert pending_device(admin_user).bin_key == first
    assert TOTPDevice.objects.filter(user=admin_user).count() == 1


def test_a_wrong_code_does_not_activate_anything(client, admin_user):
    assert client.login(email=admin_user.email, password=PASSWORD)
    client.get(reverse("mfa"))

    response = client.post(reverse("mfa"), {"token": "000000"})

    assert response.status_code == 200
    assert confirmed_device(admin_user) is None
    assert client.get("/admin/").status_code == 302


def test_the_admin_opens_once_the_session_is_verified(client, admin_user):
    assert client.login(email=admin_user.email, password=PASSWORD)
    device = pending_device(admin_user)
    client.post(reverse("mfa"), {"token": code_for(device)})

    assert client.get("/admin/").status_code == 200


# ---------------------------------------------------------------------------
# Sessions suivantes
# ---------------------------------------------------------------------------


def test_a_new_session_asks_for_the_code_again(client, admin_user):
    """Le controle porte sur la session, pas sur l'existence d'un appareil :
    un mot de passe vole ne suffit jamais, meme apres enrolement."""
    assert client.login(email=admin_user.email, password=PASSWORD)
    device = pending_device(admin_user)
    client.post(reverse("mfa"), {"token": code_for(device)})
    client.logout()

    assert client.login(email=admin_user.email, password=PASSWORD)
    assert client.get("/admin/").status_code == 302

    page = client.get(reverse("mfa"))
    assert page.status_code == 200
    assert b"Code de v" in page.content  # ecran de verification, pas d'enrolement

    # Pas de temps suivant : le precedent a servi a l'enrolement.
    client.post(
        reverse("mfa"),
        {"token": code_for(confirmed_device(admin_user), offset=30)},
    )
    assert client.get("/admin/").status_code == 200


def test_a_recovery_code_works_once(client, admin_user):
    assert client.login(email=admin_user.email, password=PASSWORD)
    device = pending_device(admin_user)
    enrolment = client.post(reverse("mfa"), {"token": code_for(device)})
    code = enrolment.context["codes"][0]
    client.logout()

    assert client.login(email=admin_user.email, password=PASSWORD)
    client.post(reverse("mfa"), {"token": code})
    assert client.get("/admin/").status_code == 200

    # Rejoue : le meme code ne doit plus rien ouvrir.
    client.logout()
    assert client.login(email=admin_user.email, password=PASSWORD)
    client.post(reverse("mfa"), {"token": code})
    assert client.get("/admin/").status_code == 302


def test_recovery_codes_are_replaced_at_each_enrolment(client, admin_user):
    assert client.login(email=admin_user.email, password=PASSWORD)
    device = pending_device(admin_user)
    client.post(reverse("mfa"), {"token": code_for(device)})

    static = StaticDevice.objects.get(user=admin_user)
    assert static.token_set.count() == 8


# ---------------------------------------------------------------------------
# Detournements
# ---------------------------------------------------------------------------


def test_the_mfa_screen_requires_a_session(client):
    response = client.get(reverse("mfa"))

    assert response.status_code == 302
    assert "/admin/login" in response["Location"] or "login" in response["Location"]


def test_an_external_redirect_is_refused_after_verification(client, admin_user):
    """`next` ne doit pas pouvoir envoyer ailleurs que sur le site."""
    assert client.login(email=admin_user.email, password=PASSWORD)
    device = pending_device(admin_user)

    response = client.post(
        f"{reverse('mfa')}?next=https://exemple-malveillant.test/",
        {"token": code_for(device)},
    )

    assert response.context["next_url"] == reverse("admin:index")


def test_the_requirement_can_be_lifted_for_local_development(
    client, admin_user, settings
):
    settings.PLATFORM_ADMIN_MFA_REQUIRED = False
    assert client.login(email=admin_user.email, password=PASSWORD)

    assert client.get("/admin/").status_code == 200
