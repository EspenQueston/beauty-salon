from django.apps import AppConfig


class AccountsConfig(AppConfig):
    """Section « Comptes et accès » de l'administration.

    Sans `verbose_name`, Django affiche le nom technique du module — une
    liste de « Accounts / Catalog / Scheduling » qui ne dit rien à l'équipe
    qui l'utilise tous les jours.
    """

    name = "apps.accounts"
    verbose_name = "Comptes et accès"

    def ready(self):
        # La connexion vaut reauthentification (voir reauth.py).
        from . import reauth, sessions  # noqa: F401
