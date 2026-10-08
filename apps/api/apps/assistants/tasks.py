"""Les reponses WhatsApp partent en tache : le webhook repond tout de suite."""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def repondre_whatsapp(self, tenant_id: str, jid: str, texte: str):
    from apps.common.db import bypass_tenant_context, tenant_context
    from apps.tenants.models import Tenant

    from . import evolution, whatsapp

    tenant = Tenant.objects.filter(pk=tenant_id).first()
    if tenant is None:
        return "ignore:salon"
    try:
        with bypass_tenant_context(), tenant_context(tenant_id):
            return whatsapp.repondre(tenant, jid, texte)
    except evolution.EvolutionIndisponible as exc:
        logger.warning("Réponse WhatsApp non envoyée pour %s.", tenant_id)
        raise self.retry(exc=exc) from exc
