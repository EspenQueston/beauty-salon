"""Double authentification des administrateurs plateforme.

Le document de cadrage la classe parmi les points non negociables, et pour
une raison precise : un compte d'administration ouvre l'alias `admin` de la
base, celui qui contourne les politiques RLS. Un mot de passe volé y donne
donc acces aux donnees de *tous* les salons, pas d'un seul.

Le choix d'implementation est volontairement explicite plutot que de
remplacer le site d'administration par celui de django-otp : un middleware
maison redirige vers cet ecran tant que la session n'est pas verifiee, ce
qui rend le parcours lisible et testable branche par branche.
"""

import io

import qrcode
import qrcode.image.svg
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django_otp import login as otp_login
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp.plugins.otp_totp.models import TOTPDevice

DEVICE_NAME = "Application d'authentification"
RECOVERY_NAME = "Codes de secours"
RECOVERY_COUNT = 8


def confirmed_device(user) -> TOTPDevice | None:
    return TOTPDevice.objects.filter(user=user, confirmed=True).first()


def pending_device(user) -> TOTPDevice:
    """Appareil en cours d'enrolement, cree au besoin.

    On garde le meme secret tant que l'enrolement n'est pas termine : sinon
    recharger la page changerait le QR code sous les yeux de la personne en
    train de le scanner.
    """
    device = TOTPDevice.objects.filter(user=user, confirmed=False).first()
    if device is None:
        device = TOTPDevice.objects.create(
            user=user, name=DEVICE_NAME, confirmed=False
        )
    return device


def _qr_svg(uri: str) -> str:
    image = qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage, box_size=10)
    buffer = io.BytesIO()
    image.save(buffer)
    return buffer.getvalue().decode()


def _issue_recovery_codes(user) -> list[str]:
    """Remplace les codes de secours et renvoie les nouveaux, en clair.

    Ils ne sont affiches qu'une fois : perdre a la fois son telephone et ces
    codes impose de passer par un autre administrateur.
    """
    device, _ = StaticDevice.objects.get_or_create(user=user, name=RECOVERY_NAME)
    device.token_set.all().delete()

    codes = []
    for _ in range(RECOVERY_COUNT):
        token = StaticToken.random_token()
        device.token_set.create(token=token)
        codes.append(token)
    return codes


@never_cache
@login_required
def mfa_view(request):
    """Ecran unique : verification si un appareil existe, enrolement sinon."""
    user = request.user

    if not user.is_staff:
        return HttpResponseRedirect("/")

    device = confirmed_device(user)

    if request.method == "POST":
        token = (request.POST.get("token") or "").strip().replace(" ", "")

        if device is not None:
            return _verify(request, device, token)
        return _enroll(request, token)

    if device is not None:
        return render(request, "mfa/verify.html", {"user": user})

    pending = pending_device(user)
    return render(
        request,
        "mfa/setup.html",
        {
            "qr_svg": _qr_svg(pending.config_url),
            "secret": pending.bin_key.hex(),
            "config_url": pending.config_url,
        },
    )


def _verify(request, device, token: str):
    # `otp_login` accepte aussi un code de secours : on interroge donc tous
    # les appareils de la personne, pas seulement le TOTP.
    from django_otp import devices_for_user

    for candidate in devices_for_user(request.user):
        if candidate.verify_token(token):
            otp_login(request, candidate)
            return HttpResponseRedirect(_next_url(request))

    messages.error(request, "Code incorrect ou expiré.")
    return render(request, "mfa/verify.html", {"user": request.user})


def _enroll(request, token: str):
    pending = pending_device(request.user)

    if not pending.verify_token(token):
        messages.error(request, "Code incorrect. Vérifiez l'heure de votre téléphone.")
        return render(
            request,
            "mfa/setup.html",
            {
                "qr_svg": _qr_svg(pending.config_url),
                "secret": pending.bin_key.hex(),
                "config_url": pending.config_url,
            },
        )

    pending.confirmed = True
    pending.save(update_fields=["confirmed"])
    otp_login(request, pending)

    codes = _issue_recovery_codes(request.user)
    return render(
        request,
        "mfa/recovery.html",
        {"codes": codes, "next_url": _next_url(request)},
    )


def _next_url(request) -> str:
    candidate = request.GET.get("next") or request.POST.get("next")
    # Redirection ouverte : on n'accepte qu'un chemin interne.
    if candidate and candidate.startswith("/") and not candidate.startswith("//"):
        return candidate
    return reverse("admin:index")


class PlatformAdminMFAMiddleware:
    """Interdit l'administration tant que la session n'est pas verifiee.

    Le controle porte sur la session (`is_verified`), pas seulement sur
    l'existence d'un appareil : un mot de passe vole ne suffit donc jamais,
    meme si la personne a deja enrole son telephone.
    """

    EXEMPT = ("/admin/login", "/admin/logout", "/admin/jsi18n")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if self._requires_mfa(request):
            return HttpResponseRedirect(
                f"{reverse('mfa')}?next={request.get_full_path()}"
            )
        return self.get_response(request)

    def _requires_mfa(self, request) -> bool:
        if not getattr(settings, "PLATFORM_ADMIN_MFA_REQUIRED", True):
            return False
        if not request.path.startswith("/admin/"):
            return False
        if request.path.startswith(self.EXEMPT):
            return False

        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated or not user.is_staff:
            # Non connecte : l'admin gere lui-meme la redirection vers son
            # ecran de connexion.
            return False

        return not user.is_verified()
