"""La devise d'un salon, pour les lignes qui la figent.

Un rendez-vous et une ecriture comptable portent leur propre devise, celle
dans laquelle ils ont ete passes. Cette fonction repond a « laquelle, pour
ce salon, maintenant » - et rien d'autre. La conversion d'un catalogue, elle,
vit dans `apps.tenants.services.conversion`.

Elle est ici plutot que dans `apps.tenants` pour ne pas faire dependre
l'agenda et la comptabilite du module des salons : la relation existe deja
dans l'autre sens.
"""

from __future__ import annotations

from .db import get_current_tenant_id

# Devise de repli quand aucun salon n'est resolu.
#
# Les cas sont rares - un objet cree hors contexte, dans un test ou une
# commande - et laisser la colonne vide serait pire : une ligne sans
# etiquette suivrait le salon a son prochain changement de devise, ce que
# cette colonne existe precisement pour empecher.
DEFAUT = "XAF"


def devise_du_salon(tenant_id=None) -> str:
    """Code ISO de la devise du salon, ou le repli.

    L'identifiant est resolu comme le fait `TenantOwnedModel.save` : celui
    qu'on passe, sinon celui du contexte courant.
    """
    from apps.tenants.models import Tenant

    tenant_id = tenant_id or get_current_tenant_id()
    if tenant_id is None:
        return DEFAUT

    # `only` : on ne lit qu'une colonne, et cette fonction est appelee a
    # chaque ecriture de rendez-vous ou de mouvement.
    devise = (
        Tenant.objects.filter(pk=tenant_id).values_list("currency", flat=True).first()
    )
    return devise or DEFAUT
