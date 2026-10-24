"""La page commerciale expose des tarifs publics, jamais des données de paiement privées."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.test import override_settings
from django.utils import timezone

from apps.billing.models import Plan, PlanPrice, PlatformPaymentMethod
from apps.common.models import HomeMetric, HomeReference
from conftest import as_tenant
from tests.factories import (
    BookingFactory,
    MembershipFactory,
    SalonProfileFactory,
    TenantFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db
HOME = "/api/v1/account/home"


def configure_price():
    plan, _ = Plan.objects.update_or_create(
        code="monthly",
        defaults={"name": "Mensuel", "group": "standard", "active": True, "billing_months": 1},
    )
    PlanPrice.objects.update_or_create(
        plan=plan, currency="XAF", defaults={"amount": Decimal("15000"), "active": True}
    )
    PlatformPaymentMethod.objects.create(
        kind="mobile_money",
        country="CG",
        currency="XAF",
        provider_name="MoMo",
        account_number="PRIVATE-ACCOUNT",
        account_holder="PRIVATE-HOLDER",
    )
    return plan


def test_catalogue_anonymous_whitelists_fields(api_client):
    configure_price()
    response = api_client.get(HOME, HTTP_X_TENANT_ID="forged", HTTP_X_TENANT_HOST="private.example")
    assert response.status_code == 200
    country = next(item for item in response.data["countries"] if item["code"] == "CG")
    assert country["currencies"][0]["plans"][0]["amount"] == "15000.00"
    assert "PRIVATE-ACCOUNT" not in response.content.decode()
    assert "PRIVATE-HOLDER" not in response.content.decode()
    assert {"BJ", "BF", "CI", "TG", "SN", "NE"} <= {
        item["code"] for item in response.data["supported_countries"]
    }
    assert "public" in response["Cache-Control"]


def test_inactive_price_and_unpayable_country_are_not_promised(api_client):
    plan = configure_price()
    PlanPrice.objects.filter(plan=plan, currency="XAF").update(active=False)
    assert "CG" not in {item["code"] for item in api_client.get(HOME).data["countries"]}


def test_reference_requires_consent_verification_and_public_salon(api_client):
    salon = TenantFactory(status="active")
    with as_tenant(salon):
        SalonProfileFactory(tenant=salon)
    reference = HomeReference.objects.create(
        tenant=salon,
        author="Author",
        quote_fr="Retour autorisé",
        quote_en="Approved feedback",
        active=True,
        consent=False,
        verified=True,
    )
    assert api_client.get(HOME).data["references"] == []
    reference.consent = True
    reference.save()
    result = api_client.get(HOME + "?lang=en").data["references"]
    assert result[0]["quote"] == "Approved feedback"
    salon.status = "suspended"
    salon.save()
    assert api_client.get(HOME).data["references"] == []


def test_reference_form_rejects_unapproved_or_unsafe_portrait():
    reference = HomeReference(tenant=TenantFactory(), author="A", active=True)
    with pytest.raises(ValidationError):
        reference.full_clean()
    reference.active = False
    reference.portrait = "http://example.com/portrait.jpg"
    with pytest.raises(ValidationError):
        reference.full_clean()


def test_session_supports_multiple_salons_and_never_caches(api_client):
    owner = UserFactory()
    MembershipFactory(user=owner)
    MembershipFactory(user=owner)
    another = MembershipFactory()
    api_client.force_login(owner)
    response = api_client.get(HOME + "/session")
    assert response.status_code == 200
    assert len(response.data["memberships"]) == 2
    assert str(another.tenant_id) not in response.content.decode()
    assert response["Cache-Control"] == "private, no-store"


def test_guest_session_is_null(api_client):
    response = api_client.get(HOME + "/session")
    assert response.status_code == 200
    assert response.data is None


def test_first_booking_remains_unique_after_cancellation(django_capture_on_commit_callbacks):
    from apps.common.models import HomeBookingMilestone
    from tests.factories import (
        CustomerFactory,
        ServiceCategoryFactory,
        ServiceFactory,
        StaffMemberFactory,
    )

    salon = TenantFactory()
    with as_tenant(salon):
        category = ServiceCategoryFactory(tenant=salon)
        service = ServiceFactory(tenant=salon, category=category)
        staff = StaffMemberFactory(tenant=salon)
        customer = CustomerFactory(tenant=salon)
        with django_capture_on_commit_callbacks(execute=True):
            booking = BookingFactory(
                tenant=salon,
                service=service,
                staff_member=staff,
                customer=customer,
                starts_at=timezone.now(),
                ends_at=timezone.now() + timedelta(hours=1),
            )
        booking.status = "cancelled"
        booking.save()
        with django_capture_on_commit_callbacks(execute=True):
            BookingFactory(
                tenant=salon,
                service=service,
                staff_member=staff,
                customer=customer,
                starts_at=timezone.now() + timedelta(days=1),
                ends_at=timezone.now() + timedelta(days=1, hours=1),
            )
    assert HomeMetric.objects.get(event="first_booking").count == 1
    assert HomeBookingMilestone.objects.filter(tenant=salon).count() == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"event": "signup_completed"},
        {"event": ["home_view"]},
        ["home_view"],
        {"event": "home_view", "language": "xx"},
    ],
)
def test_public_cannot_forge_completed_conversion(api_client, payload):
    assert api_client.post(HOME + "/metrics", payload, format="json").status_code == 400
    assert not HomeMetric.objects.exists()


def test_metrics_aggregate_without_personal_fields(api_client):
    for _ in range(2):
        assert (
            api_client.post(
                HOME + "/metrics",
                {"event": "preview_used", "language": "en", "email": "not-stored@example.com"},
                format="json",
            ).status_code
            == 204
        )
    metric = HomeMetric.objects.get()
    assert metric.count == 2
    assert metric.language == "en"
    assert {field.name for field in HomeMetric._meta.fields} == {
        "id",
        "day",
        "event",
        "language",
        "count",
    }


def test_real_stages_are_counted_after_commit(django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        salon = TenantFactory(status="pending")
    assert HomeMetric.objects.get(event="signup_completed").count == 1
    with django_capture_on_commit_callbacks(execute=True):
        salon.status = "active"
        salon.save()
    assert HomeMetric.objects.get(event="salon_published").count == 1
    with django_capture_on_commit_callbacks(execute=True):
        salon.name = "Updated name"
        salon.save()
    assert HomeMetric.objects.get(event="salon_published").count == 1
    owner = UserFactory(email_verified_at=None)
    MembershipFactory(user=owner, tenant=salon)
    with django_capture_on_commit_callbacks(execute=True):
        owner.email_verified_at = timezone.now()
        owner.save()
    assert HomeMetric.objects.get(event="email_verified").count == 1


def test_kkiapay_visibility_follows_real_configuration(api_client):
    plan = configure_price()
    PlanPrice.objects.create(plan=plan, currency="XOF", amount=Decimal("15000"))
    PlatformPaymentMethod.objects.create(kind="kkiapay", country="BF", currency="XOF")
    with override_settings(KKIAPAY_ENABLED=False):
        assert "BF" not in {item["code"] for item in api_client.get(HOME).data["countries"]}
    with override_settings(
        DEBUG=True,
        KKIAPAY_ENABLED=True,
        KKIAPAY_SANDBOX=True,
        KKIAPAY_TEST_PUBLIC_KEY="TEST_PUBLIC",
        KKIAPAY_TEST_PRIVATE_KEY="TEST_PRIVATE",
        KKIAPAY_TEST_SECRET_KEY="TEST_SECRET",
        KKIAPAY_TEST_WEBHOOK_SECRET="TEST_HASH",
    ):
        response = api_client.get(HOME)
        country = next(item for item in response.data["countries"] if item["code"] == "BF")
        assert country["currencies"][0]["kkiapay"] is True
        assert "TEST_SECRET" not in response.content.decode()
    with override_settings(DEBUG=False, KKIAPAY_ENABLED=True, KKIAPAY_SANDBOX=True):
        assert "BF" not in {item["code"] for item in api_client.get(HOME).data["countries"]}
