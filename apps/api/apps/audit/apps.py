from django.apps import AppConfig


class AuditConfig(AppConfig):
    """Section « Journal d'audit » de l'administration.

    Sans `verbose_name`, Django affiche le nom technique du module — une
    liste de « Accounts / Catalog / Scheduling » qui ne dit rien à l'équipe
    qui l'utilise tous les jours.
    """

    name = "apps.audit"
    verbose_name = "Journal d'audit"
