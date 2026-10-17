"""Le contenu des salons, dit dans une autre langue.

---------------------------------------------------------------------------
Pourquoi une table, et non des colonnes `name_en`
---------------------------------------------------------------------------

Une colonne par champ et par langue demande une migration a chaque nouveau
champ traduisible, et une deuxieme serie de colonnes le jour ou une troisieme
langue arrive. Une table de traductions ne demande rien : on inscrit le champ
au registre, et les salons suivants sont couverts sans migration.

C'est aussi la seule forme qui permette de distinguer ce qu'une machine a
traduit de ce qu'un salon a corrige lui-meme. La distinction n'est pas
cosmetique : une correction faite a la main ne doit jamais etre ecrasee au
prochain passage de la traduction automatique.

---------------------------------------------------------------------------
L'empreinte du texte source, et ce qu'elle evite
---------------------------------------------------------------------------

Chaque traduction retient l'empreinte du texte francais dont elle est issue.
Quand le salon reecrit sa prestation, l'empreinte ne correspond plus : la
traduction est perimee, et elle se refait. Sans cela, un salon qui corrige
« Pose de gel » en « Pose de gel semi-permanent » garderait indefiniment
l'ancienne traduction anglaise, sans que rien ne le signale.

C'est aussi ce qui rend le rattrapage idempotent : relancer la traduction sur
tout le catalogue ne refait que ce qui a change.
"""

from __future__ import annotations

import hashlib

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import TenantOwnedModel


def empreinte(texte: str) -> str:
    """L'empreinte d'un texte source.

    SHA-256 et non un simple `hash()` : celui de Python change a chaque
    demarrage du processus, ce qui rendrait toutes les traductions perimees
    au premier redemarrage.
    """
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()


class Origin(models.TextChoices):
    MACHINE = "machine", _("traduction automatique")
    SALON = "salon", _("corrigee par le salon")


class Translation(TenantOwnedModel):
    """Un champ d'un objet, dans une langue donnee."""

    # L'etiquette du modele — « catalog.service » — plutot qu'une cle vers
    # `django_content_type` : pas de jointure a la lecture, et rien qui depende
    # d'identifiants de types dont la valeur varie d'une base a l'autre.
    model = models.CharField(_("modele"), max_length=64)
    object_id = models.UUIDField(_("objet"))
    field = models.CharField(_("champ"), max_length=64)
    language = models.CharField(_("langue"), max_length=5)

    text = models.TextField(_("texte traduit"))
    source_digest = models.CharField(_("empreinte du texte source"), max_length=64)
    origin = models.CharField(
        _("origine"),
        max_length=16,
        choices=Origin.choices,
        default=Origin.MACHINE,
    )

    class Meta:
        verbose_name = _("traduction")
        verbose_name_plural = _("traductions")
        constraints = [
            models.UniqueConstraint(
                fields=("model", "object_id", "field", "language"),
                name="traduction_unique_par_champ_et_langue",
            )
        ]
        indexes = [
            # La lecture d'un mini-site demande toutes les traductions d'un
            # salon dans une langue, en une fois. C'est l'index qui sert a ca.
            models.Index(fields=("tenant", "language"), name="traduction_salon_langue"),
        ]

    def __str__(self) -> str:
        return f"{self.model}.{self.field} [{self.language}]"

    @property
    def perimee_pour(self) -> str:
        """L'empreinte attendue pour que cette traduction reste valable."""
        return self.source_digest
