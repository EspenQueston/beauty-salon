"""Traduire un objet, et relire ses traductions.

Deux chemins, qui ne se ressemblent pas :

- **A l'ecriture**, rarement, hors de la requete : on demande au modele de
  langue ce qui manque, et on range le resultat.
- **A la lecture**, a chaque affichage de mini-site : une seule requete SQL
  ramene toutes les traductions du salon, et les serialiseurs y puisent.

C'est ce partage qui rend la chose tenable. Traduire a la lecture couterait un
appel reseau par visite et par champ, sur des pages qui doivent s'ouvrir en
deux secondes depuis un telephone d'entree de gamme.
"""

from __future__ import annotations

import logging

from apps.common.db import tenant_context

from .models import Origin, Translation, empreinte
from .registry import champs_de, etiquette
from .traducteur import Demande, Traducteur

logger = logging.getLogger(__name__)

#: Le traducteur en service. Les tests le remplacent par un factice.
_traducteur: Traducteur = Traducteur()


def poser_traducteur(traducteur: Traducteur) -> Traducteur:
    """Remplace le traducteur, et rend l'ancien pour pouvoir le remettre."""
    global _traducteur  # noqa: PLW0603 - un seul point de reglage, volontaire
    ancien = _traducteur
    _traducteur = traducteur
    return ancien


def traducteur() -> Traducteur:
    return _traducteur


def a_traduire(objet, langue: str) -> dict[str, str]:
    """Les champs de cet objet qui manquent, ou dont la source a change.

    Une traduction corrigee par le salon n'y figure jamais : elle est a lui,
    et la machine ne repasse pas dessus.
    """
    champs = champs_de(objet)
    if not champs:
        return {}

    existantes = {
        traduction.field: traduction
        for traduction in Translation.objects.filter(
            model=etiquette(objet), object_id=objet.pk, language=langue
        )
    }

    manquants: dict[str, str] = {}
    for champ in champs:
        source = (getattr(objet, champ, "") or "").strip()
        if not source:
            continue
        deja = existantes.get(champ)
        if deja and (
            deja.origin == Origin.SALON or deja.source_digest == empreinte(source)
        ):
            continue
        manquants[champ] = source
    return manquants


def traduire(objet, langue: str) -> int:
    """Traduit ce qui manque sur cet objet. Rend le nombre de champs ecrits."""
    manquants = a_traduire(objet, langue)
    if not manquants:
        return 0

    obtenus = traducteur().traduire(Demande(cible=langue, textes=manquants))
    if not obtenus:
        return 0

    ecrits = 0
    for champ, texte in obtenus.items():
        source = manquants.get(champ)
        if not source:
            continue
        Translation.objects.update_or_create(
            model=etiquette(objet),
            object_id=objet.pk,
            field=champ,
            language=langue,
            defaults={
                "tenant_id": objet.tenant_id,
                "text": texte,
                "source_digest": empreinte(source),
                "origin": Origin.MACHINE,
            },
        )
        ecrits += 1
    return ecrits


def table_du_salon(tenant_id, langue: str) -> dict[tuple[str, str, str], str]:
    """Toutes les traductions d'un salon, en une requete.

    La cle est `(modele, identifiant, champ)` — l'identifiant en texte, parce
    que c'est sous cette forme qu'un serialiseur le retrouve.
    """
    return {
        (t.model, str(t.object_id), t.field): t.text
        for t in Translation.objects.filter(tenant_id=tenant_id, language=langue)
    }


def traduire_le_salon(tenant, langue: str) -> int:
    """Rattrape tout le contenu d'un salon. Rend le nombre de champs ecrits.

    Sert au rattrapage initial et a la commande de maintenance. Idempotent :
    un deuxieme passage ne refait que ce qui a change depuis le premier.
    """
    from apps.catalog.models import Service, ServiceCategory, ServiceOption
    from apps.salons.models import SalonProfile
    from apps.staff.models import StaffMember
    from apps.store.models import Product, Requirement

    total = 0
    with tenant_context(tenant.id):
        for modele in (
            SalonProfile,
            ServiceCategory,
            Service,
            ServiceOption,
            StaffMember,
            Product,
            Requirement,
        ):
            for objet in modele.objects.all():
                total += traduire(objet, langue)
    return total


def texte(objet, champ: str, langue: str) -> str:
    """Le champ d'un objet dans cette langue, ou son texte source.

    Sert aux e-mails, qui lisent les modeles en direct et non par les
    serialiseurs : sans cela, une cliente anglophone recevait sa confirmation
    en anglais avec la politique de retard du salon en francais au milieu.

    Le repli est le texte source, jamais une chaine vide : mieux vaut la regle
    dans la mauvaise langue que pas de regle.
    """
    source = (getattr(objet, champ, "") or "").strip()
    if not source or langue == "fr":
        return source

    traduction = Translation.objects.filter(
        model=etiquette(objet),
        object_id=objet.pk,
        field=champ,
        language=langue,
    ).first()
    if traduction is None:
        return source

    # Une traduction faite sur un autre texte que celui qu'on affiche est
    # perimee : le salon a reecrit sa politique depuis. On rend le francais,
    # qui est au moins exact.
    if traduction.source_digest != empreinte(source):
        return source
    return traduction.text
