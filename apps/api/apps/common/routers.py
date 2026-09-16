"""Routage des connexions.

Tout le trafic metier passe par `default` (role soumis aux politiques RLS).
Les migrations ne s'appliquent que sur l'alias proprietaire des tables, ce
qui evite qu'un `manage.py migrate` distrait cree des tables appartenant au
mauvais role et casse silencieusement les droits.
"""

from django.conf import settings


class TenantDatabaseRouter:
    def db_for_read(self, model, **hints):
        return None  # -> default, sauf .using("admin") explicite

    def db_for_write(self, model, **hints):
        return None

    def allow_relation(self, obj1, obj2, **hints):
        return True

    def allow_migrate(self, db, app_label, **hints):
        return db == settings.MIGRATION_DATABASE_ALIAS
