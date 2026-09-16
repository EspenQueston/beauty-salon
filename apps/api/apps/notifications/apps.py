from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    """Section « Notifications » de l'administration.

    Sans `verbose_name`, Django affiche le nom technique du module — une
    liste de « Accounts / Catalog / Scheduling » qui ne dit rien à l'équipe
    qui l'utilise tous les jours.
    """

    name = "apps.notifications"
    verbose_name = "Notifications"
