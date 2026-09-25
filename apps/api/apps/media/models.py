"""Photos et videos courtes des realisations.

Les fichiers ne sont jamais stockes en base : seulement leur cle. En
developpement le stockage est local ; le passage a R2/S3 se fera en changeant
STORAGES, sans toucher au modele ni aux vues.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import TenantOwnedModel

# Formats acceptes a l'upload. Verifies cote serveur, jamais seulement dans
# le navigateur.
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_VIDEO_TYPES = {"video/mp4", "video/webm"}
MAX_UPLOAD_BYTES = 15 * 1024 * 1024


# Prefixe des fichiers prives, sous MEDIA_ROOT.
#
# Il existe pour qu'une regle de serveur web puisse les refuser d'un seul
# trait : `location /media/prive/ { deny all; }`. Sans separation dans le
# chemin, il faudrait connaitre la visibilite de chaque fichier pour decider
# s'il peut sortir - ce qu'un serveur de fichiers statiques ne saura jamais.
PRIVATE_PREFIX = "prive"


def upload_to(instance, filename: str) -> str:
    """Chemin de stockage, separe selon la visibilite.

    -----------------------------------------------------------------------
    Pourquoi les fichiers prives changent de racine
    -----------------------------------------------------------------------

    Une preuve de versement porte le nom d'une cliente et parfois son solde
    bancaire. Elle etait rangee sous la meme racine que les photos de
    coiffure, et n'etait donc protegee que par l'imprevisibilite de son
    adresse : deux UUID, soit 244 bits. Indevinable, certes - mais une
    adresse se partage, se retrouve dans un journal de proxy, dans un
    `Referer`. L'imprevisibilite n'est pas un controle d'acces.

    Sous `prive/`, le fichier n'est plus servi par le serveur de fichiers
    statiques du tout. Il ne sort que par la route authentifiee
    `/api/v1/media/<id>/fichier`, qui verifie l'appartenance au salon avant
    de le lire.

    Le tenant reste dans le chemin des deux cotes : un fichier mal reference
    reste tracable.

    -----------------------------------------------------------------------
    Pourquoi l'extension ne vient jamais du nom televerse
    -----------------------------------------------------------------------

    Le serveur de fichiers deduit le type servi de l'extension. Le type
    verifie a l'envoi est celui qu'annonce le navigateur ; le nom, lui, est
    libre. `page.html` annonce `image/png` passait donc la verification et
    sortait en page HTML sur le domaine de l'API — celui de la session et de
    l'administration. L'extension est ici tiree du type verifie, et le nom
    reduit a des caracteres sans danger.
    """
    nom = f"{_radical(filename)}{EXTENSIONS.get((instance.content_type or '').lower(), '.bin')}"
    base = f"tenants/{instance.tenant_id}/media/{instance.id}/{nom}"
    if instance.visibility == MediaAsset.Visibility.PRIVATE:
        return f"{PRIVATE_PREFIX}/{base}"
    return base


# L'extension de chaque type accepte : c'est elle qui decidera du type servi.
EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
}


def _radical(filename: str) -> str:
    """Le nom sans extension, reduit a des lettres, chiffres, `-` et `_`."""
    import os
    import re

    radical = os.path.splitext(os.path.basename(filename or ""))[0]
    radical = re.sub(r"[^A-Za-z0-9_-]+", "-", radical).strip("-")[:60]
    return radical or "media"


class MediaAsset(TenantOwnedModel):
    class Kind(models.TextChoices):
        """A quoi sert cette image.

        -------------------------------------------------------------------
        Pourquoi il en a fallu davantage
        -------------------------------------------------------------------

        `gallery` etait la valeur par defaut de **tout** televersement, quel
        que soit l'ecran d'origine : le selecteur de medias est partage, et
        personne ne disait au serveur ce que l'image allait devenir. Un QR
        code de paiement, une photo d'article, l'image de la page « A
        propos » arrivaient donc tous etiquetes « galerie ».

        Tant que l'image finissait rattachee a son emploi, l'exclusion par
        cle etrangere la retirait des realisations. Mais un televersement
        qu'on ne rattache pas - on se trompe de fichier, on en essaie deux,
        on en change plus tard - restait « galerie » pour toujours. C'est
        ainsi que des QR codes se sont retrouves sur la page des
        realisations d'un salon, a cote de ses coiffures.

        L'emploi est desormais declare **au televersement**, par l'ecran qui
        sait ce qu'il fait. « galerie » redevient ce qu'il aurait toujours du
        etre : le choix explicite de publier une realisation, et rien
        d'autre.
        """

        GALLERY = "gallery", _("Galerie")
        LOGO = "logo", _("Logo")
        BANNER = "banner", _("Bannière")
        SERVICE = "service", _("Prestation")
        STAFF = "staff", _("Prestataire")
        PAYMENT = "payment", _("QR de paiement")
        # Le QR qui ajoute le salon en contact WeChat. Distinct de
        # `payment` : l'un encaisse un acompte, l'autre ouvre une
        # conversation. Les confondre ferait payer une cliente qui voulait
        # poser une question - et les deux images se ressemblent assez pour
        # qu'un genre commun rende l'erreur facile.
        WECHAT = "wechat", _("QR de contact WeChat")
        ABOUT = "about", _("Page À propos")
        PRODUCT = "product", _("Article de boutique")
        # La capture de paiement envoyee par une cliente. Elle porte son nom
        # et parfois son solde bancaire : c'est la piece la plus sensible de
        # toute la reserve.
        #
        # Elle etait deja rangee en `private`, ce qui la tenait hors de la
        # vitrine publique - mais sous le genre « galerie », donc visible
        # dans la mediatheque du salon, entre ses photos de coiffures. Et la
        # protection ne tenait qu'a un seul drapeau : quiconque basculait la
        # visibilite la publiait.
        PROOF = "proof", _("Preuve de versement")

    class Visibility(models.TextChoices):
        PUBLIC = "public", _("Publique")
        PRIVATE = "private", _("Privée")

    file = models.FileField(upload_to=upload_to, max_length=500)
    content_type = models.CharField(max_length=100)
    byte_size = models.PositiveIntegerField(default=0)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.GALLERY)
    visibility = models.CharField(
        max_length=10, choices=Visibility.choices, default=Visibility.PUBLIC
    )

    alt_text = models.CharField(max_length=255, blank=True)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    # Derives WebP generes par tache Celery : {"sm": "cle", "md": "cle"}
    derivatives = models.JSONField(default=dict, blank=True)

    position = models.PositiveSmallIntegerField(_("ordre d'affichage"), default=0)

    # Mise en avant sur la page d'accueil du mini-site.
    #
    # L'accueil ne montre qu'un extrait de la galerie. Sans ce drapeau, cet
    # extrait etait « les premieres par ordre d'affichage » : pour mettre une
    # photo en vitrine, il fallait la remonter tout en haut de la galerie, et
    # donc renoncer a l'ordre voulu sur la page des realisations. Les deux
    # decisions sont maintenant independantes.
    featured = models.BooleanField(_("en vedette sur l'accueil"), default=False)

    class Meta:
        verbose_name = _("média")
        verbose_name_plural = _("médias")
        ordering = ("position", "-created_at")
        indexes = [models.Index(fields=["tenant", "kind", "position"])]

    def __str__(self) -> str:
        return self.alt_text or str(self.file)
