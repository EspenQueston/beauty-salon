"""Les ensembles de couleurs a fond franc : blanc le jour, noir la nuit.

Ce que ces tests tiennent : la cle `dark` du theme est acceptee a
l'inscription et dans la fiche du salon, mais seulement sous forme de code
hexadecimal — elle entre telle quelle dans le CSS du mini-site.
"""

import pytest

PASSWORD = "motdepasse-solide"


@pytest.mark.django_db
def test_le_salon_choisit_un_ensemble_a_fond_noir(api_client, salon_a):
    assert api_client.login(email=salon_a.owner.email, password=PASSWORD)
    theme = {"primary": "#8A4F9E", "accent": "#EBDCF3", "surface": "#FFFFFF", "dark": "#000000"}

    reponse = api_client.patch("/api/v1/salon-profile", {"theme_config": theme}, format="json")

    assert reponse.status_code == 200, reponse.content
    assert reponse.data["theme_config"]["dark"] == "#000000"


@pytest.mark.django_db
@pytest.mark.parametrize("valeur", ["black", "#000", "url(x)", "#0000001", 12])
def test_un_fond_sombre_qui_n_est_pas_un_code_hexadecimal_est_refuse(api_client, salon_a, valeur):
    assert api_client.login(email=salon_a.owner.email, password=PASSWORD)

    reponse = api_client.patch(
        "/api/v1/salon-profile",
        {"theme_config": {"primary": "#8A4F9E", "dark": valeur}},
        format="json",
    )

    assert reponse.status_code == 400


@pytest.mark.django_db(databases=["default", "admin"], transaction=True)
def test_l_inscription_accepte_un_ensemble_a_fond_noir(api_client):
    reponse = api_client.post(
        "/api/v1/account/signup",
        {
            "salon_name": "Mauve Studio",
            "slug": "mauve-studio",
            "email": "mauve@example.com",
            "password": "un-mot-de-passe-solide",
            "accepts_terms": True,
            "theme_config": {
                "primary": "#14254D", "accent": "#F7C948", "surface": "#FFFFFF", "dark": "#000000",
            },
        },
        format="json",
    )

    assert reponse.status_code == 201, reponse.content
