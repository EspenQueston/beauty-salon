"""Double authentification, mots de passe fuites, sessions inactives, journal.

Suite de l'audit du 2 octobre 2026 (voir test_securite_comptes.py).
"""

import time
from unittest.mock import patch

import pytest
from django.core import mail
from django.urls import reverse
from django_otp.oath import totp
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts import mfa_api, validators
from apps.accounts.sessions import CLE
from apps.audit.models import AuditLog
from apps.clients.models import ClientProfile
from apps.notifications.models import PlatformNotification
from tests.factories import UserFactory

MDP = "motdepasse-solide"


def code_de(appareil) -> str:
    return (
        f"{totp(appareil.bin_key, appareil.step, appareil.t0, appareil.digits, appareil.drift):06d}"
    )


def avec_2fa(user) -> TOTPDevice:
    return TOTPDevice.objects.create(user=user, name="Application", confirmed=True)


def connexion(client, email, mot_de_passe=MDP):
    return client.post(
        "/api/v1/auth/login", {"email": email, "password": mot_de_passe}, format="json"
    )


# ---------------------------------------------------------------------------
# Double authentification a la connexion
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_le_mot_de_passe_seul_n_ouvre_plus_la_session(api_client, salon_a):
    avec_2fa(salon_a.owner)

    reponse = connexion(api_client, salon_a.owner.email)

    assert reponse.status_code == 200
    assert reponse.json()["mfa_required"] is True
    assert api_client.get("/api/v1/auth/session").status_code == 403


@pytest.mark.django_db
def test_le_bon_code_ouvre_la_session_et_se_journalise(api_client, salon_a):
    appareil = avec_2fa(salon_a.owner)
    connexion(api_client, salon_a.owner.email)

    faux = api_client.post("/api/v1/auth/mfa/verify", {"code": "000000"}, format="json")
    # django-otp impose une seconde d'attente apres un code faux : on la passe.
    appareil.refresh_from_db()
    appareil.throttle_reset()
    bon = api_client.post("/api/v1/auth/mfa/verify", {"code": code_de(appareil)}, format="json")

    assert faux.status_code == 400
    assert bon.status_code == 200
    assert bon.json()["mfa_enabled"] is True
    assert api_client.get("/api/v1/auth/session").status_code == 200
    actions = set(AuditLog.objects.values_list("action", flat=True))
    assert {"auth.mfa_failed", "auth.login_succeeded"} <= actions


@pytest.mark.django_db
def test_un_code_de_secours_sert_une_seule_fois(api_client, salon_a):
    from apps.accounts.mfa import _issue_recovery_codes

    avec_2fa(salon_a.owner)
    codes = _issue_recovery_codes(salon_a.owner)

    connexion(api_client, salon_a.owner.email)
    premiere = api_client.post("/api/v1/auth/mfa/verify", {"code": codes[0]}, format="json")
    api_client.post("/api/v1/auth/logout")
    connexion(api_client, salon_a.owner.email)
    seconde = api_client.post("/api/v1/auth/mfa/verify", {"code": codes[0]}, format="json")

    assert premiere.status_code == 200
    assert premiere.json()["codes_de_secours_restants"] == len(codes) - 1
    assert seconde.status_code == 400


@pytest.mark.django_db
def test_sans_mot_de_passe_juste_pas_de_code_a_essayer(api_client, salon_a):
    appareil = avec_2fa(salon_a.owner)

    reponse = api_client.post("/api/v1/auth/mfa/verify", {"code": code_de(appareil)}, format="json")

    assert reponse.status_code == 400
    assert reponse.json()["code"] == "mfa_expired"


@pytest.mark.django_db
def test_l_attente_du_code_expire_apres_cinq_minutes(api_client, salon_a):
    appareil = avec_2fa(salon_a.owner)
    connexion(api_client, salon_a.owner.email)

    with patch("apps.accounts.mfa_api.time.time", return_value=time.time() + 6 * 60):
        reponse = api_client.post(
            "/api/v1/auth/mfa/verify", {"code": code_de(appareil)}, format="json"
        )

    assert reponse.json()["code"] == "mfa_expired"


