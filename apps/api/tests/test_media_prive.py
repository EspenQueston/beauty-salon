"""Les preuves de versement ne sortent que par la porte gardee.

---------------------------------------------------------------------------
Ce qu'on protege
---------------------------------------------------------------------------

Une capture d'ecran de paiement porte le nom de la cliente, l'heure du
versement, parfois le solde du compte. C'est la piece la plus sensible de
toute la reserve de medias.

Elle etait rangee en `visibility=private`, ce qui la tenait hors de la
vitrine et hors de la mediatheque du salon — mais le fichier restait servi a
une adresse publique, protegee par les seuls 244 bits de deux UUID. Une
adresse indevinable reste une adresse : elle se partage, se copie, se
retrouve dans le journal d'un proxy. Et rien ne permet de la revoquer.

Ces tests verifient les quatre affirmations sur lesquelles repose la
correction : le fichier change de racine, l'adresse publiee est celle de la
route gardee, un inconnu n'entre pas, et un salon voisin non plus.
"""

import io

import pytest
from PIL import Image

from apps.media.models import MediaAsset
from apps.payments.models import DepositProof, PaymentChannel
from conftest import as_tenant, salon_host
from tests.factories import MembershipFactory, UserFactory
from tests.test_dashboard_api import make_booking

HOST = {"Host": salon_host("blondrose")}
PASSWORD = "motdepasse-solide"


def png_reel() -> io.BytesIO:
    """Une vraie image : DRF l'ouvre avec Pillow, un octet quelconque echoue."""
    tampon = io.BytesIO()
    Image.new("RGB", (8, 8), "white").save(tampon, format="PNG")
    tampon.name = "capture.png"
    tampon.seek(0)
    return tampon


def capture_privee(salon) -> MediaAsset:
    """Une preuve de versement, rangee comme le fait la vraie route."""
    with as_tenant(salon.tenant):
        from django.core.files.base import ContentFile

        return MediaAsset.objects.create(
            tenant=salon.tenant,
            file=ContentFile(png_reel().getvalue(), name="capture.png"),
            content_type="image/png",
            kind=MediaAsset.Kind.PROOF,
            visibility=MediaAsset.Visibility.PRIVATE,
        )


def photo_publique(salon) -> MediaAsset:
    with as_tenant(salon.tenant):
        from django.core.files.base import ContentFile

        return MediaAsset.objects.create(
            tenant=salon.tenant,
            file=ContentFile(png_reel().getvalue(), name="coiffure.png"),
            content_type="image/png",
            kind=MediaAsset.Kind.GALLERY,
            visibility=MediaAsset.Visibility.PUBLIC,
        )


# ---------------------------------------------------------------------------
# Le rangement sur disque
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_une_piece_privee_quitte_la_racine_publique(salon_a):
    """C'est ce qui permet au serveur web de la refuser d'une seule regle."""
    asset = capture_privee(salon_a)

    assert asset.file.name.startswith("prive/")
    assert str(salon_a.tenant.id) in asset.file.name


@pytest.mark.django_db
def test_une_photo_publique_reste_a_sa_place(salon_a):
    """Le changement ne doit toucher que le prive : une vitrine servie par
    une route authentifiee ne s'afficherait plus pour personne."""
    asset = photo_publique(salon_a)

    assert not asset.file.name.startswith("prive/")


# ---------------------------------------------------------------------------
# L'adresse publiee
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_le_salon_recoit_l_adresse_gardee_et_non_celle_du_fichier(
    api_client, salon_a
):
    from tests.test_dashboard_api import login

    asset = capture_privee(salon_a)
    booking = make_booking(salon_a)
    with as_tenant(salon_a.tenant):
        DepositProof.objects.create(
            tenant=salon_a.tenant,
            booking=booking,
            image=asset,
            channel=PaymentChannel.Kind.WECHAT,
        )

    login(api_client, salon_a.owner)
    reponse = api_client.get(f"/api/v1/bookings/{booking.id}/")

    adresse = reponse.data["deposit_proof"]["image_url"]
    assert f"/api/v1/media/{asset.id}/fichier" in adresse
    # L'adresse du fichier ne doit apparaitre nulle part : la publier une
    # seule fois suffit a la faire fuir.
    assert "/media/prive/" not in adresse


