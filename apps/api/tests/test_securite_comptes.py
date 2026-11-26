"""Audit de l'authentification (2026-10-02) : les correctifs, et ce qu'ils empechent.

Chaque test decrit un abus concret, rejoue de facon non destructive :

  - force brute et essais distribues sur un meme compte ;
  - annuaire des comptes par le chronometre ou le texte des reponses ;
  - bombardement d'e-mails de reinitialisation ;
  - sessions qui survivent a un changement de mot de passe ;
  - gerante qui se nomme proprietaire ;
  - lien d'invitation qui ouvre un compte existant sans mot de passe ;
  - changement d'adresse e-mail avec une session volee ;
  - verification d'adresse : jeton unique, expirant, lie a l'adresse.
"""

from unittest.mock import patch

import pytest
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from apps.accounts import verification
from apps.accounts.models import Invitation, Membership, User
from apps.billing import services as facturation
from apps.billing.services import PaiementRefuse
from apps.tenants.models import Tenant
from conftest import as_tenant
from tests.factories import MembershipFactory, TenantFactory, UserFactory
from tests.test_abonnements import (
    ADMIN,
    abonnement_de,
    medias_temporaires,
    moyens,
    offres,
)
from tests.test_auth_flows import signup_payload

FIXTURES_PARTAGEES = (medias_temporaires, moyens, offres)
MDP = "motdepasse-solide"


def connexion(client, email, mot_de_passe=MDP):
    return client.post(
        "/api/v1/auth/login", {"email": email, "password": mot_de_passe}, format="json"
    )


# ---------------------------------------------------------------------------
# Connexion
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_le_message_d_echec_ne_dit_pas_si_le_compte_existe(api_client):
    UserFactory(email="awa@example.com")

    inconnu = connexion(api_client, "personne@example.com")
    mauvais = connexion(api_client, "awa@example.com", "pas-le-bon-mot")

    assert inconnu.status_code == mauvais.status_code == 401
    assert inconnu.json() == mauvais.json()


@pytest.mark.django_db
def test_cinq_echecs_suspendent_les_essais_sur_cette_adresse(api_client):
    UserFactory(email="awa@example.com")
    for _ in range(5):
        connexion(api_client, "awa@example.com", "pas-le-bon-mot")

    # Meme le bon mot de passe est refuse pendant la fenetre : c'est ce qui
    # rend la force brute inutile.
    reponse = connexion(api_client, "AWA@example.com")

    assert reponse.status_code == 429
    assert reponse.json()["code"] == "too_many_attempts"


@pytest.mark.django_db
def test_le_frein_est_le_meme_pour_une_adresse_inconnue(api_client):
    for _ in range(5):
        connexion(api_client, "personne@example.com", "x")

    assert connexion(api_client, "personne@example.com", "x").status_code == 429


@pytest.mark.django_db
def test_une_connexion_reussie_remet_le_compteur_a_zero(api_client):
    UserFactory(email="awa@example.com")
    for _ in range(4):
        connexion(api_client, "awa@example.com", "pas-le-bon-mot")

    assert connexion(api_client, "awa@example.com").status_code == 200
    api_client.logout()
    for _ in range(4):
        connexion(api_client, "awa@example.com", "pas-le-bon-mot")
    assert connexion(api_client, "awa@example.com").status_code == 200


@pytest.mark.django_db
def test_l_administration_freine_aussi_ses_tentatives(client, settings):
    UserFactory(email="admin@example.com", is_staff=True, is_superuser=True)
    url = reverse("admin:login")
    for _ in range(5):
        client.post(url, {"username": "admin@example.com", "password": "faux"})

    reponse = client.post(url, {"username": "admin@example.com", "password": MDP}, follow=True)

    assert "Trop de tentatives" in reponse.content.decode()
    assert "_auth_user_id" not in client.session


# ---------------------------------------------------------------------------
# Mot de passe oublie
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_reinitialisation_meme_reponse_et_un_seul_e_mail_a_la_fois(
    api_client, django_capture_on_commit_callbacks
):
    UserFactory(email="awa@example.com")
    url = "/api/v1/account/password/reset"

    with django_capture_on_commit_callbacks(execute=True):
        existant = api_client.post(url, {"email": "awa@example.com"}, format="json")
        inconnu = api_client.post(url, {"email": "personne@example.com"}, format="json")
        # Deuxieme demande dans la foulee : freinee, en silence.
        api_client.post(url, {"email": "awa@example.com"}, format="json")

    assert existant.status_code == inconnu.status_code == 200
    assert existant.json() == inconnu.json()
    assert [m.to for m in mail.outbox] == [["awa@example.com"]]


