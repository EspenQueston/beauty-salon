"""Fixtures partagees par toute la suite de tests."""

from contextlib import contextmanager
from datetime import time

import pytest
from django.conf import settings
from rest_framework.test import APIClient

from apps.common.db import tenant_context
from tests.factories import (
    BusinessHoursFactory,
    CustomerFactory,
    DomainFactory,
    MembershipFactory,
    SalonProfileFactory,
    ServiceCategoryFactory,
    ServiceFactory,
    StaffMemberFactory,
    StaffServiceFactory,
    TenantFactory,
    UserFactory,
)


def salon_host(slug: str) -> str:
    """Hostname du mini-site d'un salon, selon le domaine configure."""
    return f"{slug}.{settings.PLATFORM_DOMAIN}"


@contextmanager
def as_tenant(tenant):
    """Reproduit en test le contexte pose par TenantContextMiddleware."""
    with tenant_context(tenant.id):
        yield


@pytest.fixture(autouse=True)
def clear_caches():
    """Vide le cache entre deux tests.

    La resolution hostname -> tenant est mise en cache. Comme chaque test est
    annule en fin d'execution mais que le cache, lui, survit dans le process,
    un test heriterait sinon de l'identifiant d'un salon qui n'existe plus.
    """
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def tenant_a(db):
    tenant = TenantFactory(name="Blond Rose", slug="blondrose")
    DomainFactory(tenant=tenant, hostname=salon_host("blondrose"))
    return tenant


@pytest.fixture
def tenant_b(db):
    tenant = TenantFactory(name="Beauty by Anna", slug="beautybyanna")
    DomainFactory(tenant=tenant, hostname=salon_host("beautybyanna"))
    return tenant


class SalonFixture:
    """Un salon complet et reservable, pour eviter dix lignes de montage
    repetees dans chaque test."""

    def __init__(self, tenant):
        self.tenant = tenant
        with as_tenant(tenant):
            self.profile = SalonProfileFactory(tenant=tenant)
            self.category = ServiceCategoryFactory(tenant=tenant, name="Coiffure")
            self.service = ServiceFactory(
                tenant=tenant, category=self.category, name="Tresses", duration_minutes=120
            )
            self.staff = StaffMemberFactory(tenant=tenant, name="Fatou")
            StaffServiceFactory(
                tenant=tenant, staff_member=self.staff, service=self.service
            )
            # Ouvert du lundi au samedi, 9h-18h (heure locale du salon).
            for weekday in range(0, 6):
                BusinessHoursFactory(
                    tenant=tenant,
                    staff_member=None,
                    weekday=weekday,
                    starts_at=time(9, 0),
                    ends_at=time(18, 0),
                )
            self.customer = CustomerFactory(tenant=tenant)

        self.owner = UserFactory()
        self.membership = MembershipFactory(tenant=tenant, user=self.owner)


@pytest.fixture
def salon_a(tenant_a):
    return SalonFixture(tenant_a)


@pytest.fixture
def salon_b(tenant_b):
    return SalonFixture(tenant_b)
