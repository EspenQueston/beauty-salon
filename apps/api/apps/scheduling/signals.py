"""Toutes les routes de changement de statut passent par le même cycle de récompense."""

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import Booking


@receiver(pre_save, sender=Booking)
def retenir_statut(sender, instance, **kwargs):
    if kwargs.get("raw"):
        return
    instance._statut_precedent = (
        sender.objects.select_for_update()
        .filter(pk=instance.pk)
        .values_list("status", flat=True)
        .first()
    )


@receiver(post_save, sender=Booking)
def recompenses(sender, instance, created, raw=False, **kwargs):
    champs = kwargs.get("update_fields")
    if champs is not None and "status" not in champs:
        return
    if raw or created or instance.status == getattr(instance, "_statut_precedent", None):
        return
    from apps.parrainage.clients import transition

    transition(instance, instance._statut_precedent)
