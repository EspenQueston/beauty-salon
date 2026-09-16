"""Environnement de developpement local."""

from .base import *  # noqa: F403
from .base import PLATFORM_DOMAIN, env

DEBUG = True

API_PORT = env("API_PORT", default="8001")
WEB_PORT = env("WEB_PORT", default="3100")

# Les navigateurs resolvent nativement *.localhost vers la boucle locale
# (RFC 6761) : le routage multi-tenant se developpe sans DNS, sans fichier
# hosts, et sans traverser un eventuel proxy local.
ALLOWED_HOSTS = [f".{PLATFORM_DOMAIN}", "localhost", "127.0.0.1", "[::1]", "testserver"]

CSRF_TRUSTED_ORIGINS = [
    f"http://{PLATFORM_DOMAIN}:{WEB_PORT}",
    f"http://*.{PLATFORM_DOMAIN}:{WEB_PORT}",
    f"http://{PLATFORM_DOMAIN}:{API_PORT}",
    f"http://*.{PLATFORM_DOMAIN}:{API_PORT}",
    f"http://127.0.0.1:{WEB_PORT}",
    f"http://127.0.0.1:{API_PORT}",
]

CORS_ALLOWED_ORIGINS = [
    f"http://127.0.0.1:{WEB_PORT}",
    f"http://localhost:{WEB_PORT}",
]

# ---------------------------------------------------------------------------
# Cookies : portee limitee a l'hote
# ---------------------------------------------------------------------------
# En developpement, le navigateur appelle l'API sur *le meme hostname* que la
# page (seul le port change, et les cookies ignorent le port). Un cookie
# limite a l'hote suffit donc, et c'est preferable :
#
#   - `Domain=.localhost` est refuse ou traite de facon inconstante selon les
#     navigateurs, `localhost` se comportant comme un domaine de premier
#     niveau ;
#   - la session d'un salon ne deborde pas sur les autres sous-domaines, ce
#     qui reproduit mieux le cloisonnement de production.
#
# En production, SESSION_COOKIE_DOMAIN reprend sa valeur de base.py pour
# partager la session entre app. et api.
SESSION_COOKIE_DOMAIN = None
CSRF_COOKIE_DOMAIN = None

SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# Sentry reste inactif tant qu'aucun DSN n'est fourni.
SENTRY_DSN = env("SENTRY_DSN", default="")
if SENTRY_DSN:
    import sentry_sdk

    sentry_sdk.init(dsn=SENTRY_DSN, environment="development", traces_sample_rate=0.1)
