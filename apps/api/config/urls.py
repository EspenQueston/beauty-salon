from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.accounts.mfa import mfa_view
from apps.common.views import csrf, health
from apps.domains.views import certificat_autorise
from apps.notifications.views_sw import service_worker_admin

admin.site.site_header = "Beauty Salon - Administration plateforme"
admin.site.site_title = "Beauty Salon"
admin.site.index_title = "Supervision"
# « Voir le site » pointe par defaut sur « / », qui est ici la racine de
# l'API : aucune page a afficher. Le site public vit sur un autre hote.
admin.site.site_url = settings.SITE_BASE_URL

"""
Chemin de l'administration plateforme.

`admin/` par defaut : rien ne change pour qui a l'adresse en signet. La
variable existe parce que ce chemin est la premiere chose que balaient les
robots, et qu'un compte d'administration ouvre l'alias de base qui
contourne les politiques RLS — il voit donc tous les salons a la fois.

Ce n'est pas une protection : le secret d'une URL n'en est jamais une, et la
double authentification reste ce qui tient la porte. C'est une facon de ne
pas figurer dans les journaux de tentatives automatisees.
"""
ADMIN_PATH = settings.ADMIN_PATH

urlpatterns = [
    path(ADMIN_PATH, admin.site.urls),
    # Hors du site d'administration : c'est l'ecran qui debloque son acces.
    path("mfa", mfa_view, name="mfa"),
    path("health", health, name="health"),
    # Interroge par Caddy avant d'emettre un certificat, par le reseau
    # interne seulement : voir apps/domains/views.py.
    path("interne/certificat", certificat_autorise, name="certificat-autorise"),
    path("api/v1/csrf", csrf, name="csrf"),
    # Le service worker de l'administration, a la racine de l'hote.
    # Servi depuis `/static/`, sa portee ne couvrirait pas les pages
    # d'administration : voir apps/notifications/views_sw.py.
    path("sw-admin.js", service_worker_admin, name="sw-admin"),
    path("api/v1/", include("config.api_urls")),
]

if settings.DEBUG:
    """
    La racine mene a l'administration — en developpement seulement.

    -----------------------------------------------------------------------
    Pourquoi ce raccourci existe
    -----------------------------------------------------------------------

    Ce port sert une API, pas un site : il n'y a rien a afficher sur « / »,
    et Django repondait donc 404 avec la liste de ses routes. C'est correct,
    et c'est tout de meme une perte de temps — on tape l'adresse du serveur
    qu'on vient de lancer, on tombe sur une page jaune, et il faut lire une
    URLconf pour apprendre que l'ecran cherche est sous `admin/`.

    -----------------------------------------------------------------------
    Et pourquoi il reste en developpement
    -----------------------------------------------------------------------

    En production, cette redirection annoncerait le chemin de
    l'administration a quiconque visite la racine — c'est-a-dire l'inverse
    exact de ce que permet `ADMIN_PATH`. Le 404 y est la bonne reponse : une
    API n'a pas de page d'accueil, et le silence ne renseigne personne.
    """
    from django.views.generic import RedirectView

    urlpatterns += [
        path("", RedirectView.as_view(url=f"/{ADMIN_PATH}", permanent=False)),
        # Le schema n'est jamais expose en production : rien ne l'exige et il
        # decrit toute la surface d'attaque.
        path("api/schema", SpectacularAPIView.as_view(), name="schema"),
        path(
            "api/docs",
            SpectacularSwaggerView.as_view(url_name="schema"),
            name="docs",
        ),
    ]
    """
    Fichiers media en developpement — sauf les prives.

    `static()` sert tout ce qui est sous MEDIA_ROOT, y compris `prive/` ou
    dorment les preuves de versement. En developpement comme en production,
    ces fichiers ne doivent sortir que par `/api/v1/media/<id>/fichier`, qui
    verifie l'appartenance au salon.

    La vue de refus passe *avant* : Django prend la premiere route qui
    correspond, et un motif plus specifique place apres ne serait jamais
    atteint.

    En production, c'est au serveur web de poser la meme regle :
        location /media/prive/ { deny all; }
    """
    from django.http import Http404

    def _media_prive_refuse(request, chemin):
        raise Http404("Ce fichier ne se lit que par la route authentifiée.")

    # Django normalise MEDIA_URL avec une barre initiale ; les motifs
    # d'URL, eux, sont relatifs a la racine et n'en veulent pas.
    _media = settings.MEDIA_URL.lstrip("/")
    urlpatterns += [
        re_path(rf"^{_media}prive/(?P<chemin>.*)$", _media_prive_refuse),
    ]
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