@pytest.mark.django_db
def test_les_codes_faux_en_serie_sont_freines_et_signales(api_client, salon_a):
    from apps.notifications.service import prevenir_plateforme  # noqa: F401

    UserFactory(is_platform_admin=True)
    appareil = avec_2fa(salon_a.owner)
    connexion(api_client, salon_a.owner.email)
    for _ in range(5):
        api_client.post("/api/v1/auth/mfa/verify", {"code": "000000"}, format="json")

    reponse = api_client.post("/api/v1/auth/mfa/verify", {"code": code_de(appareil)}, format="json")

    assert reponse.status_code == 429
    assert AuditLog.objects.filter(action="auth.account_locked").exists()
    assert PlatformNotification.objects.filter(genre="incident").exists()


# ---------------------------------------------------------------------------
# Activer, desactiver
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_activer_exige_le_code_et_le_mot_de_passe(
    api_client, salon_a, django_capture_on_commit_callbacks
):
    api_client.force_login(salon_a.owner)
    preparation = api_client.post("/api/v1/auth/mfa/setup", {}, format="json")
    assert preparation.status_code == 200
    assert "<svg" in preparation.json()["qr_svg"]
    appareil = TOTPDevice.objects.get(user=salon_a.owner, confirmed=False)

    sans_mdp = api_client.post(
        "/api/v1/auth/mfa/confirm", {"code": code_de(appareil)}, format="json"
    )
    with django_capture_on_commit_callbacks(execute=True):
        active = api_client.post(
            "/api/v1/auth/mfa/confirm",
            {"code": code_de(appareil), "password": MDP},
            format="json",
        )

    assert sans_mdp.status_code == 400
    assert active.status_code == 200
    assert len(active.json()["codes"]) == 8
    assert mfa_api.active(salon_a.owner)
    assert AuditLog.objects.filter(action="auth.mfa_enabled").exists()
    assert "activée" in mail.outbox[-1].subject


@pytest.mark.django_db
def test_desactiver_exige_le_code_et_le_mot_de_passe(api_client, salon_a):
    appareil = avec_2fa(salon_a.owner)
    api_client.force_login(salon_a.owner)

    sans_code = api_client.post("/api/v1/auth/mfa/disable", {"password": MDP}, format="json")
    retire = api_client.post(
        "/api/v1/auth/mfa/disable", {"password": MDP, "code": code_de(appareil)}, format="json"
    )

    assert sans_code.status_code == 400
    assert retire.status_code == 200
    assert not mfa_api.active(salon_a.owner)


@pytest.mark.django_db
def test_une_cliente_ne_regle_pas_la_double_authentification(api_client):
    cliente = UserFactory()
    ClientProfile.objects.create(user=cliente)
    api_client.force_login(cliente)

    assert api_client.post("/api/v1/auth/mfa/setup", {}, format="json").status_code == 403


# ---------------------------------------------------------------------------
# Mots de passe fuites (Have I Been Pwned)
# ---------------------------------------------------------------------------


class _Reponse:
    def __init__(self, texte):
        self.texte = texte

    def read(self):
        return self.texte.encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _hibp_connait(mot_de_passe: str):
    import hashlib

    empreinte = hashlib.sha1(mot_de_passe.encode()).hexdigest().upper()  # noqa: S324
    adresses = []

    def urlopen(requete, timeout):
        adresses.append(requete.full_url)
        return _Reponse(f"0000000000000000000000000000000000A:0\r\n{empreinte[5:]}:4521\r\n")

    return urlopen, adresses


@pytest.mark.django_db
def test_un_mot_de_passe_fuite_est_refuse_sans_le_divulguer(api_client, salon_a, settings):
    settings.PWNED_PASSWORDS_CHECK = True
    fuite = "un-mot-de-passe-tres-connu"
    faux_urlopen, adresses = _hibp_connait(fuite)
    api_client.force_login(salon_a.owner)

    with patch.object(validators, "urlopen", side_effect=faux_urlopen):
        reponse = api_client.post(
            "/api/v1/auth/password/change",
            {"current_password": MDP, "new_password": fuite},
            format="json",
        )

    assert reponse.status_code == 400
    assert "fuites" in str(reponse.json())
    # k-anonymat : seuls les 5 premiers caracteres de l'empreinte sont partis.
    assert len(adresses) == 1 and adresses[0].rsplit("/", 1)[1] == adresses[0][-5:]
    assert fuite not in adresses[0]
    assert AuditLog.objects.filter(action="auth.password_breached").exists()


