"""Apparence avancee : polices etendues et pages du salon (au plus trois)."""

import pytest
from django.core.files.base import ContentFile

from apps.media.models import MediaAsset
from conftest import as_tenant
from tests.test_abonnements import medias_temporaires, offres
from tests.test_assistants_pro import HOTE, salon_pro
from tests.test_offres_pro import pro

FIXTURES_PARTAGEES = (medias_temporaires, offres, pro, salon_pro)
URL = "/api/v1/site-pro"


def page(titre="Tarifs", **extra):
    return {"titre": titre, "accroche": "", "contenu": "Premier.\n\nSecond.", **extra}


def media(salon, *, kind=MediaAsset.Kind.ABOUT, visibility=MediaAsset.Visibility.PUBLIC):
    with as_tenant(salon.tenant):
        asset = MediaAsset(tenant=salon.tenant, kind=kind, visibility=visibility)
        asset.file.save("page.txt", ContentFile(b"image"), save=True)
    return asset


@pytest.mark.django_db
def test_une_police_manuscrite_va_aux_titres_pas_au_texte(api_client, salon_pro):
    api_client.force_login(salon_pro.owner)

    titres = api_client.put(URL, {"police_titres": "great-vibes"}, format="json")
    texte = api_client.put(URL, {"police_texte": "great-vibes"}, format="json")

    assert titres.status_code == 200
    assert texte.status_code == 400
    polices = {p["cle"]: p for p in titres.json()["options"]["polices"]}
    assert len(polices) >= 20 and polices["great-vibes"]["texte"] is False


@pytest.mark.django_db
def test_trois_pages_au_plus_et_chacune_rejoint_le_menu(api_client, salon_pro):
    api_client.force_login(salon_pro.owner)

    quatre = api_client.put(URL, {"pages": [page(f"Page {i}") for i in range(4)]}, format="json")
    trois = api_client.put(
        URL, {"pages": [page("Tarifs"), page("Tarifs"), page("Événements")]}, format="json"
    )

    assert quatre.status_code == 400
    assert trois.status_code == 200, trois.json()
    config = trois.json()["config"]
    assert [p["slug"] for p in config["pages"]] == ["tarifs", "tarifs-2", "evenements"]
    assert config["pages"][0]["contenu"] == "Premier.\n\nSecond."
    menu = [entree["cle"] for entree in config["menu"]]
    for p in config["pages"]:
        assert f"page:{p['id']}" in menu


@pytest.mark.django_db
def test_retirer_une_page_retire_son_entree_de_menu(api_client, salon_pro):
    api_client.force_login(salon_pro.owner)
    config = api_client.put(URL, {"pages": [page()]}, format="json").json()["config"]

    sans = api_client.put(URL, {"pages": [], "menu": config["menu"]}, format="json")

    assert sans.status_code == 200
    assert not any(e["cle"].startswith("page:") for e in sans.json()["config"]["menu"])


@pytest.mark.django_db
@pytest.mark.parametrize(
    "mauvaise",
    [
        page(titre="<b>x</b>"),
        page(contenu="<script>alert(1)</script>"),
        page(titre="x"),
        page(contenu="x" * 5000),
        page(id="../../etc"),
        page(image="pas-un-uuid"),
    ],
)
def test_une_page_hors_des_regles_est_refusee(api_client, salon_pro, mauvaise):
    api_client.force_login(salon_pro.owner)

    assert api_client.put(URL, {"pages": [mauvaise]}, format="json").status_code == 400


@pytest.mark.django_db
def test_l_image_d_une_page_vient_des_medias_publics_du_salon(api_client, salon_pro, salon_b):
    api_client.force_login(salon_pro.owner)
    voisine = media(salon_b)
    preuve = media(salon_pro, kind=MediaAsset.Kind.PROOF, visibility=MediaAsset.Visibility.PRIVATE)
    bonne = media(salon_pro)

    for interdite in (voisine, preuve):
        reponse = api_client.put(URL, {"pages": [page(image=str(interdite.id))]}, format="json")
        assert reponse.status_code == 400, interdite.kind

    ajout = api_client.put(URL, {"pages": [page(image=str(bonne.id))]}, format="json")
    assert ajout.status_code == 200
    public = api_client.get("/api/v1/public/salon", **HOTE).json()["site_config"]
    assert str(bonne.id) in public["pages"][0]["image"]["url"]


@pytest.mark.django_db
def test_sans_pro_les_pages_ne_sont_plus_publiees(api_client, salon_pro):
    from datetime import timedelta

    from django.utils import timezone

    from tests.test_offres_pro import au_plan

    api_client.force_login(salon_pro.owner)
    api_client.put(URL, {"pages": [page()]}, format="json")

    au_plan(salon_pro, "monthly", fin=timezone.now() + timedelta(days=20))

    assert api_client.get("/api/v1/public/salon", **HOTE).json()["site_config"] is None
    # Gardees pour le retour a Pro.
    assert api_client.get(URL).json()["config"]["pages"][0]["titre"] == "Tarifs"
