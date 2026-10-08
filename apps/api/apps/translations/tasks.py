"""Les traductions se font hors de la requete.

Un appel a un modele de langue prend une a trois secondes. Le faire pendant
l'enregistrement d'une prestation ferait attendre la gerante du salon devant un
bouton, pour un texte qu'elle ne lira pas — elle ecrit en francais.

`max_retries` : une panne reseau ne doit pas laisser un champ sans traduction
pour toujours. Au-dela des reessais, le rattrapage periodique reprend ce qui
manque — c'est ce qui rend l'ensemble auto-reparateur.
"""

from __future__ import annotations

import logging

from celery import shared_task

from apps.common.db import tenant_context

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def traduire_objet(
    self,
    etiquette_modele: str,
    identifiant: str,
    tenant_id: str,
    langue: str,
) -> int:
    """Traduit un objet designe par son etiquette de modele et son identifiant.

    L'objet est passe par reference et non serialise : entre la mise en file et
    l'execution, le salon a pu le corriger, et c'est la derniere version qu'il
    faut traduire.
    """
    from django.apps import apps as registre_django

    from .services import traduire

    try:
        modele = registre_django.get_model(etiquette_modele)
    except LookupError:
        modele = None
    if modele is None:
        logger.warning("modele inconnu pour la traduction : %s", etiquette_modele)
        return 0

    with tenant_context(tenant_id):
        objet = modele.objects.filter(pk=identifiant).first()
        if objet is None:
            # Supprime entre-temps : il n'y a plus rien a traduire, et ce n'est
            # pas une erreur.
            return 0
        return traduire(objet, langue)


@shared_task
def traduire_tous_les_salons(langue: str = "en") -> int:
    """Rattrapage periodique : tout ce qui manque, dans tous les salons."""
    from apps.tenants.models import Tenant

    from .services import traduire_le_salon

    total = 0
    for tenant in Tenant.objects.all():
        try:
            total += traduire_le_salon(tenant, langue)
        except Exception:  # noqa: BLE001 - un salon en echec n'arrete pas les autres
            logger.exception("rattrapage de traduction impossible pour %s", tenant.id)
    return total
