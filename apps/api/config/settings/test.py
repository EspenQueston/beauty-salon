"""Reglages de la suite de tests.

Les tests doivent s'executer avec les politiques RLS *reellement actives* :
c'est tout l'interet des tests d'isolation. On garde donc les deux roles,
mais la base de test est unique et partagee par les deux alias.
"""

from .base import *  # noqa: F403
from .base import DATABASES, PLATFORM_DOMAIN

DEBUG = False

ALLOWED_HOSTS = [f".{PLATFORM_DOMAIN}", "localhost", "127.0.0.1", "testserver"]

# Django cree la base de test via l'alias `default` (role salon_app, soumis
# aux politiques). L'alias `admin` pointe vers cette meme base de test sans
# la recreer : il ne change que le role utilise pour s'y connecter.
DATABASES["admin"]["TEST"] = {"MIRROR": "default"}

# Les migrations doivent s'appliquer sur la base de test elle-meme.
MIGRATION_DATABASE_ALIAS = "default"

# Pas de Redis requis pour lancer les tests.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "test",
    }
}

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Desactivee par defaut pour ne pas alourdir chaque test d'admin ; les tests
# qui la concernent la reactivent explicitement avec override_settings.
PLATFORM_ADMIN_MFA_REQUIRED = False

# Le throttling fausserait les tests fonctionnels ; il a sa propre suite.
# Les portees sont deduites de celles de base.py plutot que reecrites : une
# nouvelle portee ajoutee cote production ne fait pas echouer la suite avec
# une erreur de configuration obscure.
REST_FRAMEWORK = {  # noqa: F405
    **globals()["REST_FRAMEWORK"],
    "DEFAULT_THROTTLE_RATES": dict.fromkeys(
        globals()["REST_FRAMEWORK"]["DEFAULT_THROTTLE_RATES"], "1000/min"
    ),
}
