"""Base des vues du dashboard.

Le filtrage par salon n'est pas ecrit ici : il se produit tout seul, parce
que les managers tenant lisent le contexte pose par le middleware et que
PostgreSQL applique ses politiques. Une vue qui oublierait de filtrer
renverrait donc une liste vide, pas les donnees du voisin.

Piege a connaitre : on ne peut PAS declarer `queryset = Model.objects.all()`
en attribut de classe. Cet attribut est evalue a l'import du module, donc
hors contexte tenant, donc TenantManager renvoie `.none()` - et le queryset
reste vide pour toujours, quelle que soit la requete. D'ou `model` +
reconstruction a chaque appel.
"""

from rest_framework import viewsets

from .permissions import HasTenantRole, IsTenantMember


class TenantModelViewSet(viewsets.ModelViewSet):
    permission_classes = [IsTenantMember, HasTenantRole]

    # Modele gere par la vue. Le queryset est reconstruit a chaque requete.
    model = None
    select_related: tuple[str, ...] = ()
    prefetch_related: tuple[str, ...] = ()

    # Roles autorises a ecrire. `safe_roles` elargit la lecture si besoin.
    required_roles: tuple[str, ...] = ()
    safe_roles: tuple[str, ...] = ()

    def get_queryset(self):
        queryset = self.model.objects.all()
        if self.select_related:
            queryset = queryset.select_related(*self.select_related)
        if self.prefetch_related:
            queryset = queryset.prefetch_related(*self.prefetch_related)
        return queryset

    def perform_create(self, serializer):
        # Le tenant vient du contexte de la requete, jamais du corps envoye
        # par le client : c'est la difference entre une API multi-tenant et
        # une faille.
        serializer.save(tenant_id=self.request.tenant_id)
