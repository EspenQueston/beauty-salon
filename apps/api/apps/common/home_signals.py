"""Étapes réelles du parcours, agrégées sans identifiant personnel."""

import logging

from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


def record_after_commit(event, using):
    def record():
        try:
            from .home import count_event

            count_event(event, using=using)
        except Exception:
            # Une mesure ne doit jamais empêcher une inscription ou une réservation.
            logger.exception("Mesure du parcours indisponible : %s", event)

    transaction.on_commit(record, using=using)


@receiver(pre_save, sender="tenants.Tenant")
@receiver(pre_save, sender="accounts.User")
def remember_state(sender, instance, using, raw=False, **kwargs):
    if raw or instance._state.adding:
        instance._home_previous = None
        return
    field = "status" if sender._meta.model_name == "tenant" else "email_verified_at"
    instance._home_previous = (
        sender.objects.using(using).filter(pk=instance.pk).values_list(field, flat=True).first()
    )


@receiver(post_save, sender="tenants.Tenant")
def salon_progress(sender, instance, created, using, raw=False, **kwargs):
    if raw:
        return
    if created:
        record_after_commit("signup_completed", using)
    if kwargs.get("update_fields") is not None and "status" not in kwargs["update_fields"]:
        return
    if instance.status == "active" and getattr(instance, "_home_previous", None) != "active":
        record_after_commit("salon_published", using)


@receiver(post_save, sender="accounts.User")
def email_progress(sender, instance, using, raw=False, **kwargs):
    if raw:
        return
    if (
        kwargs.get("update_fields") is not None
        and "email_verified_at" not in kwargs["update_fields"]
    ):
        return
    if (
        instance.email_verified_at
        and not getattr(instance, "_home_previous", None)
        and instance.memberships.filter(role="owner", status="active").exists()
    ):
        record_after_commit("email_verified", using)


@receiver(post_save, sender="scheduling.Booking")
def booking_progress(sender, instance, created, using, raw=False, **kwargs):
    if raw or not created:
        return
    # Un salon qui avait déjà des rendez-vous avant l'ajout des mesures n'est pas nouveau.
    if (
        sender.all_tenants.using(using)
        .filter(tenant_id=instance.tenant_id)
        .exclude(pk=instance.pk)
        .exists()
    ):
        return

    def record():
        try:
            from .home import count_event
            from .models import HomeBookingMilestone

            with transaction.atomic(using=using):
                _, first = HomeBookingMilestone.objects.using(using).get_or_create(
                    tenant_id=instance.tenant_id
                )
                if first:
                    count_event("first_booking", using=using)
        except Exception:
            logger.exception("Mesure du premier rendez-vous indisponible")

    transaction.on_commit(record, using=using)
