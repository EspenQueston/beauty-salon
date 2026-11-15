"""Les textes qu'un salon Pro ecrit lui-meme suivent la langue du mini-site.

Accroche, bouton « Reserver », et surtout les pages ajoutees : leur titre
devient une entree du menu. Un menu anglais avec « Tarifs & forfaits » au
milieu se lit comme un oubli.

Ce qui compte ici, c'est que rien ne soit a declarer : une page creee demain
par un salon qui n'existe pas encore doit passer en anglais par le meme chemin
— l'enregistrement met la traduction en file, le mini-site la lit.
"""

import pytest

from apps.salons.models import SalonProfile
from apps.translations.models import Origin, Translation
from apps.translations.services import poser_traducteur, traduire
from apps.translations.traducteur import TraducteurFactice
from conftest import as_tenant
from tests.test_abonnements import medias_temporaires, offres
from tests.test_assistants_pro import HOTE, salon_pro
from tests.test_offres_pro import pro
from tests.test_pages_perso import URL, page

FIXTURES_PARTAGEES = (medias_temporaires, offres, pro, salon_pro)


@pytest.fixture(autouse=True)
def traducteur_factice():
    ancien = poser_traducteur(TraducteurFactice())
    yield
    poser_traducteur(ancien)


def publier(api_client, salon, django_capture_on_commit_callbacks, **config):
    """Enregistre comme le fait l'ecran Apparence, taches de traduction comprises."""
    api_client.force_login(salon.owner)
    with django_capture_on_commit_callbacks(execute=True):
        reponse = api_client.put(URL, config, format="json")
    assert reponse.status_code == 200, reponse.json()
    return reponse.json()["config"]


def public(api_client, langue=None):
    params = {"lang": langue} if langue else {}
    return api_client.get("/api/v1/public/salon", params, **HOTE).json()["site_config"]


@pytest.mark.django_db
def test_une_page_ajoutee_passe_en_anglais_sans_rien_declarer(
    api_client, salon_pro, django_capture_on_commit_callbacks
):
    publier(
        api_client,
        salon_pro,
        django_capture_on_commit_callbacks,
        accroche="Le soin de vos cheveux.",
        bouton_reserver="Je réserve",
        pages=[page("Tarifs", accroche="Nos prix.")],
    )

    anglais = public(api_client, "en")
    francais = public(api_client)

    assert anglais["accroche"] == "[en] Le soin de vos cheveux."
    assert anglais["bouton_reserver"] == "[en] Je réserve"
    assert anglais["pages"][0]["titre"] == "[en] Tarifs"
    assert anglais["pages"][0]["accroche"] == "[en] Nos prix."
    assert anglais["pages"][0]["contenu"] == "[en] Premier.\n\nSecond."
    # L'adresse ne change pas avec la langue : /p/tarifs reste /p/tarifs.
    assert anglais["pages"][0]["slug"] == francais["pages"][0]["slug"] == "tarifs"
    assert francais["pages"][0]["titre"] == "Tarifs"
    assert francais["accroche"] == "Le soin de vos cheveux."


@pytest.mark.django_db
def test_une_page_ajoutee_plus_tard_rejoint_le_menu_anglais(
    api_client, salon_pro, django_capture_on_commit_callbacks
):
    config = publier(
        api_client, salon_pro, django_capture_on_commit_callbacks, pages=[page("Tarifs")]
    )
    publier(
        api_client,
        salon_pro,
        django_capture_on_commit_callbacks,
        pages=[*config["pages"], page("Formations")],
    )

    titres = [p["titre"] for p in public(api_client, "en")["pages"]]

    assert titres == ["[en] Tarifs", "[en] Formations"]


@pytest.mark.django_db
def test_renommer_une_page_refait_son_titre(
    api_client, salon_pro, django_capture_on_commit_callbacks
):
    config = publier(
        api_client, salon_pro, django_capture_on_commit_callbacks, pages=[page("Tarifs")]
    )
    renommee = {**config["pages"][0], "titre": "Nos tarifs"}
    publier(api_client, salon_pro, django_capture_on_commit_callbacks, pages=[renommee])

    assert public(api_client, "en")["pages"][0]["titre"] == "[en] Nos tarifs"


@pytest.mark.django_db
def test_sans_traduction_la_page_reste_en_francais(api_client, salon_pro):
    """Traducteur en panne ou tache pas encore passee : jamais un blanc."""
    api_client.force_login(salon_pro.owner)
    api_client.put(URL, {"pages": [page("Tarifs")]}, format="json")

    anglais = public(api_client, "en")

    assert anglais["pages"][0]["titre"] == "Tarifs"
    assert anglais["pages"][0]["contenu"] == "Premier.\n\nSecond."


@pytest.mark.django_db
def test_une_page_retiree_n_encombre_plus_la_table(
    api_client, salon_pro, django_capture_on_commit_callbacks
):
    config = publier(
        api_client,
        salon_pro,
        django_capture_on_commit_callbacks,
        pages=[page("Tarifs"), page("Formations")],
    )
    gardee, retiree = config["pages"]
    publier(api_client, salon_pro, django_capture_on_commit_callbacks, pages=[gardee])

    with as_tenant(salon_pro.tenant):
        champs = set(Translation.objects.values_list("field", flat=True))

    assert f"page.{gardee['id']}.titre" in champs
    assert not any(retiree["id"] in champ for champ in champs)


@pytest.mark.django_db
def test_une_correction_du_salon_sur_une_page_survit(
    api_client, salon_pro, django_capture_on_commit_callbacks
):
    config = publier(
        api_client, salon_pro, django_capture_on_commit_callbacks, pages=[page("Tarifs")]
    )
    champ = f"page.{config['pages'][0]['id']}.titre"
    with as_tenant(salon_pro.tenant):
        Translation.objects.filter(field=champ).update(text="Prices", origin=Origin.SALON)
        traduire(SalonProfile.objects.get(), "en")

    assert public(api_client, "en")["pages"][0]["titre"] == "Prices"


@pytest.mark.django_db
def test_le_menu_d_un_autre_salon_ne_reprend_pas_ces_titres(
    api_client, salon_pro, salon_b, django_capture_on_commit_callbacks
):
    """Les champs virtuels sont rattaches a la fiche, donc au salon (RLS)."""
    publier(api_client, salon_pro, django_capture_on_commit_callbacks, pages=[page("Tarifs")])

    with as_tenant(salon_b.tenant):
        assert not Translation.objects.filter(field__startswith="page.").exists()
