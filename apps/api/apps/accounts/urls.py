"""Routes d'authentification.

Deux familles, montees sous deux prefixes differents :

    /api/v1/auth/     session existante requise
    /api/v1/account/  ouvert : inscription, mot de passe oublie, invitation

Ces dernieres ne vivent surtout pas sous `/api/v1/public/`, qui designe
l'API publique *d'un salon* : le middleware y exige un salon resolu depuis
le hostname, alors qu'une inscription ou un lien de reinitialisation
n'appartiennent a aucun salon.
"""

from django.urls import path

from .views import (
    AcceptInvitationView,
    LoginView,
    LogoutView,
    PasswordChangeView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    PublicInvitationView,
    SessionView,
    SignupView,
    SlugAvailabilityView,
)

app_name = "accounts"

# Routes authentifiees ou semi-publiques, sous /api/v1/auth/
urlpatterns = [
    path("login", LoginView.as_view(), name="login"),
    path("logout", LogoutView.as_view(), name="logout"),
    path("session", SessionView.as_view(), name="session"),
    path("password/change", PasswordChangeView.as_view(), name="password-change"),
]

# Routes ouvertes, sous /api/v1/account/
account_urlpatterns = [
    path("signup", SignupView.as_view(), name="signup"),
    path("slug-availability", SlugAvailabilityView.as_view(), name="slug-availability"),
    path(
        "password/reset",
        PasswordResetRequestView.as_view(),
        name="password-reset",
    ),
    path(
        "password/reset/confirm",
        PasswordResetConfirmView.as_view(),
        name="password-reset-confirm",
    ),
    path("invitation", PublicInvitationView.as_view(), name="invitation"),
    path("invitation/accept", AcceptInvitationView.as_view(), name="invitation-accept"),
]
