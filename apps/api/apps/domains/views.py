"""Ce que le serveur web a le droit de certifier.

---------------------------------------------------------------------------
Pourquoi cette question se pose
---------------------------------------------------------------------------

Chaque salon a son sous-domaine, cree a l'inscription : ils ne sont pas
connus quand le serveur demarre, et aucun certificat unique ne les couvre
tous tant que le domaine ne permet pas le certificat joker. Caddy obtient
donc le certificat d'un sous-domaine **a la premiere visite** — c'est son
mode « a la demande ».

Laisse sans controle, ce mode certifie n'importe quel nom qu'on lui
presente. Il suffirait de pointer mille noms vers le serveur, ou de
visiter mille sous-domaines inventes, pour epuiser le quota de Let's
Encrypt : plus aucun salon ne recevrait de certificat pendant une semaine.

Avant chaque emission, Caddy pose donc la question ici. La reponse est oui
pour les hotes de la plateforme et pour les domaines enregistres dans la
table de routage — ni plus, ni moins.

---------------------------------------------------------------------------
Qui peut appeler
---------------------------------------------------------------------------

Caddy seul, par le reseau interne. Le proxy refuse `/interne/` a qui vient
de l'exterieur. Et quand bien meme : la route ne dit que ce que n'importe
qui apprend en tapant l'adresse, a savoir si un salon porte ce nom.
"""

from __future__ import annotations

from django.conf import settings
from django.db.models import Q
from django.http import HttpResponse
from django.views.decorators.http import require_GET

from .models import Domain

#: Hotes de la plateforme elle-meme : le site, l'espace pro, l'API, et le
#: `www` que certains tapent par habitude.
SOUS_DOMAINES_PLATEFORME = ("www", "app", "api")


def est_hote_plateforme(hote: str) -> bool:
    domaine = settings.PLATFORM_DOMAIN
    return hote == domaine or hote in {f"{sous}.{domaine}" for sous in SOUS_DOMAINES_PLATEFORME}


def est_domaine_de_salon(hote: str) -> bool:
    """Un domaine actif de la table de routage.

    Un domaine personnalise n'est retenu qu'une fois sa propriete prouvee :
    enregistrer `exemple.com` sans le posseder ne doit pas suffire a faire
    travailler le serveur pour lui.
    """
    return (
        Domain.objects.filter(hostname=hote, active=True)
        .filter(Q(kind=Domain.Kind.PLATFORM_SUBDOMAIN) | Q(verified_at__isnull=False))
        .exists()
    )


@require_GET
def certificat_autorise(request):
    """Reponse attendue par `on_demand_tls { ask … }` : 200 oui, autre chose non."""
    hote = request.GET.get("domain", "").strip().lower().rstrip(".")
    if not hote:
        return HttpResponse(status=400)
    if est_hote_plateforme(hote) or est_domaine_de_salon(hote):
        return HttpResponse(status=200)
    return HttpResponse(status=404)
