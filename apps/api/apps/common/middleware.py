"""Resolution du tenant a chaque requete.

La regle de securite tient en une phrase : **la source du tenant depend de la
route, jamais de ce que le client affirme**.

- `/api/v1/public/...` : le tenant vient du hostname (ou du header
  `X-Tenant-Host` que pose le serveur Next.js). Ces routes n'exposent que des
  donnees publiques ; laisser le client choisir le salon est le comportement
  attendu.
- `/api/v1/account/...` : aucun tenant. Inscription, mot de passe oublie et
  invitation ne concernent pas un salon en particulier - et s'inscrire alors
  qu'on est deja connecte a un autre salon doit rester possible.
- Tout le reste : le tenant vient des memberships de l'utilisateur connecte.
  Un `X-Tenant-Host` falsifie n'a aucun effet, et un `X-Tenant-Id` qui ne
  correspond a aucun membership actif donne un 403 journalise.
"""

import logging

from django.core.exceptions import ValidationError
from django.http import JsonResponse

from .db import tenant_context

logger = logging.getLogger(__name__)

PUBLIC_API_PREFIX = "/api/v1/public/"

# Routes de compte : elles n'appartiennent a aucun salon.
ACCOUNT_API_PREFIX = "/api/v1/account/"

# Routes servies sans ouvrir de transaction ni de contexte tenant.
EXEMPT_PREFIXES = ("/static/", "/media/", "/health")


class TenantNotFound(Exception):
    pass


class TenantForbidden(Exception):
    pass


class TenantAmbiguous(Exception):
    pass


class TenantContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.tenant_id = None
        request.membership = None

        if request.path.startswith(EXEMPT_PREFIXES):
            return self.get_response(request)

        try:
            tenant_id = self._resolve(request)
        except TenantNotFound:
            return JsonResponse(
                {"detail": "Salon introuvable.", "code": "tenant_not_found"}, status=404
            )
        except TenantForbidden:
            logger.warning(
                "Acces refuse : l'utilisateur %s a demande le tenant %s sans membership actif.",
                getattr(request.user, "pk", None),
                request.headers.get("X-Tenant-Id"),
            )
            return JsonResponse(
                {"detail": "Accès refusé à ce salon.", "code": "tenant_forbidden"}, status=403
            )
        except TenantAmbiguous:
            return JsonResponse(
                {
                    "detail": "Précisez le salon avec l'en-tête X-Tenant-Id.",
                    "code": "tenant_ambiguous",
                },
                status=400,
            )

        request.tenant_id = tenant_id
        with tenant_context(tenant_id):
            return self.get_response(request)

    # -- resolution ---------------------------------------------------------

    def _resolve(self, request) -> str | None:
        # Volontairement avant tout le reste : une inscription ne doit pas
        # heriter du salon auquel la personne est deja connectee.
        if request.path.startswith(ACCOUNT_API_PREFIX):
            return None

        if request.path.startswith(PUBLIC_API_PREFIX):
            return self._from_host(request)

        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            return self._from_membership(request, user)

        return None

    def _from_host(self, request) -> str:
        from apps.domains.services import resolve_tenant_id

        hostname = request.headers.get("X-Tenant-Host") or request.get_host()
        hostname = hostname.split(":")[0].strip().lower()

        tenant_id = resolve_tenant_id(hostname)
        if tenant_id is None:
            raise TenantNotFound
        return tenant_id

    def _from_membership(self, request, user) -> str | None:
        from apps.accounts.models import Membership

        memberships = Membership.objects.filter(user=user, status=Membership.Status.ACTIVE)
        requested = request.headers.get("X-Tenant-Id")

        if requested:
            try:
                membership = memberships.filter(tenant_id=requested).first()
            except (ValidationError, ValueError):
                raise TenantForbidden from None
            if membership is None:
                raise TenantForbidden
        else:
            found = list(memberships.select_related("tenant")[:2])
            if not found:
                # Administrateur plateforme, ou compte sans salon : pas de
                # contexte tenant, donc aucune donnee salon visible.
                return None
            if len(found) > 1:
                raise TenantAmbiguous
            membership = found[0]

        request.membership = membership
        return str(membership.tenant_id)
