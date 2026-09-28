"""Taches planifiees du parrainage."""

from celery import shared_task

from . import services


@shared_task
def evaluer_parrainages() -> dict:
    """Admissibilite des filleuls et expiration des remises. Idempotente."""
    return services.evaluer()
