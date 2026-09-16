"""Recettes et depenses vues depuis l'administration plateforme.

---------------------------------------------------------------------------
Pourquoi c'est en lecture seule
---------------------------------------------------------------------------

Ce sont les comptes d'un commercant : son chiffre d'affaires, ses charges,
sa marge. La plateforme les heberge, elle ne les tient pas.

L'acces existe pour le support - repondre a « mon total de mars est faux »
sans demander une capture d'ecran - et pour rien d'autre. D'ou l'absence
totale d'ecriture : personne chez la plateforme ne doit pouvoir corriger,
ajouter ou supprimer une ligne dans la comptabilite d'un salon. Une
correction se fait par le salon, depuis son propre ecran.

C'est aussi ce qui distingue cette table de `billing` : la facturation de
l'abonnement appartient a la plateforme et s'y modifie ; les comptes du
salon appartiennent au salon et s'y regardent seulement.
"""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from apps.common.admin import TenantScopedAdmin

from .models import Transaction


@admin.register(Transaction)
class TransactionAdmin(TenantScopedAdmin):
    list_display = (
        "occurred_on",
        "tenant",
        "kind",
        "category_label",
        "label",
        "amount",
        "method",
    )
    list_filter = ("kind", "method", "tenant", "occurred_on")
    search_fields = ("label", "counterparty", "tenant__name")
    date_hierarchy = "occurred_on"
    ordering = ("-occurred_on",)

    readonly_fields = (
        "tenant",
        "kind",
        "category",
        "label",
        "amount",
        "occurred_on",
        "method",
        "counterparty",
        "note",
        "booking",
        "created_at",
        "updated_at",
    )

    @admin.display(description=_("poste"))
    def category_label(self, obj) -> str:
        return obj.category_label

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
