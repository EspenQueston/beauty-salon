"""Contexte tenant : le pont entre la requete HTTP et PostgreSQL.

Deux choses sont posees en meme temps par `tenant_context()` :

1. une ContextVar Python, lue par TenantManager pour filtrer les querysets ;
2. la variable de session PostgreSQL `app.tenant_id`, lue par les politiques
   RLS (voir rls.py).

Les deux couches sont redondantes *volontairement*. Si la premiere est
contournee (requete brute, relation inverse, bug de manager), la seconde
tient encore. Si `app.tenant_id` n'est pas positionnee, les politiques ne
laissent passer aucune ligne : le systeme echoue ferme, jamais ouvert.
"""

from contextlib import contextmanager
from contextvars import ContextVar

from django.db import DEFAULT_DB_ALIAS, connections, transaction

# Nom de la variable de session PostgreSQL. Doit correspondre exactement a
# celui utilise dans les politiques generees par rls.py.
TENANT_GUC = "app.tenant_id"

_current_tenant_id: ContextVar[str | None] = ContextVar("current_tenant_id", default=None)


class TenantContextError(RuntimeError):
    """Imbrication de contextes tenant incompatibles."""


def get_current_tenant_id() -> str | None:
    """Tenant du contexte courant, ou None hors contexte."""
    return _current_tenant_id.get()


def require_current_tenant_id() -> str:
    tenant_id = _current_tenant_id.get()
    if tenant_id is None:
        raise TenantContextError(
            "Aucun tenant dans le contexte courant. Enveloppez l'appel dans "
            "tenant_context(tenant_id)."
        )
    return tenant_id


@contextmanager
def tenant_context(tenant_id, using: str = DEFAULT_DB_ALIAS):
    """Fixe le tenant courant pour la duree du bloc.

    `SET LOCAL` n'a de sens que dans une transaction : le bloc en ouvre une.
    Passer `None` vide explicitement le contexte, ce qui rend toutes les
    tables tenant invisibles a cette connexion.
    """
    new_value = None if tenant_id is None else str(tenant_id)
    current = _current_tenant_id.get()

    # SET LOCAL survit jusqu'a la fin de la transaction *externe*. Imbriquer
    # deux tenants differents laisserait donc fuiter le second apres la sortie
    # du bloc interne : on refuse plutot que de produire un bug silencieux.
    if current is not None and new_value is not None and current != new_value:
        raise TenantContextError(
            f"Contexte tenant deja actif ({current}), impossible de basculer "
            f"vers {new_value} sans sortir du bloc courant."
        )

    with transaction.atomic(using=using):
        previous = _read_guc(using)
        _write_guc(using, new_value or "")

        token = _current_tenant_id.set(new_value)
        try:
            yield new_value
        finally:
            _current_tenant_id.reset(token)
            # SET LOCAL vit jusqu'a la fin de la transaction *externe*, pas
            # du bloc atomic imbrique : sans restauration explicite, le
            # tenant resterait pose apres la sortie du bloc. Inutile si la
            # transaction est deja condamnee.
            if not connections[using].needs_rollback:
                _write_guc(using, previous)


def _read_guc(using: str) -> str:
    with connections[using].cursor() as cursor:
        cursor.execute("SELECT current_setting(%s, true)", [TENANT_GUC])
        return cursor.fetchone()[0] or ""


def _write_guc(using: str, value: str) -> None:
    with connections[using].cursor() as cursor:
        cursor.execute("SELECT set_config(%s, %s, true)", [TENANT_GUC, value])


@contextmanager
def bypass_tenant_context():
    """Vide le contexte applicatif sans toucher a la connexion.

    Reserve aux traitements plateforme qui parcourent plusieurs salons et
    travaillent explicitement sur l'alias `admin`.
    """
    token = _current_tenant_id.set(None)
    try:
        yield
    finally:
        _current_tenant_id.reset(token)
