"""Routes de l'API v1.

Deux familles bien separees, parce que la source du tenant differe :

    /api/v1/public/...   tenant deduit du hostname, aucune authentification
    /api/v1/account/...  ouvert, sans salon : inscription, mot de passe,
                         invitation
    /api/v1/...          tenant deduit des memberships de l'utilisateur

Cette separation est ce sur quoi s'appuie TenantContextMiddleware pour
decider a qui faire confiance. Ne pas melanger les deux prefixes.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.accounts.urls import account_urlpatterns
from apps.accounts.views import InvitationViewSet, MembershipViewSet
from apps.billing.views import InvoiceViewSet, SubscriptionView
from apps.catalog.views import (
    ResourceViewSet,
    ServiceCategoryViewSet,
    ServiceOptionViewSet,
    ServiceResourceViewSet,
    ServiceViewSet,
)
from apps.clients.views import (
    ClientBookingsView,
    ClientForgetBookingView,
    ClientMeView,
    ClientSessionView,
    ClientSignupView,
)
from apps.customers.views import CustomerViewSet
from apps.finance.views import TransactionViewSet
from apps.media.views import MediaAssetViewSet
from apps.payments.views import (
    PaymentChannelViewSet,
    PublicBookingStatusView,
    PublicDepositProofView,
    PublicPaymentView,
)
from apps.reviews.views import (
    PublicReviewCreateView,
    PublicReviewListView,
    ReviewInvitationView,
    ReviewViewSet,
)
from apps.salons.views import PublicSalonView
from apps.salons.views_dashboard import SalonProfileView, TravelZoneViewSet
from apps.scheduling.views import (
    AvailabilityExceptionViewSet,
    BookingViewSet,
    BusinessHoursViewSet,
    OverviewView,
    WaitlistViewSet,
)
from apps.scheduling.views_public import (
    PublicAvailabilityView,
    PublicBookingCreateView,
    PublicWaitlistView,
)
from apps.staff.views import StaffMemberViewSet
from apps.store.views import (
    ProductViewSet,
    RequirementProductViewSet,
    RequirementViewSet,
)
from apps.tenants.views_identity import SalonIdentityView

router = DefaultRouter()
router.register("service-categories", ServiceCategoryViewSet, basename="service-category")
router.register("services", ServiceViewSet, basename="service")
router.register("service-options", ServiceOptionViewSet, basename="service-option")
router.register("resources", ResourceViewSet, basename="resource")
router.register(
    "service-resources", ServiceResourceViewSet, basename="service-resource"
)
router.register("staff-members", StaffMemberViewSet, basename="staff-member")
router.register("business-hours", BusinessHoursViewSet, basename="business-hours")
router.register(
    "availability-exceptions", AvailabilityExceptionViewSet, basename="availability-exception"
)
router.register("bookings", BookingViewSet, basename="booking")
router.register("waitlist", WaitlistViewSet, basename="waitlist")
router.register("transactions", TransactionViewSet, basename="transaction")
router.register("products", ProductViewSet, basename="product")
router.register(
    "payment-channels", PaymentChannelViewSet, basename="payment-channel"
)
router.register("requirements", RequirementViewSet, basename="requirement")
router.register(
    "requirement-products", RequirementProductViewSet, basename="requirement-product"
)
router.register("customers", CustomerViewSet, basename="customer")
router.register("media", MediaAssetViewSet, basename="media")
router.register("team", MembershipViewSet, basename="team")
router.register("invitations", InvitationViewSet, basename="invitation")
router.register("invoices", InvoiceViewSet, basename="invoice")
router.register("reviews", ReviewViewSet, basename="review")
router.register("travel-zones", TravelZoneViewSet, basename="travel-zone")

public_urlpatterns = [
    path("salon", PublicSalonView.as_view(), name="public-salon"),
    path("availability", PublicAvailabilityView.as_view(), name="public-availability"),
    path("bookings", PublicBookingCreateView.as_view(), name="public-booking-create"),
    path("waitlist", PublicWaitlistView.as_view(), name="public-waitlist"),
    # Reglement de l'acompte. Le jeton signe remplace l'authentification :
    # la cliente n'a pas de compte, et un identifiant devine n'ouvre rien.
    path("payment", PublicPaymentView.as_view(), name="public-payment"),
    path(
        "payment/proof",
        PublicDepositProofView.as_view(),
        name="public-payment-proof",
    ),
    # Suivi d'un rendez-vous, en lecture seule. C'est la ou renvoie la page
    # de reglement une fois l'acompte accepte.
    path(
        "booking-status",
        PublicBookingStatusView.as_view(),
        name="public-booking-status",
    ),
    # L'espace cliente vit sous `public/` parce qu'il s'ouvre depuis un
    # mini-site, sans compte d'equipe. Les routes restent authentifiees,
    # sauf l'inscription.
    path("client/signup", ClientSignupView.as_view(), name="client-signup"),
    path("client/session", ClientSessionView.as_view(), name="client-session"),
    path("client/me", ClientMeView.as_view(), name="client-me"),
    path("client/bookings", ClientBookingsView.as_view(), name="client-bookings"),
    path(
        "client/bookings/forget",
        ClientForgetBookingView.as_view(),
        name="client-forget-booking",
    ),
    path("reviews", PublicReviewListView.as_view(), name="public-reviews"),
    path(
        "reviews/invitation",
        ReviewInvitationView.as_view(),
        name="public-review-invitation",
    ),
    path(
        "reviews/create",
        PublicReviewCreateView.as_view(),
        name="public-review-create",
    ),
]

urlpatterns = [
    path("public/", include((public_urlpatterns, "public"))),
    # Comptes : ouvert, sans salon resolu (inscription, mot de passe,
    # invitation). Distinct de `public/`, qui est l'API d'un salon.
    path("account/", include((account_urlpatterns, "account"))),
    path("auth/", include("apps.accounts.urls")),
    path("salon-profile", SalonProfileView.as_view(), name="salon-profile"),
    # Identite : le nom du salon et les coordonnees de qui le tient.
    # Trois tables, un seul ecran - on vient les changer au meme moment.
    path("salon-identity", SalonIdentityView.as_view(), name="salon-identity"),
    # Accueil du tableau de bord. Une seule lecture pour douze chiffres :
    # en six appels, l'ecran s'assemble par morceaux sur un reseau mobile.
    path("overview", OverviewView.as_view(), name="overview"),
    path("subscription", SubscriptionView.as_view(), name="subscription"),
    path("", include(router.urls)),
]
