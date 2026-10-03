"""Des notifications qui ressemblent a des notifications.

Le push portait un titre, un texte et l'icone de la plateforme. Il porte
desormais une grande image, le logo du salon, des boutons et l'heure de
l'evenement. Ces tests tiennent ce que le telephone ne montrera jamais s'il
manque : l'ordre dans lequel on cherche l'image, l'absence de toute image
privee, les destinations des boutons, et la notification d'essai.
"""

import io
from datetime import timedelta

import pytest
from django.core.files.base import ContentFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.media.models import MediaAsset
from apps.notifications import evenements, habillage, push
from apps.notifications.models import Genre, PushSubscription
from apps.notifications.service import prevenir_plateforme, prevenir_salon
from conftest import as_tenant
from tests.factories import BookingFactory

PASSWORD = "motdepasse-solide"
ENDPOINT = "https://fcm.googleapis.com/fcm/send/jeton-essai-1"
VAPID = {"VAPID_PUBLIC_KEY": "cle-publique", "VAPID_PRIVATE_KEY": "cle-privee"}


@pytest.fixture(autouse=True)
def medias_temporaires(settings, tmp_path):
    """Les images de test ne doivent pas atterrir dans le vrai dossier media."""
    settings.MEDIA_ROOT = tmp_path


def media(salon, *, visibilite=MediaAsset.Visibility.PUBLIC, nom="photo.png") -> MediaAsset:
    tampon = io.BytesIO()
    Image.new("RGB", (8, 8), "white").save(tampon, format="PNG")
    with as_tenant(salon.tenant):
        return MediaAsset.objects.create(
            tenant=salon.tenant,
            file=ContentFile(tampon.getvalue(), name=nom),
            content_type="image/png",
            kind=(
                MediaAsset.Kind.PROOF
                if visibilite == MediaAsset.Visibility.PRIVATE
                else MediaAsset.Kind.GALLERY
            ),
            visibility=visibilite,
        )


@pytest.fixture
def charges(monkeypatch):
    """Ce qui serait parti vers les appareils, sans rien envoyer."""
    from apps.notifications import tasks

    capturees = []
    monkeypatch.setattr(
        tasks.pousser_notification,
        "delay",
        lambda comptes, portee, charge: capturees.append(charge),
    )
    return capturees


def pousser(django_capture_on_commit_callbacks, fonction, *args, **kwargs):
    with django_capture_on_commit_callbacks(execute=True):
        fonction(*args, **kwargs)


# ---------------------------------------------------------------------------
# Les adresses d'image
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@override_settings(API_BASE_URL="http://localhost:8001")
def test_une_image_publique_a_une_adresse_absolue(salon_a):
    """Le systeme affiche la notification hors de toute page : une adresse
    relative n'y designe rien."""
    adresse = habillage.url_publique(media(salon_a))

    assert adresse.startswith("http://localhost:8001/media/")


@pytest.mark.django_db
def test_une_preuve_de_versement_n_a_jamais_d_adresse(salon_a):
    """Elle n'a rien a faire sur un ecran verrouille."""
    preuve = media(salon_a, visibilite=MediaAsset.Visibility.PRIVATE, nom="preuve.png")

    assert habillage.url_publique(preuve) == ""
    assert habillage.url_publique(None) == ""


def test_l_image_composee_porte_le_genre_le_salon_et_sa_couleur():
    adresse = habillage.image_composee(Genre.AVIS, "Blond Rose & Co", "#8B5CF6")

    assert "/notification-image/avis?" in adresse
    assert "salon=Blond+Rose+%26+Co" in adresse
    assert "couleur=8B5CF6" in adresse


def test_un_genre_inconnu_n_a_pas_d_image_composee():
    assert habillage.image_composee("inconnu", "Salon", "#000000") == ""


