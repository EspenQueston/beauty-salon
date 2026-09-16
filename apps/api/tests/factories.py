"""Fabriques de donnees de test.

Les modeles tenant refusent d'etre ecrits hors contexte : la politique RLS
possede une clause WITH CHECK, donc un INSERT sans `app.tenant_id` est
rejete par PostgreSQL. Les fabriques doivent donc etre appelees dans un
bloc `as_tenant(...)`, exactement comme le code de production tourne dans le
contexte pose par le middleware.
"""

from datetime import time
from decimal import Decimal

import factory
from django.conf import settings

from apps.accounts.models import Membership, User
from apps.catalog.models import Service, ServiceCategory
from apps.customers.models import Customer
from apps.domains.models import Domain
from apps.salons.models import SalonProfile
from apps.scheduling.models import Booking, BusinessHours
from apps.staff.models import StaffMember, StaffService
from apps.tenants.models import Tenant


class TenantFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Tenant

    name = factory.Sequence(lambda n: f"Salon {n}")
    slug = factory.Sequence(lambda n: f"salon-{n}")
    status = Tenant.Status.ACTIVE
    country = Tenant.Country.CONGO
    timezone = "Africa/Brazzaville"
    currency = Tenant.Currency.XAF


class DomainFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Domain

    tenant = factory.SubFactory(TenantFactory)
    hostname = factory.LazyAttribute(
        lambda o: f"{o.tenant.slug}.{settings.PLATFORM_DOMAIN}"
    )
    kind = Domain.Kind.PLATFORM_SUBDOMAIN
    is_primary = True
    active = True


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        skip_postgeneration_save = True

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    display_name = factory.Sequence(lambda n: f"Utilisateur {n}")

    @factory.post_generation
    def password(obj, create, extracted, **kwargs):
        obj.set_password(extracted or "motdepasse-solide")
        if create:
            obj.save()


class MembershipFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Membership

    tenant = factory.SubFactory(TenantFactory)
    user = factory.SubFactory(UserFactory)
    role = Membership.Role.OWNER
    status = Membership.Status.ACTIVE


class SalonProfileFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SalonProfile

    description = "Specialiste tresses et perruques."
    city = "Brazzaville"
    slot_granularity_minutes = 15
    buffer_minutes = 0
    min_lead_time_minutes = 0
    max_advance_days = 90


class ServiceCategoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ServiceCategory

    name = factory.Sequence(lambda n: f"Categorie {n}")


class ServiceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Service

    name = factory.Sequence(lambda n: f"Prestation {n}")
    duration_minutes = 60
    price_amount = Decimal("15000")
    requires_deposit = False


class StaffMemberFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = StaffMember

    name = factory.Sequence(lambda n: f"Prestataire {n}")
    active = True


class StaffServiceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = StaffService


class BusinessHoursFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = BusinessHours

    weekday = 0
    starts_at = time(9, 0)
    ends_at = time(18, 0)


class CustomerFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Customer

    full_name = factory.Sequence(lambda n: f"Cliente {n}")
    phone = factory.Sequence(lambda n: f"+2420000{n:04d}")


class BookingFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Booking

    status = Booking.Status.CONFIRMED
    source = Booking.Source.WEB
    service_name = factory.LazyAttribute(lambda o: o.service.name)
