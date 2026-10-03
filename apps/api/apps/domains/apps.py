from django.apps import AppConfig


class DomainsConfig(AppConfig):
    name = "apps.domains"
    verbose_name = "Adresses des mini-sites"

    def ready(self):
        from django.db.models.signals import post_delete, post_save

        from .models import Domain
        from .services import invalidate_hostname

        def _invalidate(sender, instance, **kwargs):
            invalidate_hostname(instance.hostname)

        # Sans cela, renommer ou desactiver un domaine resterait sans effet
        # pendant la duree du cache.
        post_save.connect(_invalidate, sender=Domain, dispatch_uid="domains.invalidate_save")
        post_delete.connect(_invalidate, sender=Domain, dispatch_uid="domains.invalidate_delete")