# ---------------------------------------------------------------------------
# L'ordre de l'image : photo de l'evenement, banniere, image composee
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_sans_photo_ni_banniere_l_image_est_composee(
    salon_a, charges, django_capture_on_commit_callbacks
):
    pousser(
        django_capture_on_commit_callbacks,
        prevenir_salon,
        salon_a.tenant.id,
        genre=Genre.AVIS,
        titre="Nouvel avis",
        lien="/avis",
    )

    (charge,) = charges
    assert "/notification-image/avis?" in charge["image"]
    assert "salon=Blond+Rose" in charge["image"]


@pytest.mark.django_db
def test_la_banniere_du_salon_passe_avant_l_image_composee(
    salon_a, charges, django_capture_on_commit_callbacks
):
    banniere = media(salon_a, nom="banniere.png")
    with as_tenant(salon_a.tenant):
        salon_a.profile.banner = banniere
        salon_a.profile.save(update_fields=["banner"])

    pousser(
        django_capture_on_commit_callbacks,
        prevenir_salon,
        salon_a.tenant.id,
        genre=Genre.AVIS,
        titre="Nouvel avis",
        lien="/avis",
    )

    (charge,) = charges
    assert charge["image"].endswith(banniere.file.name.split("/")[-1])


@pytest.mark.django_db
def test_la_photo_de_la_prestation_passe_avant_tout(
    salon_a, charges, django_capture_on_commit_callbacks
):
    photo = media(salon_a, nom="tresses.png")
    with as_tenant(salon_a.tenant):
        salon_a.profile.banner = media(salon_a, nom="banniere.png")
        salon_a.profile.save(update_fields=["banner"])
        salon_a.service.image = photo
        salon_a.service.save(update_fields=["image"])
        debut = timezone.now() + timedelta(days=2)
        reservation = BookingFactory(
            tenant=salon_a.tenant,
            service=salon_a.service,
            staff_member=salon_a.staff,
            customer=salon_a.customer,
            starts_at=debut,
            ends_at=debut + timedelta(minutes=120),
        )

        with django_capture_on_commit_callbacks(execute=True):
            evenements.nouvelle_reservation(reservation)

    (charge,) = charges
    assert charge["image"].endswith("tresses.png")


@pytest.mark.django_db
def test_le_logo_du_salon_sert_d_icone(salon_a, charges, django_capture_on_commit_callbacks):
    logo = media(salon_a, nom="logo.png")
    with as_tenant(salon_a.tenant):
        salon_a.profile.logo = logo
        salon_a.profile.save(update_fields=["logo"])

    pousser(
        django_capture_on_commit_callbacks,
        prevenir_salon,
        salon_a.tenant.id,
        genre=Genre.AVIS,
        titre="Nouvel avis",
        lien="/avis",
    )

    (charge,) = charges
    assert charge["icone"].endswith("logo.png")


@pytest.mark.django_db
def test_un_logo_prive_n_est_jamais_envoye(salon_a, charges, django_capture_on_commit_callbacks):
    """Un media prive rattache par erreur au profil ne doit pas fuir."""
    with as_tenant(salon_a.tenant):
        salon_a.profile.logo = media(
            salon_a, visibilite=MediaAsset.Visibility.PRIVATE, nom="prive.png"
        )
        salon_a.profile.save(update_fields=["logo"])

    pousser(
        django_capture_on_commit_callbacks,
        prevenir_salon,
        salon_a.tenant.id,
        genre=Genre.AVIS,
        titre="Nouvel avis",
        lien="/avis",
    )

    (charge,) = charges
    assert charge["icone"] == ""
    assert "prive" not in charge["image"]


