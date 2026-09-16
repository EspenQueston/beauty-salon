"""Traitements periodiques de facturation."""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def run_billing_cycle():
    """Fait avancer les abonnements : fin d'essai, emission, impayes.

    Quotidienne et idempotente : la relancer dans la journee ne facture
    jamais deux fois la meme periode.
    """
    from .services import run_billing_cycle as run

    return run()
