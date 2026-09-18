"""Reglages communs a tous les environnements.

Point d'attention principal : la section DATABASES declare deux connexions
vers la *meme* base. C'est le socle de l'isolation multi-tenant ; voir
apps/common/db.py et apps/common/rls.py.
"""

import re
from pathlib import Path

import environ
from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve().parent.parent.parent
REPO_ROOT = BASE_DIR.parent.parent

env = environ.Env()
environ.Env.read_env(REPO_ROOT / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY", default="dev-only-change-me")
DEBUG = env.bool("DJANGO_DEBUG", default=False)

# ---------------------------------------------------------------------------
# Domaine plateforme
# ---------------------------------------------------------------------------
# Toute la resolution de tenant part de la. Aucun domaine n'est code en dur :
# passer en production revient a changer cette seule variable.
PLATFORM_DOMAIN = env("PLATFORM_DOMAIN", default="localhost")

# Sous-domaines reserves : ils n'appartiennent a aucun salon.
RESERVED_SUBDOMAINS = {"www", "app", "api", "admin", "static", "media", "mail"}

ALLOWED_HOSTS = [f".{PLATFORM_DOMAIN}", "localhost", "127.0.0.1"]

WEB_PORT = env("WEB_PORT", default="3100")

# Base des liens envoyes par e-mail (invitation, reinitialisation). Ces liens
# pointent vers l'espace professionnel, jamais vers l'API : c'est la que la
# session doit etre ouverte.
APP_BASE_URL = env("APP_BASE_URL", default=f"http://app.{PLATFORM_DOMAIN}:{WEB_PORT}")

# Site public de la plateforme. C'est la destination du lien « Voir le site »
# de l'administration : sans lui, Django pointe sur « / », c'est-a-dire la
# racine de l'API, qui ne rend aucune page.
SITE_BASE_URL = env("SITE_BASE_URL", default=f"http://{PLATFORM_DOMAIN}:{WEB_PORT}")

# Duree de validite des liens de reinitialisation de mot de passe.
PASSWORD_RESET_TIMEOUT = 60 * 60 * 24

# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "corsheaders",
    "drf_spectacular",
    # Double authentification des administrateurs plateforme. Les deux
    # greffons passent par une configuration locale, uniquement pour leur
    # donner un intitulé lisible dans l'administration.
    "django_otp",
    "apps.common.otp_apps.TOTPConfig",
    "apps.common.otp_apps.StaticTokenConfig",
]

LOCAL_APPS = [
    "apps.common",
    "apps.accounts",
    "apps.tenants",
    "apps.domains",
    "apps.salons",
    "apps.staff",
    "apps.catalog",
    "apps.scheduling",
    "apps.customers",
    "apps.media",
    "apps.notifications",
    "apps.audit",
    "apps.billing",
    "apps.reviews",
    "apps.clients",
    "apps.finance",
    "apps.platformledger",
    "apps.store",
    "apps.payments",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # Pose request.user.is_verified(). Doit suivre l'authentification.
    "django_otp.middleware.OTPMiddleware",
    "apps.accounts.mfa.PlatformAdminMFAMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Doit venir apres AuthenticationMiddleware : la resolution du tenant
    # depend de l'utilisateur connecte pour les routes du dashboard.
    "apps.common.middleware.TenantContextMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# ---------------------------------------------------------------------------
# Bases de donnees : deux roles, une seule base
# ---------------------------------------------------------------------------
#   default : role salon_app, NOBYPASSRLS. Toutes les requetes metier.
#             Sans app.tenant_id positionne, les politiques RLS ne laissent
#             passer aucune ligne.
#   admin   : role salon_admin, BYPASSRLS et proprietaire des tables.
#             Migrations, admin plateforme, taches Celery inter-tenants.
DATABASES = {
    "default": {
        **env.db_url("DATABASE_URL"),
        "CONN_MAX_AGE": 60,
        "ATOMIC_REQUESTS": False,
    },
    "admin": {
        **env.db_url("DATABASE_ADMIN_URL"),
        "CONN_MAX_AGE": 60,
        "ATOMIC_REQUESTS": False,
    },
}

DATABASE_ROUTERS = ["apps.common.routers.TenantDatabaseRouter"]

# Les migrations ne s'appliquent que via le role proprietaire :
#   uv run python manage.py migrate --database=admin
# Surcharge a "default" dans les reglages de test (voir settings/test.py).
MIGRATION_DATABASE_ALIAS = "admin"

# Un compte d'administration ouvre l'alias de base qui contourne les
# politiques RLS : un mot de passe seul n'y suffit jamais.
PLATFORM_ADMIN_MFA_REQUIRED = env.bool("PLATFORM_ADMIN_MFA_REQUIRED", default=True)

OTP_TOTP_ISSUER = "Beauty Salon"

# Chemin de l'administration plateforme. Voir config/urls.py : la barre
# finale est obligatoire, Django construit ses sous-chemins par concatenation.
ADMIN_PATH = env("ADMIN_PATH", default="admin/")

# Cle de currencyapi.com, pour convertir un catalogue quand un salon change
# de devise. Vide par defaut : sans elle, le basculement est *refuse* plutot
# qu'effectue a un taux devine — convertir toute une grille tarifaire avec
# dix pour cent d'erreur ne se rattrape pas.
CURRENCY_API_KEY = env("CURRENCY_API_KEY", default="")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# Cache et files d'attente
# ---------------------------------------------------------------------------
REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
    }
}

CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6379/1")
CELERY_RESULT_BACKEND = None
CELERY_TASK_ALWAYS_EAGER = False
CELERY_TIMEZONE = "UTC"
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1

