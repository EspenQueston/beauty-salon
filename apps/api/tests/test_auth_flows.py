"""Inscription, mots de passe et invitations d'equipe.

Ces routes sont ouvertes sur internet et creent des comptes : ce sont les
plus interessantes a attaquer. Les tests portent donc autant sur ce qu'elles
refusent que sur ce qu'elles permettent.
"""

import pytest
from django.core import mail

from apps.accounts.models import Invitation, Membership, User
from apps.accounts.services import accept_invitation, invite_member, signup_salon
from apps.tenants.models import Tenant
from conftest import as_tenant
from tests.factories import UserFactory

# Transactions reelles, et les deux alias.
#
# Deux raisons, toutes deux fideles a la production :
#   - la recherche d'une invitation par jeton passe par l'alias `admin`, une
#     connexion distincte qui ne verrait pas des ecritures non validees ;
#   - les e-mails partent sur `transaction.on_commit`, donc jamais si
#     l'inscription echoue a mi-chemin. Sans commit reel, rien ne part.
pytestmark = pytest.mark.django_db(
    databases=["default", "admin"], transaction=True
)

PASSWORD = "motdepasse-solide"
NEW_PASSWORD = "nouveau-motdepasse-42"


def signup_payload(**overrides):
    payload = {
        "salon_name": "Studio Kiné",
        "slug": "studio-kine",
        "email": "proprietaire@example.com",
        "password": "un-mot-de-passe-solide",
        "accepts_terms": True,
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Inscription d'un salon
# ---------------------------------------------------------------------------


def test_signup_creates_a_pending_salon_with_its_owner(api_client):
    response = api_client.post(
        "/api/v1/account/signup", signup_payload(), format="json"
    )

    assert response.status_code == 201, response.data

    tenant = Tenant.objects.get(slug="studio-kine")
    # Le salon n'est pas public tant que l'equipe ne l'a pas valide.
    assert tenant.status == Tenant.Status.PENDING
    assert tenant.domains.filter(is_primary=True).exists()

    membership = Membership.objects.get(tenant=tenant)
    assert membership.role == Membership.Role.OWNER
    assert membership.user.email == "proprietaire@example.com"

    # Un e-mail de bienvenue part.
    assert len(mail.outbox) == 1

    # Mais aucune session n'est ouverte : s'inscrire ne vaut pas se
    # connecter. La reponse rend l'adresse pour pre-remplir l'ecran suivant.
    assert response.data["email"] == "proprietaire@example.com"
    assert api_client.get("/api/v1/auth/session").status_code == 403


def test_signing_up_then_logging_in(api_client):
    """Le mot de passe choisi a l'inscription ouvre bien la session."""
    api_client.post("/api/v1/account/signup", signup_payload(), format="json")

    response = api_client.post(
        "/api/v1/auth/login",
        {"email": "proprietaire@example.com", "password": signup_payload()["password"]},
        format="json",
    )

    assert response.status_code == 200, response.data
    assert api_client.get("/api/v1/auth/session").status_code == 200


def test_a_pending_salon_is_not_published(api_client):
    api_client.post("/api/v1/account/signup", signup_payload(), format="json")

    from conftest import salon_host

    response = api_client.get(
        "/api/v1/public/salon", headers={"Host": salon_host("studio-kine")}
    )

    assert response.status_code == 404
    assert response.json()["code"] == "not_published"


def test_signup_refuses_a_taken_address(api_client, salon_a):
    response = api_client.post(
        "/api/v1/account/signup", signup_payload(slug="blondrose"), format="json"
    )

    assert response.status_code == 400
    assert "slug" in response.data["detail"]


def test_signup_refuses_a_reserved_address(api_client):
    response = api_client.post(
        "/api/v1/account/signup", signup_payload(slug="admin"), format="json"
    )

    assert response.status_code == 400


def test_signup_refuses_a_weak_password(api_client):
    response = api_client.post(
        "/api/v1/account/signup", signup_payload(password="motdepasse"), format="json"
    )

    assert response.status_code == 400
    assert Tenant.objects.filter(slug="studio-kine").count() == 0


def test_signup_requires_accepting_the_terms(api_client):
    response = api_client.post(
        "/api/v1/account/signup", signup_payload(accepts_terms=False), format="json"
    )

    assert response.status_code == 400


def test_signup_refuses_an_email_already_registered(api_client, salon_a):
    response = api_client.post(
        "/api/v1/account/signup",
        signup_payload(email=salon_a.owner.email),
        format="json",
    )

    assert response.status_code == 400
    # Aucun salon orphelin ne doit rester derriere une inscription refusee.
    assert Tenant.objects.filter(slug="studio-kine").count() == 0


def test_slug_availability(api_client, salon_a):
    libre = api_client.get("/api/v1/account/slug-availability", {"slug": "nouveau-salon"})
    pris = api_client.get("/api/v1/account/slug-availability", {"slug": "blondrose"})
    reserve = api_client.get("/api/v1/account/slug-availability", {"slug": "app"})

    assert libre.data["available"] is True
    assert pris.data["available"] is False
    assert reserve.data["available"] is False


# ---------------------------------------------------------------------------
# Mot de passe oublie
# ---------------------------------------------------------------------------


def test_password_reset_sends_a_link_and_changes_the_password(api_client, salon_a):
    demande = api_client.post(
        "/api/v1/account/password/reset",
        {"email": salon_a.owner.email},
        format="json",
    )
    assert demande.status_code == 200
    assert len(mail.outbox) == 1

    uid, token = _extract_reset_credentials(mail.outbox[0].body)
    confirmation = api_client.post(
        "/api/v1/account/password/reset/confirm",
        {"uid": uid, "token": token, "password": NEW_PASSWORD},
        format="json",
    )

    assert confirmation.status_code == 200
    salon_a.owner.refresh_from_db()
    assert salon_a.owner.check_password(NEW_PASSWORD)


def test_password_reset_says_the_same_thing_for_an_unknown_email(api_client):
    response = api_client.post(
        "/api/v1/account/password/reset",
        {"email": "personne@example.com"},
        format="json",
    )

    # Meme reponse que pour un compte existant : ce formulaire ne doit pas
    # servir a savoir qui est inscrit.
    assert response.status_code == 200
    assert len(mail.outbox) == 0


def test_a_reset_link_cannot_be_used_twice(api_client, salon_a):
    api_client.post(
        "/api/v1/account/password/reset",
        {"email": salon_a.owner.email},
        format="json",
    )
    uid, token = _extract_reset_credentials(mail.outbox[0].body)

    body = {"uid": uid, "token": token, "password": NEW_PASSWORD}
    first = api_client.post("/api/v1/account/password/reset/confirm", body, format="json")
    second = api_client.post("/api/v1/account/password/reset/confirm", body, format="json")

    assert first.status_code == 200
    # Le jeton derive du hash du mot de passe : le changer l'invalide.
    assert second.status_code == 400
    assert second.json()["code"] == "invalid_token"


def test_a_forged_reset_token_is_refused(api_client, salon_a):
    api_client.post(
        "/api/v1/account/password/reset",
        {"email": salon_a.owner.email},
        format="json",
    )
    uid, _ = _extract_reset_credentials(mail.outbox[0].body)

    response = api_client.post(
        "/api/v1/account/password/reset/confirm",
        {"uid": uid, "token": "faux-jeton-inutile", "password": NEW_PASSWORD},
        format="json",
    )

    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Changement de mot de passe
# ---------------------------------------------------------------------------


def test_password_change_keeps_the_session_open(api_client, salon_a):
    assert api_client.login(email=salon_a.owner.email, password=PASSWORD)

    response = api_client.post(
        "/api/v1/auth/password/change",
        {"current_password": PASSWORD, "new_password": NEW_PASSWORD},
        format="json",
    )

    assert response.status_code == 200
    salon_a.owner.refresh_from_db()
    assert salon_a.owner.check_password(NEW_PASSWORD)
    # Sans update_session_auth_hash, la personne serait deconnectee ici.
    assert api_client.get("/api/v1/auth/session").status_code == 200


def test_password_change_requires_the_current_password(api_client, salon_a):
    assert api_client.login(email=salon_a.owner.email, password=PASSWORD)

    response = api_client.post(
        "/api/v1/auth/password/change",
        {"current_password": "ce-nest-pas-le-bon", "new_password": NEW_PASSWORD},
        format="json",
    )

    assert response.status_code == 400
    salon_a.owner.refresh_from_db()
    assert salon_a.owner.check_password(PASSWORD)


# ---------------------------------------------------------------------------
# Invitations d'equipe
# ---------------------------------------------------------------------------


def test_owner_invites_a_receptionist_who_creates_her_account(api_client, salon_a):
    assert api_client.login(email=salon_a.owner.email, password=PASSWORD)

    envoi = api_client.post(
        "/api/v1/invitations/",
        {"email": "reception@example.com", "role": "receptionist"},
        format="json",
    )
    assert envoi.status_code == 201, envoi.data
    assert len(mail.outbox) == 1

    token = _extract_invitation_token(mail.outbox[0].body)

    # La personne consulte l'invitation sans etre connectee.
    apercu = api_client.get("/api/v1/account/invitation", {"token": token})
    assert apercu.status_code == 200
    assert apercu.data["salon_name"] == "Blond Rose"
    assert apercu.data["account_exists"] is False

    acceptation = api_client.post(
        "/api/v1/account/invitation/accept",
        {"token": token, "password": NEW_PASSWORD, "display_name": "Reception"},
        format="json",
    )

    assert acceptation.status_code == 201
    membership = Membership.objects.get(
        tenant=salon_a.tenant, user__email="reception@example.com"
    )
    assert membership.role == Membership.Role.RECEPTIONIST
    assert membership.status == Membership.Status.ACTIVE


def test_an_existing_account_joins_without_a_new_password(salon_a, salon_b):
    """Une personne qui travaille deja dans un salon peut en rejoindre un autre."""
    existant = salon_b.owner

    with as_tenant(salon_a.tenant):
        invitation = invite_member(
            tenant=salon_a.tenant, email=existant.email, role=Membership.Role.STAFF
        )
    token = _extract_invitation_token(mail.outbox[-1].body)

    user, _ = accept_invitation(token=token)

    assert user.pk == existant.pk
    assert Membership.objects.filter(tenant=salon_a.tenant, user=existant).exists()
    with as_tenant(salon_a.tenant):
        invitation.refresh_from_db()
    assert invitation.accepted_at is not None


def test_an_invitation_cannot_be_used_twice(api_client, salon_a):
    with as_tenant(salon_a.tenant):
        invite_member(
            tenant=salon_a.tenant, email="deux-fois@example.com", role="staff"
        )
    token = _extract_invitation_token(mail.outbox[-1].body)

    body = {"token": token, "password": NEW_PASSWORD}
    first = api_client.post("/api/v1/account/invitation/accept", body, format="json")
    second = api_client.post("/api/v1/account/invitation/accept", body, format="json")

    assert first.status_code == 201
    assert second.status_code == 400


def test_a_revoked_invitation_is_refused(api_client, salon_a):
    assert api_client.login(email=salon_a.owner.email, password=PASSWORD)
    envoi = api_client.post(
        "/api/v1/invitations/",
        {"email": "annulee@example.com", "role": "staff"},
        format="json",
    )
    token = _extract_invitation_token(mail.outbox[-1].body)

    revocation = api_client.post(f"/api/v1/invitations/{envoi.data['id']}/revoke/")
    assert revocation.status_code == 200

    api_client.logout()
    acceptation = api_client.post(
        "/api/v1/account/invitation/accept",
        {"token": token, "password": NEW_PASSWORD},
        format="json",
    )

    assert acceptation.status_code == 400
    assert not User.objects.filter(email="annulee@example.com").exists()


def test_a_forged_invitation_token_reveals_nothing(api_client, salon_a):
    response = api_client.get("/api/v1/account/invitation", {"token": "jeton-invente"})

    assert response.status_code == 404
    assert response.json()["code"] == "invalid_invitation"


def test_the_raw_invitation_token_is_never_stored(salon_a):
    with as_tenant(salon_a.tenant):
        invite_member(tenant=salon_a.tenant, email="trace@example.com", role="staff")
        token = _extract_invitation_token(mail.outbox[-1].body)
        invitation = Invitation.objects.get(email="trace@example.com")

    # Une fuite de la base ne doit donner acces a aucun compte.
    assert token not in invitation.token_hash
    assert invitation.token_hash == Invitation.hash_token(token)


def test_a_receptionist_cannot_invite(api_client, salon_a):
    from tests.factories import MembershipFactory

    receptionniste = UserFactory()
    MembershipFactory(
        tenant=salon_a.tenant,
        user=receptionniste,
        role=Membership.Role.RECEPTIONIST,
    )
    assert api_client.login(email=receptionniste.email, password=PASSWORD)

    response = api_client.post(
        "/api/v1/invitations/",
        {"email": "quelquun@example.com", "role": "staff"},
        format="json",
    )

    assert response.status_code == 403


def test_invitations_of_another_salon_stay_invisible(api_client, salon_a, salon_b):
    with as_tenant(salon_b.tenant):
        invite_member(tenant=salon_b.tenant, email="chez-anna@example.com", role="staff")

    assert api_client.login(email=salon_a.owner.email, password=PASSWORD)
    response = api_client.get("/api/v1/invitations/")

    assert response.status_code == 200
    assert response.data == []


def test_inviting_an_existing_member_is_refused(api_client, salon_a):
    assert api_client.login(email=salon_a.owner.email, password=PASSWORD)

    response = api_client.post(
        "/api/v1/invitations/",
        {"email": salon_a.owner.email, "role": "manager"},
        format="json",
    )

    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Equipe
# ---------------------------------------------------------------------------


def test_the_last_owner_cannot_be_removed(api_client, salon_a):
    assert api_client.login(email=salon_a.owner.email, password=PASSWORD)
    membership = Membership.objects.get(tenant=salon_a.tenant, user=salon_a.owner)

    suppression = api_client.delete(f"/api/v1/team/{membership.id}/")
    retrogradation = api_client.patch(
        f"/api/v1/team/{membership.id}/", {"role": "staff"}, format="json"
    )

    # Sans proprietaire, plus personne ne peut inviter ni fermer le compte.
    assert suppression.status_code == 400
    assert retrogradation.status_code == 400


def test_the_team_list_shows_only_this_salon(api_client, salon_a, salon_b):
    assert api_client.login(email=salon_a.owner.email, password=PASSWORD)
    response = api_client.get("/api/v1/team/")

    assert response.status_code == 200
    emails = {row["tenant"]["slug"] for row in response.data}
    assert emails == {"blondrose"}


# ---------------------------------------------------------------------------
# Utilitaires
# ---------------------------------------------------------------------------


def _extract_reset_credentials(body: str) -> tuple[str, str]:
    for word in body.split():
        if "uid=" in word and "token=" in word:
            query = word.split("?", 1)[1]
            parts = dict(pair.split("=", 1) for pair in query.split("&"))
            return parts["uid"], parts["token"]
    raise AssertionError(f"Lien de reinitialisation introuvable dans :\n{body}")


def _extract_invitation_token(body: str) -> str:
    for word in body.split():
        if "token=" in word:
            return word.split("token=", 1)[1].strip()
    raise AssertionError(f"Jeton d'invitation introuvable dans :\n{body}")


def test_signing_up_while_logged_into_another_salon(api_client, salon_a):
    """Une gerante peut ouvrir un second salon sans se deconnecter.

    Les routes de compte n'ouvrent aucun contexte tenant : sans cela, le
    middleware aurait deja pose celui du salon courant et la creation du
    nouveau salon echouerait.
    """
    assert api_client.login(email=salon_a.owner.email, password=PASSWORD)

    response = api_client.post(
        "/api/v1/account/signup",
        signup_payload(email="second-salon@example.com", slug="second-salon"),
        format="json",
    )

    assert response.status_code == 201, response.data
    assert Tenant.objects.filter(slug="second-salon").exists()


@pytest.mark.django_db
def test_a_new_salon_starts_with_a_workable_schedule(api_client):
    """Un salon qui vient de s'inscrire propose deja des creneaux.

    Sans horaires, le moteur ne renvoie rien : le mini-site s'ouvre sur
    « aucune disponibilite » et la gerante conclut que la reservation ne
    marche pas. C'est le premier abandon du parcours, et il se corrige en
    posant une grille de depart modifiable.
    """
    from apps.scheduling.models import BusinessHours

    api_client.post("/api/v1/account/signup", signup_payload(), format="json")

    tenant = Tenant.objects.get(slug="studio-kine")
    with as_tenant(tenant):
        hours = list(BusinessHours.objects.filter(tenant=tenant))

    # Mardi -> samedi, deux plages par jour (coupure du midi).
    assert len(hours) == 10
    assert sorted({row.weekday for row in hours}) == [1, 2, 3, 4, 5]
    # Les horaires du salon, pas ceux d'une personne en particulier.
    assert all(row.staff_member_id is None for row in hours)


@pytest.mark.django_db
def test_signup_keeps_the_colours_composed_before_registering(api_client):
    """Ce qu'on a composé sur la page d'accueil est réellement appliqué.

    La page promet « vos choix vous suivent ». Si la palette se perdait au
    passage du formulaire, cette phrase serait fausse — ce qui coûte plus
    cher que de ne rien promettre.
    """
    from apps.salons.models import SalonProfile
    from conftest import as_tenant

    payload = signup_payload()
    payload["theme_config"] = {
        "primary": "#0F766E",
        "accent": "#CDEDE7",
        "surface": "#F4FAF9",
    }

    response = api_client.post("/api/v1/account/signup", payload, format="json")
    assert response.status_code == 201, response.data

    tenant = Tenant.objects.get(slug=payload["slug"])
    with as_tenant(tenant):
        profile = SalonProfile.objects.get(tenant=tenant)
    assert profile.theme_config == payload["theme_config"]


@pytest.mark.django_db
def test_signup_refuses_a_colour_that_is_not_hexadecimal(api_client):
    """Le thème arrive de l'URL : une valeur libre finirait dans le CSS."""
    payload = signup_payload()
    payload["theme_config"] = {"primary": "red; background: url(evil)"}

    response = api_client.post("/api/v1/account/signup", payload, format="json")

    assert response.status_code == 400
    assert not Tenant.objects.filter(slug=payload["slug"]).exists()


@pytest.mark.django_db
def test_the_owner_is_a_provider_from_the_start(db):
    """Sans prestataire, le mini-site s'ouvre sur « aucune disponibilité ».

    Le cas de loin le plus fréquent est une personne qui travaille seule :
    elle *est* le salon. Lui demander de se créer une fiche pour se désigner
    elle-même est une étape qui n'a de sens que pour le logiciel — et tant
    qu'elle ne l'a pas faite, sa page paraît cassée.
    """
    from apps.staff.models import StaffMember

    tenant, user = signup_salon(
        name="Chez Awa",
        slug="chezawa",
        email="awa@example.com",
        password=PASSWORD,
        display_name="Awa Diallo",
    )

    with as_tenant(tenant):
        fiches = list(StaffMember.objects.all())

    assert len(fiches) == 1
    assert fiches[0].name == "Awa Diallo"
    assert fiches[0].active
    # Rattachée au compte : c'est ce lien qui fait qu'un prestataire ne voit
    # que son propre agenda.
    assert fiches[0].membership.user == user


@pytest.mark.django_db
def test_a_signup_without_a_personal_name_still_gets_a_named_provider(db):
    """Une fiche sans nom s'afficherait vide sur le mini-site.

    L'inscription retombe déjà sur le nom du salon quand personne n'a donné
    de nom personnel — « Salon Test » comme prestataire est étrange, mais
    c'est une ligne qu'on corrige en deux clics, là où une fiche anonyme
    passe inaperçue jusqu'à ce qu'une cliente la voie.
    """
    from apps.staff.models import StaffMember

    tenant, _ = signup_salon(
        name="Salon Test",
        slug="salontest",
        email="chantal.kouka@example.com",
        password=PASSWORD,
    )

    with as_tenant(tenant):
        fiche = StaffMember.objects.get()

    assert fiche.name.strip(), "la fiche du prestataire est sans nom"
    assert fiche.name == "Salon Test"
