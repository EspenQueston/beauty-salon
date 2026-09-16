from django.apps import AppConfig


class StaffConfig(AppConfig):
    """Section « Prestataires » de l'administration.

    Sans `verbose_name`, Django affiche le nom technique du module — une
    liste de « Accounts / Catalog / Scheduling » qui ne dit rien à l'équipe
    qui l'utilise tous les jours.
    """

    name = "apps.staff"
    verbose_name = "Prestataires"
