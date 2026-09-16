"""Interdiction de relier deux objets de salons differents.

L'API ne peut pas produire ce cas : les politiques RLS masquent les lignes
des autres salons. L'admin plateforme, lui, travaille avec un role BYPASSRLS
et voit tout - c'est le seul endroit d'ou une incoherence inter-tenant
pourrait entrer. Ces tests verrouillent ce chemin.
"""

from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.scheduling.models import Booking
from apps.staff.models import StaffService
from conftest import as_tenant
from tests.factories import ServiceFactory


@pytest.mark.django_db
def test_a_staff_member_cannot_be_given_another_salons_service(salon_a, salon_b):
    link = StaffService(
        tenant=salon_a.tenant,
        staff_member=salon_a.staff,
        service=salon_b.service,  # prestation du voisin
    )

    with pytest.raises(ValidationError) as caught:
        link.full_clean()

    assert "service" in caught.value.message_dict


@pytest.mark.django_db
def test_a_booking_cannot_point_at_another_salons_customer(salon_a, salon_b):
    starts_at = timezone.now() + timedelta(days=5)
    booking = Booking(
        tenant=salon_a.tenant,
        customer=salon_b.customer,  # cliente du voisin
        staff_member=salon_a.staff,
        service=salon_a.service,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=120),
        service_name=salon_a.service.name,
    )

    with pytest.raises(ValidationError) as caught:
        booking.full_clean()

    assert "customer" in caught.value.message_dict


@pytest.mark.django_db
def test_a_service_cannot_use_another_salons_category(salon_a, salon_b):
    service = ServiceFactory.build(
        tenant=salon_a.tenant,
        category=salon_b.category,
        name="Prestation douteuse",
        duration_minutes=60,
    )

    with pytest.raises(ValidationError) as caught:
        service.full_clean()

    assert "category" in caught.value.message_dict


@pytest.mark.django_db
def test_consistent_relations_pass_validation(salon_a):
    """Le garde-fou ne gene pas le cas normal."""
    with as_tenant(salon_a.tenant):
        starts_at = timezone.now() + timedelta(days=5)
        booking = Booking(
            tenant=salon_a.tenant,
            customer=salon_a.customer,
            staff_member=salon_a.staff,
            service=salon_a.service,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=120),
            service_name=salon_a.service.name,
        )
        booking.full_clean()  # ne doit rien lever


@pytest.mark.django_db
def test_a_staff_member_cannot_be_linked_to_another_salons_membership(
    salon_a, salon_b
):
    """Le lien vers Membership est un OneToOneField.

    Il se traite comme une cle etrangere, mais Django le classe a part :
    ne verifier que `many_to_one` laissait passer ce cas precis, et l'admin
    plateforme proposait bien les membres des deux salons dans le menu.
    """
    salon_a.staff.membership = salon_b.membership

    with pytest.raises(ValidationError) as caught:
        salon_a.staff.full_clean()

    assert "membership" in caught.value.message_dict
