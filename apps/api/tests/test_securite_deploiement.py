"""Les reglages de production tiennent-ils vraiment ?

---------------------------------------------------------------------------
Pourquoi ces verifications sont des tests, et pas une page de documentation
---------------------------------------------------------------------------

Une consigne ecrite dans un fichier README se perime le jour ou quelqu'un
ajoute un reglage sans la relire. Un drapeau de securite, lui, se desactive
d'un caractere — `True` en `False` — et rien ne le signale : le site
continue de fonctionner, simplement les cookies repartent en clair.

Ces tests chargent le module de production comme le ferait un deploiement et
verifient ce qu'il produit. Ils echouent avant la mise en ligne, pas apres.
"""

import importlib

import pytest
from django.core.exceptions import ImproperlyConfigured

CLE_VALIDE = "T" + "x" * 63


def charger(monkeypatch, **surcharges):
    """Importe `config.settings.production` avec un environnement choisi."""
    variables = {
        "DJANGO_SECRET_KEY": CLE_VALIDE,
        "PLATFORM_DOMAIN": "beautysalon.app",
        "SENTRY_DSN": "",
        **surcharges,
    }
    for nom, valeur in variables.items():
        monkeypatch.setenv(nom, valeur)

    # `base` d'abord : `PLATFORM_DOMAIN` y est calcule a l'import, et
    # recharger `production` seul reprendrait le module deja en memoire —
    # donc le domaine de la machine de test, pas celui qu'on vient de poser.
    #
    # Recharger ces modules ne touche pas `django.conf.settings`, qui garde
    # l'instantane pris au demarrage de la suite.
    importlib.reload(importlib.import_module("config.settings.base"))
    return importlib.reload(importlib.import_module("config.settings.production"))


# ---------------------------------------------------------------------------
# La cle secrete
# ---------------------------------------------------------------------------
#
# Elle ne signe pas que les sessions : les liens de reinitialisation, les
# jetons de paiement, les codes d'arrivee et les invitations a laisser un
# avis en derivent tous. Qui la connait les forge tous, pour tous les salons.


def test_la_cle_de_developpement_est_refusee(monkeypatch):
    with pytest.raises(ImproperlyConfigured, match="developpement"):
        charger(monkeypatch, DJANGO_SECRET_KEY="dev-only-change-me")


def test_une_cle_trop_courte_est_refusee(monkeypatch):
    with pytest.raises(ImproperlyConfigured, match="50"):
        charger(monkeypatch, DJANGO_SECRET_KEY="trop-courte")


def test_une_cle_absente_arrete_le_demarrage(monkeypatch):
    monkeypatch.delenv("DJANGO_SECRET_KEY", raising=False)
    # `base.py` lit le `.env` du depot : on neutralise sa valeur plutot que
    # de supposer qu'il n'existe pas sur la machine qui execute les tests.
    with pytest.raises((ImproperlyConfigured, Exception)):
        charger(monkeypatch, DJANGO_SECRET_KEY="")


# ---------------------------------------------------------------------------
# Transport et cookies
# ---------------------------------------------------------------------------


def test_les_cookies_ne_partent_jamais_en_clair(monkeypatch):
    reglages = charger(monkeypatch)

    assert reglages.SESSION_COOKIE_SECURE is True
    assert reglages.CSRF_COOKIE_SECURE is True
    assert reglages.SESSION_COOKIE_HTTPONLY is True


def test_le_site_impose_https(monkeypatch):
    reglages = charger(monkeypatch)

    assert reglages.SECURE_SSL_REDIRECT is True
    assert reglages.SECURE_HSTS_SECONDS >= 31_536_000
    # Chaque salon est un sous-domaine : les laisser hors de HSTS rouvrirait
    # la porte qu'on vient de fermer.
    assert reglages.SECURE_HSTS_INCLUDE_SUBDOMAINS is True


def test_le_mode_debug_est_eteint(monkeypatch):
    reglages = charger(monkeypatch)

    assert reglages.DEBUG is False


# ---------------------------------------------------------------------------
# Origines
# ---------------------------------------------------------------------------


def test_aucune_origine_en_clair_n_est_acceptee(monkeypatch):
    """Une page servie en HTTP sur un sous-domaine rendrait le `Secure` des
    cookies contournable."""
    reglages = charger(monkeypatch)

    for motif in reglages.CORS_ALLOWED_ORIGIN_REGEXES:
        assert "https" in motif
        assert "http://" not in motif

    for origine in reglages.CSRF_TRUSTED_ORIGINS:
        assert origine.startswith("https://")