@pytest.mark.django_db
def test_la_reinitialisation_ferme_les_autres_sessions_et_previent(
    api_client, django_capture_on_commit_callbacks
):
    from django.contrib.auth.tokens import default_token_generator
    from django.utils.encoding import force_bytes
    from django.utils.http import urlsafe_base64_encode
    from rest_framework.test import APIClient

    user = UserFactory(email="awa@example.com")
    autre_appareil = APIClient()
    autre_appareil.force_login(user)
    assert autre_appareil.get("/api/v1/auth/session").status_code == 200

    with django_capture_on_commit_callbacks(execute=True):
        reponse = api_client.post(
            "/api/v1/account/password/reset/confirm",
            {
                "uid": urlsafe_base64_encode(force_bytes(user.pk)),
                "token": default_token_generator.make_token(user),
                "password": "un-nouveau-mot-de-passe-42",
            },
            format="json",
        )

    assert reponse.status_code == 200
    assert autre_appareil.get("/api/v1/auth/session").status_code == 403
    assert mail.outbox[-1].to == ["awa@example.com"]
    assert "modifié" in mail.outbox[-1].subject
    assert "un-nouveau-mot-de-passe-42" not in mail.outbox[-1].body


@pytest.mark.django_db
def test_changer_son_mot_de_passe_garde_cette_session_et_ferme_les_autres(
    api_client, django_capture_on_commit_callbacks
):
    from rest_framework.test import APIClient

    user = UserFactory(email="awa@example.com")
    api_client.force_login(user)
    autre_appareil = APIClient()
    autre_appareil.force_login(user)

    with django_capture_on_commit_callbacks(execute=True):
        reponse = api_client.post(
            "/api/v1/auth/password/change",
            {"current_password": MDP, "new_password": "un-nouveau-mot-de-passe-42"},
            format="json",
        )

    assert reponse.status_code == 200
    assert api_client.get("/api/v1/auth/session").status_code == 200
    assert autre_appareil.get("/api/v1/auth/session").status_code == 403
    assert len(mail.outbox) == 1


# ---------------------------------------------------------------------------
# Roles de l'equipe
# ---------------------------------------------------------------------------


@pytest.fixture
def equipe(salon_a):
    gerante = UserFactory(email="gerante@example.com")
    adhesion = MembershipFactory(tenant=salon_a.tenant, user=gerante, role="manager")
    return gerante, adhesion


@pytest.mark.django_db
def test_une_gerante_ne_peut_pas_se_nommer_proprietaire(api_client, salon_a, equipe):
    gerante, adhesion = equipe
    api_client.force_login(gerante)

    reponse = api_client.patch(f"/api/v1/team/{adhesion.pk}/", {"role": "owner"}, format="json")

    assert reponse.status_code == 400
    adhesion.refresh_from_db()
    assert adhesion.role == "manager"


@pytest.mark.django_db
def test_une_gerante_ne_touche_ni_ne_nomme_un_proprietaire(api_client, salon_a, equipe):
    gerante, _ = equipe
    collegue = MembershipFactory(tenant=salon_a.tenant, role="staff")
    api_client.force_login(gerante)

    promotion = api_client.patch(f"/api/v1/team/{collegue.pk}/", {"role": "owner"}, format="json")
    retrait = api_client.delete(f"/api/v1/team/{salon_a.membership.pk}/")
    invitation = api_client.post(
        "/api/v1/invitations/", {"email": "x@example.com", "role": "owner"}, format="json"
    )

    assert promotion.status_code == 400
    assert retrait.status_code == 400
    assert invitation.status_code == 403
    assert Membership.objects.filter(pk=salon_a.membership.pk).exists()


@pytest.mark.django_db
def test_la_proprietaire_peut_nommer_une_autre_proprietaire(api_client, salon_a, equipe):
    _, adhesion = equipe
    api_client.force_login(salon_a.owner)

    reponse = api_client.patch(f"/api/v1/team/{adhesion.pk}/", {"role": "owner"}, format="json")

    assert reponse.status_code == 200


# ---------------------------------------------------------------------------
# Invitations
# ---------------------------------------------------------------------------


