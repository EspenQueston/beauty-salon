"""« Mot de passe oublié » dans l'espace cliente d'un mini-site.

Le lien menait a une page de la plateforme qui n'existait pas (404). La
cliente recoit maintenant, aux couleurs du salon et dans sa langue, un lien
qui la ramene sur le mini-site ; le mot de passe se choisit la, par la meme
confirmation que l'espace professionnel.
"""

from urllib.parse import parse_qs, urlsplit

import pytest
from django.core import mail

from apps.accounts.models import User
from apps.clients.models import ClientProfile
from conftest import salon_host

URL = "/api/v1/public/client/password/reset"
HOTE = {"HTTP_HOST": salon_host("blondrose")}


@pytest.fixture
def cliente(db):
    user = User.objects.create_user(
        email="grace@example.com", password="ancien-mot-de-passe", display_name="Grâce"
    )
    ClientProfile.objects.create(user=user)
    return user


def _lien(message) -> str:
    return next(mot for mot in message.body.split() if "/compte/mot-de-passe?" in mot)


@pytest.mark.django_db
def test_la_cliente_recoit_un_lien_vers_le_mini_site(api_client, salon_a, cliente):
    reponse = api_client.post(URL, {"email": "Grace@Example.com", "lang": "fr"}, **HOTE)

    assert reponse.status_code == 200
    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert message.to == ["grace@example.com"]
    assert message.subject == "Réinitialiser votre mot de passe — Blond Rose"
    assert message.from_email.startswith("Blond Rose via Beauty Salon <")
    lien = urlsplit(_lien(message))
    assert lien.netloc.startswith("blondrose.")
    assert lien.path == "/fr/compte/mot-de-passe"
    assert {"uid", "token"} <= set(parse_qs(lien.query))


@pytest.mark.django_db
def test_le_message_suit_la_langue_du_mini_site(api_client, salon_a, cliente):
    api_client.post(URL, {"email": "grace@example.com", "lang": "en"}, **HOTE)

    message = mail.outbox[0]
    assert message.subject == "Reset your password — Blond Rose"
    assert "/en/compte/mot-de-passe?" in _lien(message)


@pytest.mark.django_db
def test_une_adresse_inconnue_recoit_la_meme_reponse(api_client, salon_a, cliente):
    connue = api_client.post(URL, {"email": "grace@example.com"}, **HOTE).json()
    inconnue = api_client.post(URL, {"email": "personne@example.com"}, **HOTE).json()

    assert connue == inconnue
    assert len(mail.outbox) == 1


@pytest.mark.django_db
def test_un_compte_d_equipe_recoit_le_lien_de_l_espace_pro(api_client, salon_a, settings):
    api_client.post(URL, {"email": salon_a.owner.email}, **HOTE)

    message = mail.outbox[0]
    assert settings.APP_BASE_URL in message.body
    assert "/compte/mot-de-passe?" not in message.body


@pytest.mark.django_db
def test_le_lien_permet_de_choisir_un_nouveau_mot_de_passe(api_client, salon_a, cliente):
    api_client.post(URL, {"email": "grace@example.com"}, **HOTE)
    requete = parse_qs(urlsplit(_lien(mail.outbox[0])).query)

    reponse = api_client.post(
        "/api/v1/account/password/reset/confirm",
        {
            "uid": requete["uid"][0],
            "token": requete["token"][0],
            "password": "nouveau-mot-de-passe-solide",
        },
        format="json",
    )

    assert reponse.status_code == 200, reponse.json()
    cliente.refresh_from_db()
    assert cliente.check_password("nouveau-mot-de-passe-solide")
    # Le lien ne sert qu'une fois.
    encore = api_client.post(
        "/api/v1/account/password/reset/confirm",
        {"uid": requete["uid"][0], "token": requete["token"][0], "password": "encore-un-autre-mdp"},
        format="json",
    )
    assert encore.status_code == 400