# ---------------------------------------------------------------------------
# Qui peut lire
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_un_inconnu_n_obtient_rien(api_client, salon_a):
    asset = capture_privee(salon_a)

    reponse = api_client.get(f"/api/v1/media/{asset.id}/fichier", headers=HOST)

    assert reponse.status_code in (401, 403)


@pytest.mark.django_db
def test_le_salon_voisin_n_obtient_rien(api_client, salon_a, salon_b):
    """Et il obtient 404, pas 403 : repondre « interdit » confirmerait qu'un
    media porte bien cet identifiant ailleurs sur la plateforme."""
    from tests.test_dashboard_api import login

    asset = capture_privee(salon_a)
    login(api_client, salon_b.owner)

    reponse = api_client.get(f"/api/v1/media/{asset.id}/fichier")

    assert reponse.status_code == 404


@pytest.mark.django_db
def test_l_equipe_du_salon_lit_la_capture(api_client, salon_a):
    """La reception encaisse au comptoir : elle doit pouvoir retrouver un
    versement, sans pour autant pouvoir modifier la mediatheque."""
    from apps.accounts.models import Membership
    from tests.test_dashboard_api import login

    asset = capture_privee(salon_a)
    receptionniste = UserFactory()
    MembershipFactory(
        tenant=salon_a.tenant,
        user=receptionniste,
        role=Membership.Role.RECEPTIONIST,
    )
    login(api_client, receptionniste)

    reponse = api_client.get(f"/api/v1/media/{asset.id}/fichier")

    assert reponse.status_code == 200
    assert reponse["Content-Type"] == "image/png"
    # Le navigateur s'en tient au type declare, et aucun cache partage ne
    # garde la piece.
    assert reponse["X-Content-Type-Options"] == "nosniff"
    assert "no-store" in reponse["Cache-Control"]
    assert b"".join(reponse.streaming_content)[:8] == b"\x89PNG\r\n\x1a\n"


@pytest.mark.django_db
def test_la_porte_gardee_sert_aussi_le_public(api_client, salon_a):
    """Elle ne restreint pas ce qui etait deja ouvert : la meme route sert un
    media public a un membre, sans quoi un appelant devrait savoir quelle
    adresse utiliser selon la visibilite."""
    from tests.test_dashboard_api import login

    asset = photo_publique(salon_a)
    login(api_client, salon_a.owner)

    reponse = api_client.get(f"/api/v1/media/{asset.id}/fichier")

    assert reponse.status_code == 200


# ---------------------------------------------------------------------------
# La porte de service reste fermee
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_le_chemin_direct_du_fichier_prive_est_refuse(api_client, salon_a, settings):
    """En developpement, Django sert lui-meme MEDIA_ROOT. `prive/` doit en
    etre exclu, sinon la correction ne vaut que pour la production."""
    asset = capture_privee(salon_a)

    reponse = api_client.get(f"/media/{asset.file.name}")

    assert reponse.status_code == 404


@pytest.mark.django_db
def test_une_ligne_sans_fichier_ne_fait_pas_tomber_la_route(api_client, salon_a):
    """Un fichier efface du stockage alors que la ligne subsiste : on rend
    404, pas une trace d'exception contenant le chemin sur disque."""
    from tests.test_dashboard_api import login

    asset = capture_privee(salon_a)
    asset.file.storage.delete(asset.file.name)

    login(api_client, salon_a.owner)
    reponse = api_client.get(f"/api/v1/media/{asset.id}/fichier")

    assert reponse.status_code == 404


@pytest.mark.django_db
def test_un_identifiant_inconnu_rend_404(api_client, salon_a):
    from tests.test_dashboard_api import login

    login(api_client, salon_a.owner)
    reponse = api_client.get(
        "/api/v1/media/00000000-0000-4000-8000-000000000000/fichier"
    )

    assert reponse.status_code == 404


@pytest.mark.django_db
def test_toute_reservation_du_salon_reste_lisible(api_client, salon_a):
    """Garde-fou de non-regression : la fiche rendez-vous continue de se
    charger quand aucune preuve n'existe."""
    from tests.test_dashboard_api import login

    booking = make_booking(salon_a)

    login(api_client, salon_a.owner)
    reponse = api_client.get(f"/api/v1/bookings/{booking.id}/")

    assert reponse.status_code == 200
    assert reponse.data["deposit_proof"] is None
