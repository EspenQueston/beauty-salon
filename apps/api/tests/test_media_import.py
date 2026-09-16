"""Import d'un media par son adresse web, et ce qu'il refuse d'atteindre.

Le controle porte sur l'**adresse resolue**, jamais sur le nom : rien
n'empeche `photos.exemple.com` de pointer sur 10.0.0.1. Ces tests remplacent
donc le resolveur pour decider ce que le nom renvoie, ce qui permet de
verifier les deux chemins - accepte et refuse - sans dependre du reseau de la
machine qui execute la suite.

C'est necessaire ici : l'environnement de developpement resout *tous* les
noms vers 198.18.0.x, une plage privee. Le garde-fou y refuse donc meme les
adresses publiques legitimes, et il a raison de le faire au vu de ce qu'il
observe.
"""

import socket

import pytest

from apps.media.fetch import RemoteMediaError, _guard


def resolving_to(monkeypatch, ip: str) -> None:
    """Fait resoudre n'importe quel nom vers `ip`."""

    def fake(host, port, *args, **kwargs):
        family = socket.AF_INET6 if ":" in ip else socket.AF_INET
        return [(family, socket.SOCK_STREAM, 6, "", (ip, port or 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake)


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",  # bouclage
        "10.0.0.5",  # prive
        "192.168.1.10",  # prive
        "172.16.0.9",  # prive
        "169.254.169.254",  # metadonnees cloud
        "0.0.0.0",  # non specifie
        "198.18.0.52",  # plage de test, celle du proxy de developpement
        "::1",  # bouclage IPv6
        "fd00::1",  # unique local IPv6
    ],
)
def test_an_internal_address_is_refused_whatever_the_name(monkeypatch, ip):
    """Un nom public qui pointe vers l'interieur reste refuse."""
    resolving_to(monkeypatch, ip)

    with pytest.raises(RemoteMediaError, match="réseau interne"):
        _guard("https://photos.exemple.com/image.jpg")


@pytest.mark.parametrize("ip", ["93.184.216.34", "2606:2800:220:1:248:1893:25c8:1946"])
def test_a_genuinely_public_address_is_accepted(monkeypatch, ip):
    """Le pendant du test precedent : sans lui, tout refuser passerait pour
    une reussite."""
    resolving_to(monkeypatch, ip)

    _guard("https://images.pexels.com/photos/1/photo.jpeg")  # ne leve pas


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "gopher://exemple.test/x",
        "ftp://exemple.test/photo.jpg",
        "data:image/png;base64,AAAA",
    ],
)
def test_only_http_and_https_are_accepted(url):
    with pytest.raises(RemoteMediaError, match="http"):
        _guard(url)


def test_an_unknown_name_is_reported_as_such(monkeypatch):
    def fails(*args, **kwargs):
        raise socket.gaierror("introuvable")

    monkeypatch.setattr(socket, "getaddrinfo", fails)

    with pytest.raises(RemoteMediaError, match="introuvable"):
        _guard("https://nexiste-pas.exemple/photo.jpg")
