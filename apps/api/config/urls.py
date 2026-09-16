from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.accounts.mfa import mfa_view
from apps.common.views import csrf, health

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
    path("api/v1/csrf", csrf, name="csrf"),
    path("api/v1/", include("config.api_urls")),
]

if settings.DEBUG:
    # Le schema n'est jamais expose en production : rien ne l'exige et il
    # decrit toute la surface d'attaque.
    urlpatterns += [
        path("api/schema", SpectacularAPIView.as_view(), name="schema"),
        path(
            "api/docs",
            SpectacularSwaggerView.as_view(url_name="schema"),
            name="docs",
        ),
    ]
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