def test_le_domaine_de_la_plateforme_pilote_tout(monkeypatch):
    """Changer de domaine ne doit demander qu'une variable : un domaine code
    en dur quelque part serait un trou le jour du deploiement."""
    reglages = charger(monkeypatch, PLATFORM_DOMAIN="mon-salon.cg")

    assert reglages.ALLOWED_HOSTS == [".mon-salon.cg", "mon-salon.cg"]
    assert "https://*.mon-salon.cg" in reglages.CSRF_TRUSTED_ORIGINS
    assert any("mon-salon" in motif for motif in reglages.CORS_ALLOWED_ORIGIN_REGEXES)


def test_le_point_dans_le_domaine_est_echappe(monkeypatch):
    """Sans echappement, `beautysalon.app` accepterait `beautysalonXapp`, que
    n'importe qui peut deposer."""
    reglages = charger(monkeypatch, PLATFORM_DOMAIN="beautysalon.app")

    import re

    motif = reglages.CORS_ALLOWED_ORIGIN_REGEXES[0]
    assert re.match(motif, "https://app.beautysalon.app")
    assert not re.match(motif, "https://beautysalonXapp")
    assert not re.match(motif, "http://app.beautysalon.app")


# ---------------------------------------------------------------------------
# En-tetes et limites
# ---------------------------------------------------------------------------


def test_la_page_ne_peut_pas_etre_encadree(monkeypatch):
    reglages = charger(monkeypatch)

    assert reglages.X_FRAME_OPTIONS == "DENY"
    assert reglages.SECURE_CONTENT_TYPE_NOSNIFF is True


def test_le_corps_des_requetes_est_borne(monkeypatch):
    """Sans plafond, un corps de plusieurs centaines de mega-octets suffit a
    saturer un processus."""
    reglages = charger(monkeypatch)

    assert reglages.DATA_UPLOAD_MAX_MEMORY_SIZE <= 50 * 1024 * 1024
    assert reglages.DATA_UPLOAD_MAX_NUMBER_FIELDS <= 5_000


def test_la_double_authentification_reste_exigee(monkeypatch):
    """Un compte plateforme ouvre l'alias de base qui contourne les
    politiques RLS : il voit tous les salons a la fois."""
    reglages = charger(monkeypatch)

    assert reglages.PLATFORM_ADMIN_MFA_REQUIRED is True


# ---------------------------------------------------------------------------
# Derriere le proxy, dans les conteneurs
# ---------------------------------------------------------------------------
#
# Ces reglages ne servent a rien en developpement, ou tout tourne sur la
# meme machine. Ils decident en production si les pages s'affichent.


def test_les_noms_internes_s_ajoutent_au_domaine(monkeypatch):
    """Le serveur Next appelle `http://api:8000` : sans ce nom, Django
    repondrait 400 a chaque rendu de mini-site."""
    reglages = charger(
        monkeypatch,
        PLATFORM_DOMAIN="mon-salon.cg",
        DJANGO_INTERNAL_HOSTS="api,127.0.0.1",
    )

    assert reglages.ALLOWED_HOSTS == [".mon-salon.cg", "mon-salon.cg", "api", "127.0.0.1"]


def test_les_medias_ont_une_adresse_absolue(monkeypatch):
    """Relative, l'adresse d'une photo prendrait l'hote de la requete — celui
    du reseau interne quand c'est le serveur Next qui demande."""
    reglages = charger(monkeypatch, PLATFORM_DOMAIN="mon-salon.cg")

    assert reglages.MEDIA_URL == "https://api.mon-salon.cg/media/"


def test_les_liens_des_emails_sont_en_https_et_sans_port(monkeypatch):
    reglages = charger(monkeypatch, PLATFORM_DOMAIN="mon-salon.cg")

    assert reglages.APP_BASE_URL == "https://app.mon-salon.cg"
    assert reglages.SITE_BASE_URL == "https://mon-salon.cg"


def test_seules_les_routes_internes_echappent_a_la_redirection(monkeypatch):
    """La sonde de sante et la question de Caddy arrivent en clair ; tout le
    reste doit toujours etre renvoye vers HTTPS."""
    import re

    reglages = charger(monkeypatch)

    def exemptee(chemin: str) -> bool:
        return any(re.search(motif, chemin) for motif in reglages.SECURE_REDIRECT_EXEMPT)

    assert exemptee("health")
    assert exemptee("interne/certificat")
    assert not exemptee("api/v1/public/salon")
    assert not exemptee("admin/")
    assert not exemptee("api/v1/interne/certificat")