# ---------------------------------------------------------------------------
# Boutons et heure
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_une_reservation_porte_deux_boutons_qui_menent_quelque_part(
    salon_a, charges, django_capture_on_commit_callbacks
):
    pousser(
        django_capture_on_commit_callbacks,
        prevenir_salon,
        salon_a.tenant.id,
        genre=Genre.RESERVATION,
        titre="Awa a réservé",
        lien="/agenda?rdv=42",
    )

    (charge,) = charges
    assert charge["actions"] == [
        {"id": "ouvrir", "titre": "Voir le rendez-vous", "lien": "/agenda?rdv=42"},
        {"id": "agenda", "titre": "Ouvrir l'agenda", "lien": "/agenda"},
    ]
    assert isinstance(charge["horodatage"], int)
    # Des millisecondes, comme l'attend `Notification.timestamp`.
    assert charge["horodatage"] > 1_700_000_000_000


def test_chaque_genre_a_au_moins_un_bouton():
    for genre in Genre.values:
        assert habillage.actions(genre, "/quelque-part"), genre


def test_sans_lien_aucun_bouton_ne_mene_nulle_part():
    assert habillage.actions(Genre.AVIS, "") == []
    # Le bouton « agenda » a sa propre destination et reste propose.
    assert [a["id"] for a in habillage.actions(Genre.RESERVATION, "")] == ["agenda"]


def test_les_libelles_tiennent_dans_un_bouton():
    """Windows coupe les boutons au-dela d'une vingtaine de caracteres."""
    for boutons in habillage.ACTIONS.values():
        for _, titre, _ in boutons:
            assert len(titre) <= 20, titre


@pytest.mark.django_db
def test_la_plateforme_recoit_le_logo_du_salon_et_un_lien_vers_sa_fiche(
    salon_a, charges, django_capture_on_commit_callbacks
):
    from tests.factories import UserFactory

    UserFactory(is_platform_admin=True)
    with as_tenant(salon_a.tenant):
        salon_a.profile.logo = media(salon_a, nom="logo.png")
        salon_a.profile.save(update_fields=["logo"])

    with django_capture_on_commit_callbacks(execute=True):
        evenements.salon_inscrit(salon_a.tenant)

    (charge,) = charges
    assert charge["icone"].endswith("logo.png")
    fiche = reverse("admin:tenants_tenant_change", args=[salon_a.tenant.id])
    assert charge["lien"] == fiche
    assert charge["actions"][0]["lien"] == fiche


@pytest.mark.django_db
def test_une_apparence_illisible_n_empeche_pas_la_notification(
    salon_a, charges, monkeypatch, django_capture_on_commit_callbacks
):
    from tests.factories import UserFactory

    UserFactory(is_platform_admin=True)

    def en_panne(tenant_id):
        raise RuntimeError("profil illisible")

    monkeypatch.setattr(habillage, "apparence", en_panne)

    pousser(
        django_capture_on_commit_callbacks,
        prevenir_salon,
        salon_a.tenant.id,
        genre=Genre.AVIS,
        titre="Nouvel avis",
        lien="/avis",
    )
    pousser(
        django_capture_on_commit_callbacks,
        prevenir_plateforme,
        genre=Genre.SALON_INSCRIT,
        titre="Nouveau salon",
        tenant_id=salon_a.tenant.id,
    )

    salon, plateforme = charges
    assert salon["titre"] == "Nouvel avis" and plateforme["titre"] == "Nouveau salon"
    # Plus sobres, mais parties : sans logo, avec l'image composee par defaut.
    assert salon["icone"] == "" and plateforme["icone"] == ""
    assert "/notification-image/avis?" in salon["image"]


# ---------------------------------------------------------------------------
# Le depot
# ---------------------------------------------------------------------------


@override_settings(**VAPID)
def test_un_depot_ne_peut_pas_attendre_indefiniment(monkeypatch):
    """Sans delai, un service de push muet retiendrait un processus du worker
    — et tous les e-mails en file derriere lui."""
    recu = {}
    monkeypatch.setattr(push, "webpush", lambda **kwargs: recu.update(kwargs))

    class Abonnement:
        endpoint = ENDPOINT
        cle_p256dh = "cle"
        cle_auth = "auth"

    push.envoyer(Abonnement(), {"titre": "x"})

    assert recu["timeout"] == push.DELAI
    assert 0 < push.DELAI <= 30


