"""Le mini-site recoit les copies reduites de chaque photo.

Sans elles, une vignette de 170 pixels telechargeait l'original — jusqu'a
1600 x 2400. L'API publie donc, pour chaque photo, ses copies WebP par
largeur ; le mini-site en tire un `srcset`.
"""

import pytest
from django.core.files.base import ContentFile

from apps.media.models import MediaAsset
from conftest import as_tenant, salon_host


@pytest.fixture(autouse=True)
def medias_temporaires(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


def _logo(salon, derives):
    with as_tenant(salon.tenant):
        asset = MediaAsset.objects.create(
            tenant=salon.tenant,
            file=ContentFile(b"x", name="logo.png"),
            content_type="image/png",
            kind=MediaAsset.Kind.LOGO,
            width=1600,
            height=1600,
            derivatives=derives,
        )
        salon.profile.logo = asset
        salon.profile.save(update_fields=["logo"])
    return asset


@pytest.mark.django_db
def test_les_copies_reduites_sont_publiees_par_largeur(api_client, salon_a):
    base = f"tenants/{salon_a.tenant.id}/media/x"
    _logo(salon_a, {"sm": f"{base}/sm.webp", "md": f"{base}/md.webp"})

    logo = api_client.get(
        "/api/v1/public/salon", HTTP_HOST=salon_host("blondrose")
    ).json()["logo"]

    assert set(logo["variants"]) == {"480", "1024"}
    assert logo["variants"]["480"].endswith("/sm.webp")
    assert logo["variants"]["1024"].endswith("/md.webp")


@pytest.mark.django_db
def test_une_photo_sans_copie_n_annonce_rien(api_client, salon_a):
    _logo(salon_a, {})

    logo = api_client.get(
        "/api/v1/public/salon", HTTP_HOST=salon_host("blondrose")
    ).json()["logo"]

    assert logo["variants"] == {}


# ---------------------------------------------------------------------------
# L'e-mail de contact du mini-site
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_l_email_de_contact_est_publie_quand_le_salon_le_donne(api_client, salon_a):
    hote = {"HTTP_HOST": salon_host("blondrose")}
    assert api_client.get("/api/v1/public/salon", **hote).json()["contact_email"] == ""

    api_client.force_login(salon_a.owner)
    reponse = api_client.patch(
        "/api/v1/salon-profile", {"contact_email": "contact@blondrose.com"}, format="json"
    )
    assert reponse.status_code == 200, reponse.json()
    api_client.logout()

    assert (
        api_client.get("/api/v1/public/salon", **hote).json()["contact_email"]
        == "contact@blondrose.com"
    )


@pytest.mark.django_db
def test_un_email_de_contact_invalide_est_refuse(api_client, salon_a):
    api_client.force_login(salon_a.owner)

    reponse = api_client.patch(
        "/api/v1/salon-profile", {"contact_email": "pas-un-email"}, format="json"
    )

    assert reponse.status_code == 400


@pytest.mark.django_db
def test_un_nouveau_salon_publie_l_adresse_de_son_inscription(api_client):
    from apps.accounts.services import signup_salon
    from apps.salons.models import SalonProfile

    tenant, _ = signup_salon(
        name="Chez Awa", slug="chezawa", email="Awa@Example.com", password="motdepasse-solide-9"
    )

    with as_tenant(tenant):
        assert SalonProfile.objects.get().contact_email == "awa@example.com"
