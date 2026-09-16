"""Permissions DRF.

Le middleware a deja resolu le tenant et le membership ; ces classes ne font
que verifier le resultat. Elles restent neanmoins explicites sur chaque vue
sensible : une vue sans permission declaree ne doit jamais exister.
"""

from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsTenantResolved(BasePermission):
    """Un salon a pu etre determine pour cette requete."""

    message = "Aucun salon n'a pu être déterminé pour cette requête."

    def has_permission(self, request, view):
        return getattr(request, "tenant_id", None) is not None


class IsTenantMember(BasePermission):
    """L'utilisateur appartient au salon courant."""

    message = "Vous n'appartenez pas à ce salon."

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and getattr(request, "tenant_id", None) is not None
            and getattr(request, "membership", None) is not None
        )


class HasTenantRole(BasePermission):
    """Restreint une vue a certains roles.

    Usage sur la vue :
        permission_classes = [IsTenantMember, HasTenantRole]
        required_roles = ("owner", "manager")

    Un `safe_roles` optionnel autorise un ensemble plus large en lecture.
    """

    message = "Votre rôle ne permet pas cette action."

    def has_permission(self, request, view):
        membership = getattr(request, "membership", None)
        if membership is None:
            return False

        if request.method in SAFE_METHODS:
            roles = getattr(view, "safe_roles", None) or getattr(view, "required_roles", ())
        else:
            roles = getattr(view, "required_roles", ())

        return not roles or membership.role in roles


class IsPlatformAdmin(BasePermission):
    message = "Réservé aux administrateurs de la plateforme."

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_platform_admin
