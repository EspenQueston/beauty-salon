"""Double authentification de l'espace professionnel (et des comptes d'equipe).

---------------------------------------------------------------------------
Le parcours
---------------------------------------------------------------------------

  1. **Activation** (ecran Securite) : un QR code a scanner dans une
     application d'authentification (Google Authenticator, Microsoft
     Authenticator, 1Password...), puis un premier code a six chiffres et le
     mot de passe actuel pour confirmer. Huit codes de secours sont affiches
     une seule fois.
  2. **Connexion** : apres le bon mot de passe, la session n'est pas ouverte.
     Elle attend (cinq minutes au plus) le code de l'application ou un code
     de secours, envoye a `/api/v1/auth/mfa/verify`.
  3. **Desactivation** : mot de passe et code exiges — une session volee ne
     suffit ni a l'activer (pour verrouiller la proprietaire dehors) ni a la
     retirer.

Memes appareils que l'administration plateforme (`django_otp`) : un compte
d'equipe qui a deja son application pour l'admin s'en sert ici aussi.

Les codes sont freines comme les mots de passe (voir `securite.py`) et
journalises (voir `journal.py`) ; ils ne sont jamais ecrits nulle part.
"""

from __future__ import annotations

import time

from django.contrib.auth import login
from django.db import transaction
from django_otp import devices_for_user
from django_otp import login as otp_login
from django_otp.plugins.otp_static.models import StaticDevice
from rest_framework import status
from rest_framework.permissions import AllowAny, BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import BaseThrottle
from rest_framework.views import APIView

from . import journal, securite, tasks
from .mfa import _issue_recovery_codes, _qr_svg, confirmed_device, pending_device
from .models import Membership, User

CLE_ATTENTE = "mfa_attente"
DELAI_ATTENTE = 5 * 60
BACKEND = "django.contrib.auth.backends.ModelBackend"


def active(user) -> bool:
    return confirmed_device(user) is not None


def mettre_en_attente(request, user) -> Response:
    """Mot de passe juste, code attendu : rien n'est ouvert encore."""
    # Nouvelle cle : une session fixee avant la connexion ne sert a rien.
    request.session.cycle_key()
    request.session[CLE_ATTENTE] = {"u": str(user.pk), "t": int(time.time())}
    return Response(
        {
            "mfa_required": True,
            "detail": "Saisissez le code de votre application d'authentification.",
        }
    )


def _codes_restants(user) -> int:
    appareil = StaticDevice.objects.filter(user=user, name="Codes de secours").first()
    return appareil.token_set.count() if appareil else 0


def _verifier_code(user, code: str):
    """L'appareil qui accepte ce code (application ou code de secours), sinon None."""
    code = (code or "").strip().replace(" ", "")
    if not code:
        return None
    for appareil in devices_for_user(user, confirmed=True):
        if appareil.verify_token(code):
            return appareil
    return None


def _ip(request) -> str:
    return BaseThrottle().get_ident(request) or ""


class EstMembreDEquipe(BasePermission):
    """La double authentification se regle depuis l'espace pro, par l'equipe."""

    message = "La double authentification se règle depuis l'espace professionnel."

    def has_permission(self, request, view):
        return bool(
            request.user.is_authenticated
            and (
                request.user.is_staff
                or Membership.objects.filter(
                    user=request.user, status=Membership.Status.ACTIVE
                ).exists()
            )
        )


# ---------------------------------------------------------------------------
# Connexion : le code
# ---------------------------------------------------------------------------


