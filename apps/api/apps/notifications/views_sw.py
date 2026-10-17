"""Le service worker de l'administration, servi depuis la racine.

---------------------------------------------------------------------------
Pourquoi il ne peut pas rester dans `/static/`
---------------------------------------------------------------------------

Un service worker ne gouverne que les chemins situes **sous le sien**. Servi
depuis `/static/notifications/sw-admin.js`, sa portee serait
`/static/notifications/` : il ne verrait aucune page de l'administration.

Le push fonctionnerait tout de meme — un push arrive au service worker quelle
que soit sa portee —, mais `clients.matchAll()` et la reprise de l'onglet
existant deviendraient hasardeuses. Un clic sur une notification ouvrirait un
nouvel onglet a chaque fois, et l'on finirait avec dix onglets de la meme
administration.

Cette vue existe donc pour une seule raison : poser le fichier a la racine.

---------------------------------------------------------------------------
Pourquoi on lit le fichier source et non le fichier collecte
---------------------------------------------------------------------------

`ManifestStaticFilesStorage` renomme les fichiers avec une empreinte, et
`staticfiles_storage.path()` leve une exception avec certains stockages
distants. Le fichier source, lui, est toujours la, et il n'a pas besoin
d'empreinte : le navigateur re-verifie un service worker a chaque chargement,
c'est la norme qui l'impose.
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_GET

CHEMIN = Path(settings.BASE_DIR) / "static" / "notifications" / "sw-admin.js"


@require_GET
# Pas de cache : un service worker corrige doit prendre effet au prochain
# chargement, pas dans vingt-quatre heures. Les navigateurs le re-verifient de
# toute facon, mais un cache intermediaire, lui, ne le sait pas.
@cache_control(no_cache=True, max_age=0)
def service_worker_admin(request):
    if not CHEMIN.exists():  # pragma: no cover - fichier versionne
        raise Http404("Service worker introuvable.")

    return FileResponse(
        CHEMIN.open("rb"),
        content_type="text/javascript; charset=utf-8",
        # Explicite : certains proxys refusent d'elargir la portee d'un
        # service worker sans cet en-tete, et le symptome est un
        # enregistrement qui echoue sans message utile.
        headers={"Service-Worker-Allowed": "/"},
    )
