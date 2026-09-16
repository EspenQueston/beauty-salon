from django.db import connections
from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET


@require_GET
def health(request):
    """Sonde de disponibilite : verifie que la base repond vraiment."""
    try:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:  # noqa: BLE001 - la sonde ne doit jamais lever
        return JsonResponse({"status": "degraded", "database": False}, status=503)
    return JsonResponse({"status": "ok", "database": True})


@require_GET
@ensure_csrf_cookie
def csrf(request):
    """Pose le cookie CSRF avant le premier POST du frontend."""
    return JsonResponse({"detail": "ok"})
