"""Administration plateforme : supervision et publication des salons.

Deux comportements comptent ici, et pour la meme raison. Un salon inscrit
depuis le formulaire public naît « en preparation » : sa page repond 404
tant qu'une personne de l'equipe n'a pas decide de la publier. L'action de
l'admin est donc l'unique interrupteur de cette mise en ligne, et le
panneau d'accueil est ce qui rend cette file d'attente visible.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.common.admin import ADMIN_DB
from apps.domains.models import Domain
from apps.tenants.models import Tenant
from conftest import as_tenant
from tests.factories import UserFactory

PASSWORD = "motdepasse-solide"

# L'admin ecrit par l'alias privilegie, qui est une seconde connexion vers la
# meme base. Sans commit reel, elle ne verrait pas les lignes creees par la
# connexion applicative : d'ou `transaction=True`.
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


@pytest.fixture
def pending_tenant():
    return Tenant.objects.create(
        name="Chez Fatou",
        slug="chez-fatou",
        status=Tenant.Status.PENDING,
    )


def publish(client, tenant):
    return client.post(
        reverse("admin:tenants_tenant_changelist"),
        {
            "action": "action_publish",
            "_selected_action": [str(tenant.pk)],
            "index": "0",
        },
        follow=True,
    )


def test_the_home_page_counts_what_is_waiting(admin_client, pending_tenant):
    response = admin_client.get(reverse("admin:index"))

    assert response.status_code == 200
    body = response.content.decode()
    assert "Ce qui attend une décision" in body
    # Le salon en attente est nomme, pas seulement compte : c'est ce qui
    # permet d'agir sans ouvrir une seconde page.
    assert "Chez Fatou" in body


def test_publishing_puts_the_mini_site_online(admin_client, pending_tenant):
    response = publish(admin_client, pending_tenant)

    assert response.status_code == 200
    pending_tenant.refresh_from_db()
    assert pending_tenant.status == Tenant.Status.ACTIVE

    # Sans sous-domaine, « actif » ne veut rien dire : personne ne peut
    # atteindre la page.
    assert Domain.objects.filter(
        tenant=pending_tenant, is_primary=True, active=True
    ).exists()


def test_publishing_is_written_to_the_audit_log(admin_client, pending_tenant):
    publish(admin_client, pending_tenant)

    entry = (
        AuditLog.objects.using(ADMIN_DB)
        .filter(resource_id=str(pending_tenant.id))
        .first()
    )
    assert entry is not None
    assert entry.action == AuditLog.Action.TENANT_STATUS_CHANGED
    assert entry.metadata["status"] == Tenant.Status.ACTIVE
    assert entry.actor_user.email == "supervision@example.com"


def test_publishing_twice_says_so_instead_of_acting(admin_client):
    tenant = Tenant.objects.create(
        name="Deja En Ligne", slug="deja-en-ligne", status=Tenant.Status.ACTIVE
    )

    response = publish(admin_client, tenant)

    assert "Déjà actifs" in response.content.decode()
    assert AuditLog.objects.using(ADMIN_DB).filter(
        resource_id=str(tenant.id)
    ).count() == 0


def test_suspending_takes_the_mini_site_offline(admin_client):
    tenant = Tenant.objects.create(
        name="A Suspendre", slug="a-suspendre", status=Tenant.Status.ACTIVE
    )

    admin_client.post(
        reverse("admin:tenants_tenant_changelist"),
        {
            "action": "action_suspend",
            "_selected_action": [str(tenant.pk)],
            "index": "0",
        },
        follow=True,
    )

    tenant.refresh_from_db()
    assert tenant.status == Tenant.Status.SUSPENDED


def test_a_salon_team_member_cannot_reach_the_admin(client):
    UserFactory(email="gerante@example.com", password=PASSWORD)
    client.login(username="gerante@example.com", password=PASSWORD)

    response = client.get(reverse("admin:index"), follow=True)

    # Redirection vers la page de connexion de l'admin : le compte existe,
    # mais il n'appartient pas a l'equipe plateforme.
    assert "Ce qui attend une décision" not in response.content.decode()


@pytest.mark.django_db
def test_the_orders_view_is_read_only_for_the_platform(salon_a):
    """La plateforme regarde les commandes des salons, elle n'y touche pas.

    Un rendez-vous porte le chiffre d'affaires du salon, ses acomptes et ses
    engagements envers une cliente. Une correction faite depuis
    l'administration passerait sous ses yeux sans trace dans son agenda, et
    ses comptes ne tomberaient plus juste.
    """
    from django.contrib.admin.sites import site

    from apps.scheduling.models import Booking

    admin_class = site._registry[Booking]

    assert admin_class.has_add_permission(None) is False
    assert admin_class.has_change_permission(None) is False
    assert admin_class.has_delete_permission(None) is False

    # Tout champ affiche est en lecture seule - y compris ceux qu'on
    # ajoutera au modele plus tard, puisque la liste est derivee des
    # fieldsets et non ecrite a la main.
    shown = {
        field
        for _, options in admin_class.fieldsets
        for field in options["fields"]
    }
    assert shown <= set(admin_class.get_readonly_fields(None))


# ---------------------------------------------------------------------------
# Les commandes des salons : la plateforme regarde, elle ne touche pas
# ---------------------------------------------------------------------------


def test_the_platform_can_read_every_salons_bookings(admin_client, salon_a):
    """Le support en a besoin : « ma cliente dit avoir reserve, je ne vois
    rien », « d'ou sort ce montant ». Repondre demande de voir."""
    from apps.scheduling.models import Booking

    starts_at = timezone.now() + timedelta(days=2)
    with as_tenant(salon_a.tenant):
        Booking.objects.create(
            tenant=salon_a.tenant,
            customer=salon_a.customer,
            staff_member=salon_a.staff,
            service=salon_a.service,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(hours=1),
            status=Booking.Status.CONFIRMED,
            service_name="Box braids",
            total_amount=Decimal("450"),
        )

    response = admin_client.get("/admin/scheduling/booking/")

    assert response.status_code == 200
    assert b"Box braids" in response.content


