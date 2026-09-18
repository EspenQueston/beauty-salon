"""Import d'un media depuis une adresse web.

---------------------------------------------------------------------------
Pourquoi telecharger plutot que pointer
---------------------------------------------------------------------------

Coller un lien Unsplash ou Pexels est le geste naturel : le salon a trouve
une photo, il en a l'adresse. Garder cette adresse et l'afficher telle quelle
serait plus simple - et une mauvaise idee. Le mini-site dependrait alors d'un
serveur tiers pour s'afficher, une photo retiree laisserait un trou dans la
page, et beaucoup d'hebergeurs refusent purement et simplement d'etre
affiches depuis un autre domaine.

Le fichier est donc copie chez nous, une fois, et le salon en est proprietaire.

---------------------------------------------------------------------------
Ce que cette fonction protege
---------------------------------------------------------------------------

Aller chercher une adresse fournie par un utilisateur, c'est offrir a ce
dernier un client HTTP qui parle depuis *notre* reseau. Sans garde-fous, il
suffirait d'envoyer `http://169.254.169.254/latest/meta-data/` pour lire les
identifiants de la machine, ou `http://localhost:5432` pour sonder la base.
C'est la faille SSRF, et elle se protege en quatre points :

  1. **Schema** : http et https seulement. `file://` lirait le disque,
     `gopher://` sert a fabriquer des requetes arbitraires.
  2. **Adresse resolue** : toute IP privee, locale, de bouclage ou reservee
     est refusee. On verifie l'IP, pas le nom : `interne.exemple.com` peut
     tres bien pointer sur 10.0.0.1.
  3. **Redirections** : suivies a la main, une par une, chacune revalidee.
     Les suivre automatiquement annulerait le controle precedent, puisque
     c'est la cible finale qui compte.
  4. **Taille et type** : lus au fur et a mesure et coupes des le
     depassement, jamais apres avoir tout charge en memoire.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.error import URLError
from urllib.parse import urljoin, urlparse, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from django.core.files.base import ContentFile

from .models import ALLOWED_IMAGE_TYPES, ALLOWED_VIDEO_TYPES, MAX_UPLOAD_BYTES

ALLOWED_TYPES = ALLOWED_IMAGE_TYPES | ALLOWED_VIDEO_TYPES

TIMEOUT_SECONDS = 10
MAX_REDIRECTS = 3
CHUNK = 64 * 1024

# Une adresse sans nom de fichier reste courante (paramètres de requête,
# redirections) : il en faut bien un pour le stockage.
DEFAULT_NAME = "import"

EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
}


class RemoteMediaError(Exception):
    """Import refuse. Le message est destine a l'utilisatrice, en francais."""


def fetch_remote_media(url: str) -> tuple[ContentFile, str]:
    """Telecharge `url` et renvoie `(fichier, type MIME)`.

    Leve `RemoteMediaError` avec un message affichable pour toute adresse
    refusee, injoignable, trop lourde ou d'un format non accepte.
    """
    current = url.strip()

    for _ in range(MAX_REDIRECTS + 1):
        _guard(current)

        request = Request(  # noqa: S310 - le schema est verifie par _guard
            current,
            headers={
                # Certains hebergeurs de photos refusent un client anonyme.
                "User-Agent": "BeautySalon/1.0 (+import media salon)",
                "Accept": "image/*,video/*",
            },
        )

        try:
            response = _open_without_redirect(request)
        except (URLError, OSError, ValueError) as exc:
            raise RemoteMediaError(
                "Cette adresse n'a pas répondu. Vérifiez le lien."
            ) from exc

        with response:
            if response.status in (301, 302, 303, 307, 308):
                location = response.headers.get("Location")
                if not location:
                    raise RemoteMediaError("Cette adresse renvoie vers nulle part.")
                # Revalidee au tour suivant : c'est la cible finale qui compte.
                current = _absolute(current, location)
                continue

            return _read(response, current)

    raise RemoteMediaError("Cette adresse renvoie vers trop de redirections.")


class _StopRedirects(HTTPRedirectHandler):
    """Rend la redirection au code appelant au lieu de la suivre.

    urllib suit les redirections tout seul, ce qui annulerait le controle
    d'adresse : seule la premiere serait verifiee, et c'est la derniere qui
    decide ou l'on se connecte vraiment.
    """

    def redirect_request(self, *args, **kwargs):
        return None


def _open_without_redirect(request: Request):
    return build_opener(_StopRedirects).open(request, timeout=TIMEOUT_SECONDS)


def _read(response, url: str) -> tuple[ContentFile, str]:
    content_type = (response.headers.get_content_type() or "").lower()
    if content_type not in ALLOWED_TYPES:
        raise RemoteMediaError(
            "Ce lien ne pointe pas vers une image ou une vidéo acceptée "
            "(JPEG, PNG, WebP, MP4, WebM)."
        )

    # L'en-tete annoncee est un indice, pas une garantie : elle permet de
    # refuser tot un fichier trop lourd, mais la lecture recompte de toute
    # facon octet par octet.
    declared = response.headers.get("Content-Length")
    if declared and declared.isdigit() and int(declared) > MAX_UPLOAD_BYTES:
        raise RemoteMediaError(_too_big())

    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = response.read(CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_UPLOAD_BYTES:
            # On s'arrete des le depassement : un serveur hostile pourrait
            # servir un flux sans fin.
            raise RemoteMediaError(_too_big())
        chunks.append(chunk)

    if total == 0:
        raise RemoteMediaError("Ce lien renvoie un fichier vide.")

    return ContentFile(b"".join(chunks), name=_filename(url, content_type)), content_type


def _too_big() -> str:
    return f"Ce fichier dépasse {MAX_UPLOAD_BYTES // (1024 * 1024)} Mo."


def _filename(url: str, content_type: str) -> str:
    stem = urlsplit(url).path.rsplit("/", 1)[-1] or DEFAULT_NAME
    stem = stem.split("?")[0][:80] or DEFAULT_NAME

    extension = EXTENSIONS.get(content_type, "")
    if extension and not stem.lower().endswith(extension):
        # L'extension vient du type reel, pas de ce que l'adresse pretend :
        # une adresse « .jpg » qui sert du WebP existe pour de bon.
        stem = f"{stem.rsplit('.', 1)[0] or DEFAULT_NAME}{extension}"
    return stem


def _absolute(base: str, location: str) -> str:
    return urljoin(base, location)


def _guard(url: str) -> None:
    """Refuse tout ce qui ne doit pas etre atteint depuis notre reseau."""
    parts = urlparse(url)

    if parts.scheme not in ("http", "https"):
        raise RemoteMediaError("Seules les adresses http et https sont acceptées.")
    if not parts.hostname:
        raise RemoteMediaError("Cette adresse est incomplète.")

    try:
        infos = socket.getaddrinfo(parts.hostname, parts.port or 0)
    except socket.gaierror as exc:
        raise RemoteMediaError(
            "Ce nom de domaine est introuvable. Vérifiez le lien."
        ) from exc

    for *_, sockaddr in infos:
        address = ipaddress.ip_address(sockaddr[0])
        if not address.is_global or address.is_multicast:
            # `is_global` couvre d'un coup le bouclage, les plages privees,
            # le lien-local (dont 169.254.169.254, les metadonnees cloud) et
            # les plages reservees.
            raise RemoteMediaError(
                "Cette adresse pointe vers un réseau interne et ne peut pas "
                "être importée."
            )