@ADMIN
def test_un_lien_d_invitation_n_ouvre_pas_un_compte_existant_sans_son_mot_de_passe(
    api_client, salon_a
):
    UserFactory(email="existante@example.com")
    with as_tenant(salon_a.tenant):
        _, jeton = Invitation.issue(
            tenant=salon_a.tenant, email="existante@example.com", role="staff"
        )
    url = "/api/v1/account/invitation/accept"

    sans = api_client.post(url, {"token": jeton}, format="json")
    faux = api_client.post(url, {"token": jeton, "password": "pas-le-bon"}, format="json")
    bon = api_client.post(url, {"token": jeton, "password": MDP}, format="json")

    assert sans.status_code == faux.status_code == 400
    assert bon.status_code == 201


# ---------------------------------------------------------------------------
# Changement d'adresse e-mail
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_changer_d_adresse_exige_le_mot_de_passe_et_previent_l_ancienne(
    api_client, salon_a, django_capture_on_commit_callbacks
):
    api_client.force_login(salon_a.owner)
    ancienne = salon_a.owner.email

    refuse = api_client.patch(
        "/api/v1/salon-identity", {"owner_email": "nouvelle@example.com"}, format="json"
    )
    assert refuse.status_code == 400
    assert refuse.json()["code"] == "password_required"

    with django_capture_on_commit_callbacks(execute=True):
        accepte = api_client.patch(
            "/api/v1/salon-identity",
            {"owner_email": "nouvelle@example.com", "current_password": MDP},
            format="json",
        )

    assert accepte.status_code == 200
    salon_a.owner.refresh_from_db()
    assert salon_a.owner.email == "nouvelle@example.com"
    # La nouvelle adresse doit faire ses preuves.
    assert salon_a.owner.email_verified_at is None
    destinataires = {tuple(m.to) for m in mail.outbox}
    assert (ancienne,) in destinataires
    assert ("nouvelle@example.com",) in destinataires


@pytest.mark.django_db
def test_garder_la_meme_adresse_ne_demande_pas_de_mot_de_passe(api_client, salon_a):
    api_client.force_login(salon_a.owner)

    reponse = api_client.patch(
        "/api/v1/salon-identity",
        {"owner_email": salon_a.owner.email.upper(), "owner_name": "Fatou"},
        format="json",
    )

    assert reponse.status_code == 200


# ---------------------------------------------------------------------------
# Verification d'adresse e-mail
# ---------------------------------------------------------------------------


@ADMIN
def test_l_inscription_d_un_salon_envoie_le_lien_et_laisse_l_adresse_a_prouver(api_client, offres):
    reponse = api_client.post("/api/v1/account/signup", signup_payload(), format="json")

    assert reponse.status_code == 201
    user = User.objects.get(email="proprietaire@example.com")
    assert user.email_verified_at is None
    lien = next(m for m in mail.outbox if "Confirmez" in m.subject)
    assert "/verifier-email?token=" in lien.body
    # Le lien ne transporte pas l'adresse en clair.
    assert "proprietaire@example.com" not in lien.body.split("token=")[1].split()[0]


@pytest.mark.django_db
def test_le_lien_verifie_l_adresse_une_seule_fois(api_client):
    user = UserFactory(email="awa@example.com", email_verified_at=None)
    jeton = verification.jeton(user)
    url = "/api/v1/account/email/verify"

    premiere = api_client.post(url, {"token": jeton}, format="json")
    seconde = api_client.post(url, {"token": jeton}, format="json")

    assert premiere.status_code == seconde.status_code == 200
    user.refresh_from_db()
    assert user.email_verified_at is not None


@pytest.mark.django_db
def test_un_lien_falsifie_expire_ou_pour_une_autre_adresse_est_refuse(api_client):
    user = UserFactory(email="awa@example.com", email_verified_at=None)
    url = "/api/v1/account/email/verify"
    jeton = verification.jeton(user)

    falsifie = api_client.post(url, {"token": jeton[:-3] + "abc"}, format="json")
    with patch.object(verification, "_duree", return_value=-1):
        expire = api_client.post(url, {"token": jeton}, format="json")
    user.email = "autre@example.com"
    user.save()
    ancienne_adresse = api_client.post(url, {"token": jeton}, format="json")

    assert falsifie.status_code == expire.status_code == ancienne_adresse.status_code == 400
    user.refresh_from_db()
    assert user.email_verified_at is None


