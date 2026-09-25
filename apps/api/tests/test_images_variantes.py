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