class MfaVerifyView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "mfa"

    def post(self, request):
        from .serializers import UserSerializer

        attente = request.session.get(CLE_ATTENTE) or {}
        if not attente or int(time.time()) - int(attente.get("t", 0)) > DELAI_ATTENTE:
            request.session.pop(CLE_ATTENTE, None)
            return Response(
                {
                    "detail": "Le délai est dépassé. Saisissez de nouveau votre mot de passe.",
                    "code": "mfa_expired",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        user = User.objects.filter(pk=attente.get("u"), is_active=True).first()
        if user is None:
            request.session.pop(CLE_ATTENTE, None)
            return Response({"detail": "Session expirée.", "code": "mfa_expired"}, status=400)

        ip = _ip(request)
        if securite.connexion_bloquee(user.email, ip):
            return Response(
                {
                    "detail": "Trop de tentatives. Patientez quelques minutes avant de réessayer.",
                    "code": "too_many_attempts",
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        appareil = _verifier_code(user, request.data.get("code", ""))
        if appareil is None:
            bloque = securite.noter_echec(user.email, ip)
            journal.consigner("AUTH_MFA_FAILED", request=request, user=user)
            if bloque:
                journal.consigner("AUTH_ACCOUNT_LOCKED", request=request, user=user, etape="mfa")
                journal.alerter_plateforme(
                    "Codes de double authentification refusés en série",
                    f"{user.email} : un mot de passe juste, puis des codes faux.",
                )
            return Response(
                {"detail": "Code incorrect ou expiré.", "code": "invalid_code"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        request.session.pop(CLE_ATTENTE, None)
        securite.noter_succes(user.email)
        login(request, user, backend=BACKEND)
        otp_login(request, appareil)
        secours = isinstance(appareil, StaticDevice)
        journal.consigner(
            "AUTH_LOGIN_SUCCEEDED", request=request, user=user, mfa=True, code_de_secours=secours
        )
        donnees = dict(UserSerializer(user).data)
        if secours:
            donnees["codes_de_secours_restants"] = _codes_restants(user)
        return Response(donnees)


# ---------------------------------------------------------------------------
# Reglages : activer, desactiver, codes de secours
# ---------------------------------------------------------------------------


def _mot_de_passe_requis(request) -> Response | None:
    if not request.user.check_password(str(request.data.get("password", ""))):
        return Response(
            {"detail": "Mot de passe incorrect.", "code": "invalid_password"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return None


class MfaStatusView(APIView):
    permission_classes = [IsAuthenticated, EstMembreDEquipe]
    throttle_scope = "mfa"

    def get(self, request):
        return Response(
            {"enabled": active(request.user), "codes_restants": _codes_restants(request.user)}
        )


class MfaSetupView(APIView):
    """Prepare l'appareil et rend le QR code. Rien n'est active avant `confirm`."""

    permission_classes = [IsAuthenticated, EstMembreDEquipe]
    throttle_scope = "mfa"

    def post(self, request):
        if active(request.user):
            return Response(
                {"detail": "La double authentification est déjà active.", "code": "already"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        appareil = pending_device(request.user)
        return Response(
            {
                "qr_svg": _qr_svg(appareil.config_url),
                # Pour la saisie a la main, quand l'appareil photo ne coopere pas.
                "secret": _base32(appareil.bin_key),
            }
        )


def _base32(cle: bytes) -> str:
    import base64

    brut = base64.b32encode(cle).decode().rstrip("=")
    return " ".join(brut[i : i + 4] for i in range(0, len(brut), 4))


class MfaConfirmView(APIView):
    permission_classes = [IsAuthenticated, EstMembreDEquipe]
    throttle_scope = "mfa"

    def post(self, request):
        refus = _mot_de_passe_requis(request)
        if refus:
            return refus
        appareil = pending_device(request.user)
        if not appareil.verify_token(str(request.data.get("code", "")).strip().replace(" ", "")):
            return Response(
                {
                    "detail": "Code incorrect. Vérifiez que l'heure de votre téléphone est juste.",
                    "code": "invalid_code",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        with transaction.atomic():
            appareil.confirmed = True
            appareil.save(update_fields=["confirmed"])
            codes = _issue_recovery_codes(request.user)
        otp_login(request, appareil)
        user = request.user
        journal.consigner("AUTH_MFA_ENABLED", request=request, user=user)
        transaction.on_commit(
            lambda: tasks.alerte_securite.delay(user.email, "mfa_active", nom=user.display_name)
        )
        return Response({"enabled": True, "codes": codes})


class MfaDisableView(APIView):
    permission_classes = [IsAuthenticated, EstMembreDEquipe]
    throttle_scope = "mfa"

    def post(self, request):
        refus = _mot_de_passe_requis(request)
        if refus:
            return refus
        if _verifier_code(request.user, str(request.data.get("code", ""))) is None:
            journal.consigner("AUTH_MFA_FAILED", request=request, user=request.user)
            return Response(
                {"detail": "Code incorrect ou expiré.", "code": "invalid_code"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        for appareil in devices_for_user(request.user, confirmed=None):
            appareil.delete()
        user = request.user
        journal.consigner("AUTH_MFA_DISABLED", request=request, user=user)
        transaction.on_commit(
            lambda: tasks.alerte_securite.delay(user.email, "mfa_desactive", nom=user.display_name)
        )
        return Response({"enabled": False})


class MfaRecoveryCodesView(APIView):
    """Nouveaux codes de secours : les anciens cessent de fonctionner."""

    permission_classes = [IsAuthenticated, EstMembreDEquipe]
    throttle_scope = "mfa"

    def post(self, request):
        refus = _mot_de_passe_requis(request)
        if refus:
            return refus
        if not active(request.user):
            return Response(
                {"detail": "La double authentification n'est pas active.", "code": "inactive"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        codes = _issue_recovery_codes(request.user)
        journal.consigner("AUTH_RECOVERY_CODES_REGENERATED", request=request, user=request.user)
        return Response({"codes": codes})
