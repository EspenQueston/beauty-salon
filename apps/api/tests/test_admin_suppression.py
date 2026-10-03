"""Ce que l'administration plateforme a le droit d'effacer.

---------------------------------------------------------------------------
Pourquoi ces ecrans etaient fermes, et pourquoi ils s'ouvrent
---------------------------------------------------------------------------

Tout y etait en lecture seule, et c'etait la bonne prudence par defaut : ces
ecrans voient **tous** les salons. Mais l'equipe qui exploite la plateforme a
de vraies raisons d'effacer - une demande de suppression de compte, une
donnee de test restee en production, une image televersee par erreur. Sans
cette permission, la seule reponse etait « ouvrez un shell Django sur la
production », ce qui est infiniment plus dangereux.

Ces tests tiennent les trois garanties qui rendent l'ouverture acceptable :

  1. la suppression laisse une trace nominative ;
  2. supprimer un rendez-vous emporte ses ecritures comptables, au lieu de
     laisser une recette sans origine ;
  3. supprimer un media efface aussi le fichier - sinon « supprimer » ne
     supprime pas, et cette table porte les captures bancaires des clientes.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.files.base import ContentFile
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.catalog.models import Resource
from apps.finance.models import Transaction
from apps.media.models import MediaAsset
from apps.scheduling.models import Booking
from conftest import as_tenant
from tests.factories import UserFactory

PASSWORD = "motdepasse-solide"

pytestmark = pytest.mark.django_db(databases=["default", "admin"], transaction=True)


@pytest.fixture
def admin_client(client):
    UserFactory(
        email="supervision@example.com",
        password=PASSWORD,
        is_staff=True,
        is_superuser=True,
        is_platform_admin=True,
    )
    client.login(username="supervision@example.com", password=PASSWORD)
    return client


def un_rendez_vous(salon, avec_recette=True):
    debut = timezone.now() + timedelta(days=2)
    with as_tenant(salon.tenant):
        booking = Booking.objects.create(
            tenant=salon.tenant,
            customer=salon.customer,
            staff_member=salon.staff,
            service=salon.service,
            starts_at=debut,
            ends_at=debut + timedelta(hours=2),
            status=Booking.Status.CONFIRMED,
            service_name="Box braids",
            total_amount=Decimal("450"),
        )
        if avec_recette:
            Transaction.objects.create(
                tenant=salon.tenant,
                booking=booking,
                kind=Transaction.Kind.INCOME,
                amount=Decimal("450"),
                currency=salon.tenant.currency,
                occurred_on=timezone.localdate(),
            )
    return booking


# ---------------------------------------------------------------------------
# Les rendez-vous, et l'argent qui va avec
# ---------------------------------------------------------------------------


def test_supprimer_un_rendez_vous_emporte_ses_ecritures(admin_client, salon_a):
    """Sinon la recette survit sans origine.

    `Transaction.booking` est en SET_NULL : supprimer le rendez-vous seul
    aurait laisse un montant dans les comptes que plus rien ne justifie.
    C'est precisement ce qui faisait refuser la suppression ; on la fait
    maintenant des deux cotes.
    """
    booking = un_rendez_vous(salon_a)

    reponse = admin_client.post(
        reverse("admin:scheduling_booking_delete", args=[booking.pk]),
        {"post": "yes"},
        follow=True,
    )

    assert reponse.status_code == 200
    with as_tenant(salon_a.tenant):
        assert not Booking.objects.filter(pk=booking.pk).exists()
        assert not Transaction.objects.filter(booking_id=booking.pk).exists()
        # Et aucune recette orpheline n'est restee derriere.
        assert Transaction.objects.count() == 0


def test_la_page_de_confirmation_annonce_les_ecritures(admin_client, salon_a):
    """Django ne les montrerait pas : son collecteur ignore les mises a NULL.

    Confirmer une suppression sans savoir qu'elle emporte 450 de recette,
    c'est exactement ce qu'on ne veut pas d'un ecran d'administration.
    """
    booking = un_rendez_vous(salon_a)

    page = admin_client.get(
        reverse("admin:scheduling_booking_delete", args=[booking.pk])
    ).content.decode("utf-8")

    assert "Écritures comptables supprimées avec" in page
    assert "450" in page


def test_la_suppression_laisse_une_trace_nominative(admin_client, salon_a):
    booking = un_rendez_vous(salon_a, avec_recette=False)

    admin_client.post(
        reverse("admin:scheduling_booking_delete", args=[booking.pk]),
        {"post": "yes"},
        follow=True,
    )

    trace = AuditLog.objects.filter(
        action=AuditLog.Action.PLATFORM_DELETED,
        resource_id=str(booking.pk),
    ).first()
    assert trace is not None
    assert trace.actor_user.email == "supervision@example.com"
    assert trace.tenant_id == salon_a.tenant.id
    # L'objet ne sera plus la pour dire de qui il s'agissait : sa
    # representation est conservee.
    assert trace.metadata["objet"]


# ---------------------------------------------------------------------------
# La galerie : le fichier suit la ligne
# ---------------------------------------------------------------------------


def test_supprimer_un_media_efface_le_fichier(admin_client, salon_a):
    """« Supprimer » ne supprimait pas.

    La ligne partait, le fichier restait sur le disque - donc toujours servi
    a son adresse pour un media public. Cette table porte aussi les preuves
    de versement : le nom d'une cliente et parfois son solde bancaire.
    """
    import pathlib

    with as_tenant(salon_a.tenant):
        media = MediaAsset(tenant=salon_a.tenant, kind=MediaAsset.Kind.GALLERY)
        media.file.save("photo.txt", ContentFile(b"une photo"), save=True)
        chemin = pathlib.Path(media.file.path)

    assert chemin.exists()

    admin_client.post(
        reverse("admin:media_mediaasset_delete", args=[media.pk]),
        {"post": "yes"},
        follow=True,
    )

    with as_tenant(salon_a.tenant):
        assert not MediaAsset.objects.filter(pk=media.pk).exists()
    assert not chemin.exists()


def test_le_fichier_part_aussi_en_suppression_groupee(salon_a):
    """`queryset.delete()` n'appelle pas `Model.delete()`.

    C'est le chemin de l'administration quand on coche plusieurs lignes, et
    celui des cascades. Le nettoyage passe donc par un signal, pas par une
    methode du modele.
    """
    import pathlib

    with as_tenant(salon_a.tenant):
        premier = MediaAsset(tenant=salon_a.tenant, kind=MediaAsset.Kind.GALLERY)
        premier.file.save("a.txt", ContentFile(b"a"), save=True)
        second = MediaAsset(tenant=salon_a.tenant, kind=MediaAsset.Kind.GALLERY)
        second.file.save("b.txt", ContentFile(b"b"), save=True)
        chemins = [pathlib.Path(premier.file.path), pathlib.Path(second.file.path)]

        assert all(chemin.exists() for chemin in chemins)
        MediaAsset.objects.filter(pk__in=[premier.pk, second.pk]).delete()

    assert not any(chemin.exists() for chemin in chemins)


def test_un_fichier_deja_disparu_n_empeche_pas_la_suppression(salon_a):
    """Sinon la ligne devient ineffacable.

    Un fichier retire a la main, une restauration partielle, un disque
    remplace : la base garderait une reference vers un fichier absent, et
    plus personne ne pourrait s'en debarrasser.
    """
    import pathlib

    with as_tenant(salon_a.tenant):
        media = MediaAsset(tenant=salon_a.tenant, kind=MediaAsset.Kind.GALLERY)
        media.file.save("fantome.txt", ContentFile(b"x"), save=True)
        pathlib.Path(media.file.path).unlink()

        media.delete()
        assert not MediaAsset.objects.filter(pk=media.pk).exists()


# ---------------------------------------------------------------------------
# Ressources et prestations
# ---------------------------------------------------------------------------


def test_une_ressource_se_supprime(admin_client, salon_a):
    """Seul le lien prestation<->ressource pointe vers elle, et il part avec."""
    with as_tenant(salon_a.tenant):
        ressource = Resource.objects.create(
            tenant=salon_a.tenant, name="Bac 2", capacity=1
        )

    admin_client.post(
        reverse("admin:catalog_resource_delete", args=[ressource.pk]),
        {"post": "yes"},
        follow=True,
    )

    with as_tenant(salon_a.tenant):
        assert not Resource.objects.filter(pk=ressource.pk).exists()


def test_une_prestation_reservee_est_protegee(admin_client, salon_a):
    """`Booking.service` est en PROTECT : la base refuse, et c'est juste.

    Supprimer la prestation d'un rendez-vous existant effacerait le libelle
    de ce que la cliente a commande.
    """
    un_rendez_vous(salon_a, avec_recette=False)

    page = admin_client.get(
        reverse("admin:catalog_service_delete", args=[salon_a.service.pk])
    ).content.decode("utf-8")

    # Django annonce le refus au lieu de proposer le bouton.
    assert "protégé" in page.lower() or "protege" in page.lower()
