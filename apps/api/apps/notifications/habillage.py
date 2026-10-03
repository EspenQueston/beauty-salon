"""Ce qui fait d'un message une vraie notification.

---------------------------------------------------------------------------
Ce qui manquait
---------------------------------------------------------------------------

Le push portait un titre, un texte et l'icone de la plateforme. Sur
Windows, macOS ou Android, le systeme sait afficher bien plus : une grande
image en tete, l'embleme de l'expediteur, l'heure de l'evenement et des
boutons d'action. Une notification sans eux se lit comme un courriel
automatique ; avec eux, comme un message du salon.

Ce module ajoute ces quatre elements a la charge envoyee. Il ne decide pas
des mots — c'est `evenements.py` — mais de tout ce qui les entoure, et il le
fait de la meme facon pour tous les evenements.

---------------------------------------------------------------------------
L'image, et l'ordre dans lequel on la cherche
---------------------------------------------------------------------------

1. La photo liee a l'evenement — celle de la prestation reservee. C'est
   elle qui dit le plus : « Box braids » se reconnait avant d'etre lu.
2. La banniere du salon, celle de son mini-site.
3. Une image composee par le site aux couleurs du salon, avec le
   pictogramme de l'evenement. Il y en a donc toujours une.

Seuls les medias **publics** entrent ici. Une preuve de versement est un
media prive : elle n'a rien a faire sur un ecran verrouille, et son
adresse ne s'ouvrirait de toute facon qu'avec une session.

---------------------------------------------------------------------------
Les boutons
---------------------------------------------------------------------------

Ils ouvrent une page ; ils n'agissent pas. Un bouton « Accepter » executerait
une ecriture depuis le service worker, sans voir le rendez-vous, et sans la
double verification qu'impose l'ecran de l'agenda. Deux au plus : c'est ce
qu'affichent Chrome et Edge.
"""

from __future__ import annotations

import time
from urllib.parse import urlencode

from django.conf import settings

from .models import Genre

#: Les boutons de chaque genre : identifiant, libelle, lien. Un lien vide
#: reprend celui de la notification. Libelles courts : Windows coupe au-dela
#: d'une vingtaine de caracteres.
ACTIONS: dict[str, tuple[tuple[str, str, str], ...]] = {
    Genre.RESERVATION: (
        ("ouvrir", "Voir le rendez-vous", ""),
        ("agenda", "Ouvrir l'agenda", "/agenda"),
    ),
    Genre.ACOMPTE_A_VERIFIER: (
        ("ouvrir", "Vérifier l'acompte", ""),
        ("agenda", "Ouvrir l'agenda", "/agenda"),
    ),
    Genre.ACOMPTE_EXPIRE: (("ouvrir", "Voir le créneau", ""),),
    Genre.ANNULATION: (
        ("ouvrir", "Voir le rendez-vous", ""),
        ("agenda", "Ouvrir l'agenda", "/agenda"),
    ),
    Genre.AVIS: (("ouvrir", "Lire l'avis", ""),),
    Genre.LISTE_ATTENTE: (("ouvrir", "Voir la liste", ""),),
    Genre.SALON_INSCRIT: (("ouvrir", "Examiner le salon", ""),),
    Genre.FACTURE: (("ouvrir", "Voir le détail", ""),),
    Genre.INCIDENT: (("ouvrir", "Voir le détail", ""),),
    Genre.ABONNEMENT: (("ouvrir", "Voir l'abonnement", ""),),
    Genre.PAIEMENT_ABONNEMENT: (("ouvrir", "Vérifier le paiement", ""),),
}

#: Les genres pour lesquels le site sait composer une image. Tenu en phase
#: avec `apps/web/app/notification-image/[genre]/route.tsx`.
IMAGES_COMPOSEES = frozenset(ACTIONS)


def url_publique(asset) -> str:
    """L'adresse absolue d'un media public, ou chaine vide.

    Absolue parce que le systeme affiche la notification hors de toute
    page : une adresse relative n'y designe rien. En production, `MEDIA_URL`
    l'est deja ; en developpement, on la complete avec l'adresse de l'API.
    """
    from apps.media.models import MediaAsset

    if asset is None or not getattr(asset, "file", None):
        return ""
    if asset.visibility != MediaAsset.Visibility.PUBLIC:
        return ""
    url = asset.file.url
    if url.startswith(("http://", "https://")):
        return url
    return f"{settings.API_BASE_URL.rstrip('/')}/{url.lstrip('/')}"


def image_composee(genre: str, salon: str, couleur: str) -> str:
    """L'image composee par le site, aux couleurs du salon.

    Servie par le serveur Next sur l'hote de l'espace pro. Les parametres
    determinent entierement l'image : elle se garde en cache sans fin.
    """
    if genre not in IMAGES_COMPOSEES:
        return ""
    requete = urlencode({"salon": salon[:40], "couleur": couleur.lstrip("#")})
    return f"{settings.APP_BASE_URL.rstrip('/')}/notification-image/{genre}?{requete}"


def apparence(tenant_id) -> dict:
    """Le nom, la couleur, le logo et la banniere d'un salon.

    A appeler dans le contexte du salon : le profil est protege par RLS.
    Un salon sans profil — cree a la main, inscription interrompue — garde
    le nom et la couleur par defaut, et n'a ni logo ni banniere.
    """
    from apps.salons.models import SalonProfile
    from apps.tenants.models import Tenant

    from .tasks import DEFAULT_BRAND, _brand_colour

    nom = (
        Tenant.objects.filter(pk=tenant_id).values_list("name", flat=True).first() or ""
    )
    profil = (
        SalonProfile.objects.filter(tenant_id=tenant_id)
        .select_related("logo", "banner")
        .first()
    )
    return {
        "nom": nom,
        "couleur": _brand_colour(profil) if profil else DEFAULT_BRAND,
        "logo": url_publique(profil.logo) if profil else "",
        "banniere": url_publique(profil.banner) if profil else "",
    }


def actions(genre: str, lien: str) -> list[dict]:
    """Les boutons d'un genre, avec leur destination."""
    return [
        {"id": identifiant, "titre": titre, "lien": propre or lien}
        for identifiant, titre, propre in ACTIONS.get(genre, ())
        if propre or lien
    ]


def habiller(charge: dict, *, genre: str, lien: str, image: str = "", salon=None) -> dict:
    """Complete une charge de push avec son image, son icone et ses boutons.

    `salon` est le resultat d'`apparence()`, ou None hors de tout salon.
    `image` est la photo propre a l'evenement, si l'appelant en a une.
    """
    salon = salon or {}
    return {
        **charge,
        "image": image
        or salon.get("banniere", "")
        or image_composee(genre, salon.get("nom", ""), salon.get("couleur", "")),
        # L'icone par defaut, celle de la plateforme, est posee par le
        # service worker : chacun connait la sienne.
        "icone": salon.get("logo", ""),
        "actions": actions(genre, lien),
        # En millisecondes, comme l'attend `Notification.timestamp`. Un
        # message remis en retard — telephone eteint la nuit — affiche ainsi
        # l'heure de l'evenement, et non celle de sa remise.
        "horodatage": int(time.time() * 1000),
    }
