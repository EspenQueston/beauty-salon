"""Realisations reliees a une prestation et a une prestataire.

Une photo de la galerie peut dire ce qu'elle montre (une prestation) et qui
l'a faite (une prestataire). Le mini-site en tire « Reserver ce look », des
filtres par categorie et la signature de l'artiste.
"""

import pytest
from django.core.files.base import ContentFile

from apps.media.models import MediaAsset
from conftest import as_tenant, salon_host

HOST = {"Host": salon_host("blondrose")}


@pytest.fixture(autouse=True)
def medias_temporaires(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


def photo(salon, **champs) -> MediaAsset:
    with as_tenant(salon.tenant):
        return MediaAsset.objects.create(
            tenant=salon.tenant,
            file=ContentFile(b"x", name="tresses.jpg"),
            content_type="image/jpeg",
            kind=MediaAsset.Kind.GALLERY,
            **champs,
        )


def realisations(api_client):
    return api_client.get("/api/v1/public/salon", headers=HOST).json()["gallery"]


@pytest.mark.django_db
def test_la_galerie_dit_ce_que_montre_la_photo_et_qui_l_a_faite(api_client, salon_a):
    photo(salon_a, service=salon_a.service, staff_member=salon_a.staff)

    [publiee] = realisations(api_client)

    assert publiee["prestation"]["id"] == str(salon_a.service.id)
    assert publiee["prestation"]["nom"] == "Tresses"
    assert publiee["prestation"]["categorie"] == "Coiffure"
    assert publiee["prestation"]["duree"] == 120
    assert publiee["prestataire"] == {"id": str(salon_a.staff.id), "nom": "Fatou"}


@pytest.mark.django_db
def test_une_photo_sans_lien_reste_une_simple_photo(api_client, salon_a):
    photo(salon_a)

    [publiee] = realisations(api_client)

    assert publiee["prestation"] is None
    assert publiee["prestataire"] is None


@pytest.mark.django_db
def test_une_prestation_retiree_ne_se_propose_plus_a_la_reservation(api_client, salon_a):
    photo(salon_a, service=salon_a.service)
    with as_tenant(salon_a.tenant):
        salon_a.service.active = False
        salon_a.service.save(update_fields=["active"])

    [publiee] = realisations(api_client)

    assert publiee["prestation"] is None


@pytest.mark.django_db
def test_le_salon_relie_sa_photo_depuis_son_espace(api_client, salon_a):
    asset = photo(salon_a)
    api_client.force_login(salon_a.owner)

    reponse = api_client.patch(
        f"/api/v1/media/{asset.id}/",
        {"service": str(salon_a.service.id), "staff_member": str(salon_a.staff.id)},
        format="json",
    )

    assert reponse.status_code == 200, reponse.data
    assert reponse.data["service"] == salon_a.service.id
    with as_tenant(salon_a.tenant):
        asset.refresh_from_db()
    assert asset.staff_member_id == salon_a.staff.id


@pytest.mark.django_db
def test_on_ne_relie_pas_une_photo_a_la_prestation_d_un_autre_salon(api_client, salon_a, salon_b):
    asset = photo(salon_a)
    api_client.force_login(salon_a.owner)

    reponse = api_client.patch(
        f"/api/v1/media/{asset.id}/", {"service": str(salon_b.service.id)}, format="json"
    )

    assert reponse.status_code == 400
    with as_tenant(salon_a.tenant):
        asset.refresh_from_db()
    assert asset.service_id is None


@pytest.mark.django_db
def test_supprimer_la_prestation_garde_la_photo(api_client, salon_a):
    asset = photo(salon_a, service=salon_a.service)
    with as_tenant(salon_a.tenant):
        from tests.factories import ServiceFactory

        nouvelle = ServiceFactory(tenant=salon_a.tenant, category=salon_a.category, name="Ephemere")
        MediaAsset.objects.filter(pk=asset.pk).update(service=nouvelle)
        nouvelle.delete()
        asset.refresh_from_db()

    assert asset.service_id is None