CELERY_BEAT_SCHEDULE = {
    # Balayage regulier plutot qu'une tache planifiee par reservation : rien
    # a revoquer quand un rendez-vous est annule ou deplace.
    "booking-reminders": {
        "task": "apps.notifications.tasks.send_booking_reminders",
        "schedule": crontab(minute="*/15"),
    },
    # Les creneaux payables mais jamais payes sont rendus vite : une pose de
    # quatre heures gelee par un onglet ferme coute une journee de travail.
    #
    # Toutes les cinq minutes, et non dix : la fenetre de reglement est de
    # trente minutes, et un balayage deux fois plus lent rendrait le creneau
    # jusqu'a dix minutes apres l'echeance annoncee. La cliente, elle, voit
    # « delai depasse » des la seconde qui suit - l'etat se calcule, il ne
    # s'attend pas -, mais le creneau ne redevient reservable qu'ici.
    "release-unpaid-bookings": {
        "task": "apps.notifications.tasks.release_unpaid_bookings",
        "schedule": crontab(minute="*/5"),
    },
    # Demandes d'avis apres prestation. Toutes les heures : le delai de
    # politesse est de quelques heures, un balayage plus frequent
    # n'attraperait rien de plus.
    "review-requests": {
        "task": "apps.notifications.tasks.send_review_requests",
        "schedule": crontab(minute=5),
    },
    # Facturation : une passe par jour suffit, la tache est idempotente.
    "billing-cycle": {
        "task": "apps.billing.tasks.run_billing_cycle",
        "schedule": crontab(hour=3, minute=0),
    },
}

# ---------------------------------------------------------------------------
# Sessions, CSRF et CORS
# ---------------------------------------------------------------------------
# Le cookie est pose sur le domaine parent pour etre partage entre
# app.PLATFORM_DOMAIN (dashboard) et api.PLATFORM_DOMAIN (API).
SESSION_COOKIE_DOMAIN = f".{PLATFORM_DOMAIN}"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14

CSRF_COOKIE_DOMAIN = f".{PLATFORM_DOMAIN}"
CSRF_COOKIE_HTTPONLY = False  # lu par le frontend pour renvoyer le header
CSRF_COOKIE_SAMESITE = "Lax"

_DOMAIN_RE = re.escape(PLATFORM_DOMAIN)

CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_ORIGIN_REGEXES = [rf"^https?://([a-z0-9-]+\.)*{_DOMAIN_RE}(:\d+)?$"]
CORS_ALLOW_HEADERS = [
    "accept",
    "authorization",
    "content-type",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
    "x-tenant-host",  # mini-site public : quel salon est demande
    "x-tenant-id",  # dashboard : quel salon parmi mes memberships
    "idempotency-key",
]

# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "apps.common.pagination.DefaultPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "public_read": "120/min",
        "booking_create": "10/hour",
        # S'inscrire sur une liste d'attente est plus anodin que reserver -
        # rien n'est bloque - mais reste une ecriture publique.
        "waitlist_create": "20/hour",
        # Envoi d'une preuve de versement. Plus permissif qu'une reservation :
        # une capture illisible se renvoie, et le salon peut refuser plusieurs
        # fois de suite sans que la cliente se retrouve bloquee. Assez bas
        # tout de meme pour qu'on ne televerse pas des images en boucle.
        "deposit_proof": "30/hour",
        "login": "10/min",
        # Creation de compte et envoi d'e-mails : bornes basses, ce sont des
        # actions rares pour un humain et attirantes pour un robot.
        "signup": "5/hour",
        "password_reset": "5/hour",
        "invitation_accept": "10/hour",
    },
    "EXCEPTION_HANDLER": "apps.common.exceptions.api_exception_handler",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Beauty Salon API",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

# ---------------------------------------------------------------------------
# Internationalisation
# ---------------------------------------------------------------------------
# Francais seul au lancement, mais tout passe par gettext : ajouter une
# langue ne demandera aucune reecriture.
LANGUAGE_CODE = "fr"
LANGUAGES = [("fr", "Francais")]
LOCALE_PATHS = [BASE_DIR / "locale"]
USE_I18N = True
USE_TZ = True
TIME_ZONE = "UTC"  # tout est stocke en UTC, converti au fuseau du salon

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
# Habillage de l'administration plateforme (static/admin/platform.css).
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# ---------------------------------------------------------------------------
# E-mail
# ---------------------------------------------------------------------------
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST", default="localhost")
EMAIL_PORT = env.int("EMAIL_PORT", default=1025)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")

# 465 = SSL implicite (la connexion est chiffrée d'emblée) ; 587 = STARTTLS
# (la connexion démarre en clair puis bascule). Les deux s'excluent, et
# Django lève une erreur si les deux drapeaux sont vrais — d'où la déduction
# à partir du port plutôt que deux variables d'environnement à tenir
# cohérentes à la main.
EMAIL_USE_SSL = env.bool("EMAIL_USE_SSL", default=EMAIL_PORT == 465)
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=EMAIL_PORT == 587)

# Sans délai maximal, un serveur SMTP injoignable bloque le worker Celery
# jusqu'au timeout par défaut du système — plusieurs minutes par message.
EMAIL_TIMEOUT = env.int("EMAIL_TIMEOUT", default=20)

# L'expéditeur doit appartenir au domaine authentifié, sinon les serveurs
# destinataires classent le message en usurpation (SPF/DMARC).
DEFAULT_FROM_EMAIL = env(
    "DEFAULT_FROM_EMAIL",
    default=EMAIL_HOST_USER or f"noreply@{PLATFORM_DOMAIN}",
)
SERVER_EMAIL = env("SERVER_EMAIL", default=DEFAULT_FROM_EMAIL)

# ---------------------------------------------------------------------------
# Journalisation
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "{levelname} {asctime} {name} {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        # Toute tentative d'acces croise doit rester visible.
        "apps.common.middleware": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}
