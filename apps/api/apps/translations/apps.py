from django.apps import AppConfig


class TranslationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.translations"
    verbose_name = "traductions"

    def ready(self) -> None:
        # L import branche les recepteurs post_save.
        from . import signals  # noqa: F401
