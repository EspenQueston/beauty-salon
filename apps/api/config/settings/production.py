"""Reglages de production.

---------------------------------------------------------------------------
Pourquoi ce fichier existe
---------------------------------------------------------------------------

Il n'y en avait pas. `base.py` porte des valeurs prudentes mais neutres, et
`development.py` desserre tout ce qu'il faut pour travailler en local : HTTP
en clair, cookies non securises, DEBUG actif. Deployer avec l'un ou l'autre
revenait donc a mettre en ligne soit une configuration a moitie reglee, soit
la configuration de developpement.

Le controle `manage.py check --deploy` le disait mot pour mot : HSTS absent,
pas de redirection HTTPS, cle secrete faible, cookies de session et CSRF sans
l'attribut `Secure`. Ce module repond aux cinq.

---------------------------------------------------------------------------
Le principe : echouer au demarrage, jamais en silence
---------------------------------------------------------------------------

Une configuration de securite qui retombe sur une valeur par defaut est pire
que pas de configuration du tout : elle donne l'apparence du reglage. Ici,
une variable manquante arrete le processus avec un message qui dit laquelle.
Un deploiement qui refuse de demarrer se voit ; une cle secrete de
developpement en production, non.
"""

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403
from .base import PLATFORM_DOMAIN, env

DEBUG = False

# ---------------------------------------------------------------------------
# La cle secrete
# ---------------------------------------------------------------------------
# Elle ne signe pas seulement les sessions. Tout ce produit en depend : les
# liens de reinitialisation de mot de passe, les jetons de paiement, les
# codes d'arrivee, les invitations a laisser un avis. Qui la connait peut
# forger n'importe lequel d'entre eux, pour n'importe quel salon.
#
# D'ou trois refus, et aucun repli.
SECRET_KEY = env("DJANGO_SECRET_KEY")

if SECRET_KEY in ("", "dev-only-change-me"):
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY porte encore la valeur de developpement. "
        "Generez-en une : python -c \"import secrets; print(secrets.token_urlsafe(64))\""
    )
if len(SECRET_KEY) < 50:
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY doit faire au moins 50 caracteres (Django, W009)."
    )

# ---------------------------------------------------------------------------
# Hotes autorises
# ---------------------------------------------------------------------------
# Le point initial couvre tous les sous-domaines : chaque salon a le sien, et
# ils ne sont pas connus a l'avance. Le domaine nu reste necessaire pour le
# site de la plateforme.
#
# S'y ajoutent les noms du reseau interne (`api`, `127.0.0.1`) : le serveur
# Next rend les pages en appelant `http://api:8000` sans passer par le
# proxy, Caddy y pose sa question avant chaque certificat, et la sonde de
# sante du conteneur frappe `127.0.0.1`. Ces noms ne sont joignables que de
# l'interieur : le proxy n'aiguille vers l'API que les requetes adressees a
# `api.<domaine>`, et aucun autre nom ne l'atteint depuis l'exterieur.
ALLOWED_HOSTS = [
    f".{PLATFORM_DOMAIN}",
    PLATFORM_DOMAIN,
    *env.list("DJANGO_INTERNAL_HOSTS", default=[]),
]

# ---------------------------------------------------------------------------
# HTTPS de bout en bout
# ---------------------------------------------------------------------------
# Derriere un reverse proxy, Django ne voit qu'une connexion HTTP interne :
# sans cet en-tete il croit la requete non chiffree, redirige vers HTTPS, et
# le proxy la renvoie — boucle infinie. L'en-tete n'est digne de confiance
# que parce que le proxy l'ecrase systematiquement ; ne l'activez pas si vous
# exposez l'application en direct.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)

# Deux routes ne sont jamais appelees par un navigateur, et toujours en
# clair sur le reseau interne : la sonde de sante, et la question que Caddy
# pose avant chaque certificat. Redirigees vers HTTPS, la premiere
# declarerait le conteneur malade, et la seconde ferait refuser tous les
# certificats de salon — Caddy lit une redirection comme un « non ».
SECURE_REDIRECT_EXEMPT = [r"^health$", r"^interne/"]

# Un an, sous-domaines compris : chaque salon est un sous-domaine, et les
# laisser hors de HSTS laisserait ouverte la porte qu'on vient de fermer.
#
# `preload` reste optionnel et desactive par defaut : l'inscription sur la
# liste des navigateurs est **irreversible a l'echelle de plusieurs mois**.
# On ne coche cette case qu'une fois le certificat en place et verifie sur
# tous les sous-domaines.
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=31_536_000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = env.bool("SECURE_HSTS_PRELOAD", default=False)