@pytest.mark.django_db
def test_renvoyer_le_lien_est_freine(api_client, django_capture_on_commit_callbacks):
    user = UserFactory(email="awa@example.com", email_verified_at=None)
    api_client.force_login(user)
    url = "/api/v1/auth/email/verify/resend"

    with django_capture_on_commit_callbacks(execute=True):
        premier = api_client.post(url, {}, format="json")
        second = api_client.post(url, {}, format="json")

    assert premier.status_code == 200
    assert second.status_code == 429
    assert len(mail.outbox) == 1


@pytest.mark.django_db
def test_la_session_dit_si_l_adresse_est_verifiee(api_client):
    user = UserFactory(email_verified_at=None)
    api_client.force_login(user)

    assert api_client.get("/api/v1/auth/session").json()["email_verified"] is False


@pytest.mark.django_db
def test_une_reinitialisation_reussie_prouve_aussi_l_adresse(api_client):
    from django.contrib.auth.tokens import default_token_generator
    from django.utils.encoding import force_bytes
    from django.utils.http import urlsafe_base64_encode

    user = UserFactory(email_verified_at=None)
    api_client.post(
        "/api/v1/account/password/reset/confirm",
        {
            "uid": urlsafe_base64_encode(force_bytes(user.pk)),
            "token": default_token_generator.make_token(user),
            "password": "un-nouveau-mot-de-passe-42",
        },
        format="json",
    )

    user.refresh_from_db()
    assert user.email_verified_at is not None


@ADMIN
def test_sans_adresse_verifiee_pas_de_paiement_declare(salon_a, moyens):
    abonnement_de(salon_a)
    User.objects.filter(pk=salon_a.owner.pk).update(email_verified_at=None)
    salon_a.owner.refresh_from_db()

    with as_tenant(salon_a.tenant), pytest.raises(PaiementRefuse) as refus:
        facturation.soumettre_paiement(
            tenant_id=salon_a.tenant.id,
            utilisateur=salon_a.owner,
            code_offre="monthly",
            pays=moyens["momo"].country,
            devise=moyens["momo"].currency,
            moyen_id=moyens["momo"].id,
            reference="REF-VERIF-1",
        )

    assert refus.value.code == "email_non_verifie"


@ADMIN
def test_l_administration_ne_publie_pas_un_salon_non_verifie(client):
    admin = UserFactory(
        email="supervision@example.com", is_staff=True, is_superuser=True, is_platform_admin=True
    )
    client.force_login(admin)
    tenant = TenantFactory(status=Tenant.Status.PENDING)
    MembershipFactory(tenant=tenant, user=UserFactory(email_verified_at=None))

    with patch("apps.accounts.mfa.confirmed_device", return_value=True):
        client.post(
            reverse("admin:tenants_tenant_changelist"),
            {"action": "action_publish", "_selected_action": [str(tenant.pk)], "index": 0},
            follow=True,
        )

    tenant.refresh_from_db()
    assert tenant.status == Tenant.Status.PENDING


@pytest.mark.django_db
def test_une_cliente_qui_s_inscrit_recoit_un_lien_vers_le_mini_site(
    api_client, salon_a, django_capture_on_commit_callbacks
):
    from conftest import salon_host

    with django_capture_on_commit_callbacks(execute=True):
        reponse = api_client.post(
            "/api/v1/public/client/signup",
            {
                "full_name": "Awa Diallo",
                "email": "awa@example.com",
                "phone": "+242061234567",
                "password": "un-mot-de-passe-solide",
            },
            format="json",
            headers={"Host": salon_host("blondrose")},
        )

    assert reponse.status_code == 201
    assert reponse.json()["email_verified"] is False
    lien = mail.outbox[-1].body
    assert "blondrose" in lien and "/compte/verifier-email?token=" in lien


def test_les_comptes_existants_sont_consideres_comme_verifies():
    """La migration 0006 marque verifies les comptes anterieurs : rien ne se ferme."""
    from pathlib import Path

    migration = (
        Path(__file__).parents[1] / "apps/accounts/migrations/0006_user_email_verified_at.py"
    )
    assert "SET email_verified_at = created_at" in migration.read_text(encoding="utf-8")


def test_le_jeton_ne_contient_pas_l_adresse():
    user = User(pk="00000000-0000-0000-0000-000000000001", email="secret@example.com")
    user.email_verified_at = None
    assert "secret" not in verification.jeton(user)
    assert timezone.now()  # garde l'import utile si le test evolue