@pytest.mark.django_db
def test_si_le_service_ne_repond_pas_le_mot_de_passe_passe(settings):
    from urllib.error import URLError

    settings.PWNED_PASSWORDS_CHECK = True
    with patch.object(validators, "urlopen", side_effect=URLError("hors ligne")):
        validators.PwnedPasswordValidator().validate("un-mot-de-passe-inedit-42")


@pytest.mark.django_db
def test_un_mot_de_passe_inconnu_des_fuites_passe(settings):
    settings.PWNED_PASSWORDS_CHECK = True
    faux_urlopen, _ = _hibp_connait("autre-chose")
    with patch.object(validators, "urlopen", side_effect=faux_urlopen):
        validators.PwnedPasswordValidator().validate("un-mot-de-passe-inedit-42")


# ---------------------------------------------------------------------------
# Sessions inactives
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_une_session_inactive_depuis_trois_jours_se_ferme(api_client, salon_a):
    api_client.force_login(salon_a.owner)
    assert api_client.get("/api/v1/auth/session").status_code == 200

    session = api_client.session
    session[CLE] = int(time.time()) - 4 * 24 * 60 * 60
    session.save()

    assert api_client.get("/api/v1/auth/session").status_code == 403


@pytest.mark.django_db
def test_une_session_active_reste_ouverte(api_client, salon_a):
    api_client.force_login(salon_a.owner)
    session = api_client.session
    session[CLE] = int(time.time()) - 2 * 24 * 60 * 60
    session.save()

    assert api_client.get("/api/v1/auth/session").status_code == 200
    # L'activite a ete rafraichie.
    assert api_client.session[CLE] > int(time.time()) - 60


@pytest.mark.django_db
def test_l_administration_se_ferme_apres_huit_heures(client):
    admin = UserFactory(is_staff=True, is_superuser=True, is_platform_admin=True)
    client.force_login(admin)
    session = client.session
    session[CLE] = int(time.time()) - 9 * 60 * 60
    session.save()

    reponse = client.get(reverse("admin:index"))

    assert reponse.status_code == 302
    assert "login" in reponse["Location"]


# ---------------------------------------------------------------------------
# Journal
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_les_connexions_sont_journalisees_sans_mot_de_passe(api_client, salon_a):
    connexion(api_client, salon_a.owner.email, "pas-le-bon-mot")
    connexion(api_client, salon_a.owner.email)

    echec = AuditLog.objects.get(action="auth.login_failed")
    succes = AuditLog.objects.get(action="auth.login_succeeded")
    assert echec.metadata["email"] == salon_a.owner.email
    assert "ip" in echec.metadata
    assert succes.actor_user == salon_a.owner
    assert "pas-le-bon-mot" not in str(echec.metadata)


@pytest.mark.django_db
def test_un_blocage_previent_l_equipe_plateforme(api_client):
    UserFactory(is_platform_admin=True)
    for _ in range(5):
        connexion(api_client, "cible@example.com", "faux")

    assert AuditLog.objects.filter(action="auth.account_locked").count() == 1
    alerte = PlatformNotification.objects.get(genre="incident")
    assert "cible@example.com" in alerte.corps
    assert "suspendues" in alerte.titre


@pytest.mark.django_db(databases=["default", "admin"], transaction=True)
def test_le_journal_de_securite_se_filtre_dans_l_administration(client, salon_a):
    admin = UserFactory(is_staff=True, is_superuser=True, is_platform_admin=True)
    client.force_login(admin)
    connexion_client = client.post(
        "/api/v1/auth/login",
        {"email": salon_a.owner.email, "password": "faux"},
        content_type="application/json",
    )
    assert connexion_client.status_code in (401, 403)

    reponse = client.get(reverse("admin:audit_auditlog_changelist") + "?categorie=securite")

    assert reponse.status_code == 200
    assert "Connexion échouée" in reponse.content.decode()