# ---------------------------------------------------------------------------
# Adresses publiques
# ---------------------------------------------------------------------------
# Les medias sont servis par le proxy, sur l'hote de l'API. L'adresse est
# **absolue**, et c'est ce qui la rend juste.
#
# Relative, Django la completerait avec l'hote de la requete. Or une partie
# des requetes vient du serveur Next, qui appelle `http://api:8000` pour
# rendre une page : les photos du salon sortaient alors en
# `http://api:8000/media/…`, adresse qu'aucun navigateur ne peut joindre, et
# chaque mini-site s'affichait sans une image. Une URL absolue traverse
# `build_absolute_uri` sans etre touchee.
MEDIA_URL = env("MEDIA_URL", default=f"https://api.{PLATFORM_DOMAIN}/media/")

# Liens des e-mails. `base.py` les compose pour le developpement — `http`
# et le port 3100 — ce qui, en production, enverrait chaque cliente vers
# une adresse morte.
APP_BASE_URL = env("APP_BASE_URL", default=f"https://app.{PLATFORM_DOMAIN}")
SITE_BASE_URL = env("SITE_BASE_URL", default=f"https://{PLATFORM_DOMAIN}")

# ---------------------------------------------------------------------------
# Cookies
# ---------------------------------------------------------------------------
# `Secure` : le cookie ne part jamais en clair, donc jamais sur un reseau
# Wi-Fi partage. C'est la contre-mesure au vol de session par ecoute, et le
# controle de deploiement de Django la reclame explicitement (W012, W016).
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# `SameSite=Lax` et non `Strict` : la session est partagee entre
# app.DOMAINE et api.DOMAINE, et `Strict` la supprimerait au premier saut
# entre les deux. `Lax` bloque deja les requetes intersites dangereuses —
# POST, PUT, DELETE — ce qui est precisement la surface CSRF.
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

# Django refuse toute ecriture dont l'origine n'est pas listee ici des lors
# que la connexion est en HTTPS. Le joker ne couvre qu'un niveau de
# sous-domaine, ce qui correspond exactement au plan d'adressage : un salon
# par sous-domaine, jamais deux niveaux.
CSRF_TRUSTED_ORIGINS = [
    f"https://{PLATFORM_DOMAIN}",
    f"https://*.{PLATFORM_DOMAIN}",
]

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
# `base.py` accepte http et https, ce qui convient au developpement. En
# production, une origine en clair ne doit jamais etre reconnue : elle
# rendrait le `Secure` des cookies contournable par une page servie en HTTP
# sur un sous-domaine.
_DOMAINE = PLATFORM_DOMAIN.replace(".", r"\.")
CORS_ALLOWED_ORIGIN_REGEXES = [rf"^https://([a-z0-9-]+\.)*{_DOMAINE}$"]

# ---------------------------------------------------------------------------
# En-tetes de reponse
# ---------------------------------------------------------------------------
# Pas d'affichage dans une iframe : sans cela, une page tierce peut
# superposer un cadre invisible au-dessus d'un bouton et faire cliquer la
# gerante sur « supprimer » en lui faisant croire qu'elle clique ailleurs.
X_FRAME_OPTIONS = "DENY"

# Le navigateur s'en tient au type declare. Une image televersee qui
# contiendrait du HTML ne sera donc jamais interpretee comme une page.
SECURE_CONTENT_TYPE_NOSNIFF = True

# L'adresse d'un mini-site ne suit pas les liens sortants : le nom du salon
# et celui de sa cliente n'ont pas a figurer dans les journaux d'un tiers.
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

# ---------------------------------------------------------------------------
# Limites de requete
# ---------------------------------------------------------------------------
# Le televersement de medias passe par son propre plafond (15 Mo, verifie
# dans le serializer). Celui-ci borne tout le reste : un corps JSON de
# plusieurs mega-octets n'a aucune raison d'exister, et en accepter un
# revient a offrir un epuisement memoire gratuit.
DATA_UPLOAD_MAX_MEMORY_SIZE = env.int("DATA_UPLOAD_MAX_MEMORY_SIZE", default=20 * 1024 * 1024)
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
# Un formulaire du produit compte quelques dizaines de champs. Mille est
# large ; cent mille, la valeur par defaut, sert surtout a saturer un
# processus.
DATA_UPLOAD_MAX_NUMBER_FIELDS = 1_000

# ---------------------------------------------------------------------------
# Observabilite
# ---------------------------------------------------------------------------
SENTRY_DSN = env("SENTRY_DSN", default="")
if SENTRY_DSN:
    import sentry_sdk

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment="production",
        traces_sample_rate=env.float("SENTRY_TRACES_SAMPLE_RATE", default=0.05),
        # Aucune donnee personnelle dans les rapports d'erreur : ni adresse
        # e-mail, ni adresse IP, ni corps de requete. Un outil de supervision
        # n'est pas un endroit ou stocker le fichier clientes d'un salon.
        send_default_pii=False,
    )
