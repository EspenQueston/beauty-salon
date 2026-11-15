from django.apps import AppConfig


class MediaConfig(AppConfig):
    """Section « Photos et vidéos » de l'administration.

    Sans `verbose_name`, Django affiche le nom technique du module — une
    liste de « Accounts / Catalog / Scheduling » qui ne dit rien à l'équipe
    qui l'utilise tous les jours.
    """

    name = "apps.media"
    verbose_name = "Photos et vidéos"

    def ready(self):
        # Le fichier suit la ligne : sans cet import, le signal n'est jamais
        # branché et « supprimer » laisse la photo sur le disque.
        from . import signals  # noqa: F401