def test_the_platform_cannot_create_change_or_delete_a_booking(admin_client, salon_a):
    """Un rendez-vous appartient au salon.

    Une correction faite ici passerait sous ses yeux sans trace dans son
    agenda, et ses comptes ne tomberaient plus juste. La suppression est
    fermee plus fort encore : les lignes de recette pointent vers ces
    rendez-vous.

    Le controle porte sur les reponses HTTP, pas sur les methodes : quelqu'un
    qui redefinirait `has_change_permission` ferait tomber ce test, ce qui est
    exactement le but.
    """
    from apps.scheduling.models import Booking

    starts_at = timezone.now() + timedelta(days=2)
    with as_tenant(salon_a.tenant):
        booking = Booking.objects.create(
            tenant=salon_a.tenant,
            customer=salon_a.customer,
            staff_member=salon_a.staff,
            service=salon_a.service,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(hours=1),
            status=Booking.Status.CONFIRMED,
            service_name="Box braids",
            total_amount=Decimal("450"),
        )

    # Creation : la page d'ajout n'existe pas.
    assert admin_client.get("/admin/scheduling/booking/add/").status_code == 403

    # Suppression : refusee.
    assert (
        admin_client.get(f"/admin/scheduling/booking/{booking.id}/delete/").status_code
        == 403
    )

    # Consultation : ouverte, mais sans formulaire modifiable.
    detail = admin_client.get(f"/admin/scheduling/booking/{booking.id}/change/")
    assert detail.status_code == 200
    assert b'name="status"' not in detail.content

    # Et un POST direct ne change rien, meme en contournant l'interface.
    admin_client.post(
        f"/admin/scheduling/booking/{booking.id}/change/",
        {"status": Booking.Status.CANCELLED},
    )
    with as_tenant(salon_a.tenant):
        booking.refresh_from_db()
    assert booking.status == Booking.Status.CONFIRMED