# ---------------------------------------------------------------------------
# La notification d'essai
# ---------------------------------------------------------------------------


def connecter(client, salon):
    salon.owner.set_password(PASSWORD)
    salon.owner.save()
    assert client.login(email=salon.owner.email, password=PASSWORD)
    return client


URL_ESSAI = "/api/v1/notifications/essai"


@pytest.mark.django_db
def test_sans_cles_vapid_l_essai_le_dit(client, salon_a):
    connecter(client, salon_a)
    with override_settings(VAPID_PUBLIC_KEY="", VAPID_PRIVATE_KEY=""):
        reponse = client.post(URL_ESSAI)

    assert reponse.status_code == 409


@pytest.mark.django_db
@override_settings(**VAPID)
def test_sans_appareil_l_essai_le_dit(client, salon_a):
    connecter(client, salon_a)

    reponse = client.post(URL_ESSAI)

    assert reponse.status_code == 409
    assert "appareil" in reponse.json()["detail"]


@pytest.mark.django_db
@override_settings(**VAPID)
def test_l_essai_part_vers_mes_appareils_et_seulement_les_miens(
    client, salon_a, monkeypatch
):
    from tests.factories import MembershipFactory, UserFactory

    mien = PushSubscription.objects.create(
        user=salon_a.owner, endpoint=ENDPOINT, cle_p256dh="c", cle_auth="a"
    )
    collegue = UserFactory()
    MembershipFactory(tenant=salon_a.tenant, user=collegue)
    PushSubscription.objects.create(
        user=collegue, endpoint=ENDPOINT.replace("-1", "-2"), cle_p256dh="c", cle_auth="a"
    )

    servis = []

    def envoyer(abonnement, charge):
        servis.append((abonnement.pk, charge))
        return True

    monkeypatch.setattr(push, "envoyer", envoyer)
    connecter(client, salon_a)

    reponse = client.post(URL_ESSAI)

    assert reponse.status_code == 200
    assert reponse.json()["envoyes"] == 1
    ((cible, charge),) = servis
    assert cible == mien.pk
    # Un essai se dit essai, et montre une vraie prestation du salon.
    assert charge["titre"].startswith("Essai")
    assert "Tresses" in charge["corps"]
    assert charge["actions"] and charge["image"]


@pytest.mark.django_db
@override_settings(**VAPID)
def test_un_appareil_disparu_est_retire_pendant_l_essai(client, salon_a, monkeypatch):
    abonnement = PushSubscription.objects.create(
        user=salon_a.owner, endpoint=ENDPOINT, cle_p256dh="c", cle_auth="a"
    )
    monkeypatch.setattr(push, "envoyer", lambda *a, **k: False)
    connecter(client, salon_a)

    reponse = client.post(URL_ESSAI)

    assert reponse.json() == {"envoyes": 0, "echecs": 0, "retires": 1}
    assert not PushSubscription.objects.filter(pk=abonnement.pk).exists()


@pytest.mark.django_db
@override_settings(**VAPID)
def test_l_essai_ne_remplit_pas_la_cloche(client, salon_a, monkeypatch):
    """Un essai n'est pas un evenement : rien a relire demain."""
    from apps.notifications.models import Notification

    PushSubscription.objects.create(
        user=salon_a.owner, endpoint=ENDPOINT, cle_p256dh="c", cle_auth="a"
    )
    monkeypatch.setattr(push, "envoyer", lambda *a, **k: True)
    connecter(client, salon_a)

    client.post(URL_ESSAI)

    with as_tenant(salon_a.tenant):
        assert not Notification.objects.exists()


@pytest.mark.django_db
def test_l_essai_demande_une_session(client):
    assert client.post(URL_ESSAI).status_code in (401, 403)
