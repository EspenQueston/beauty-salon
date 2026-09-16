"""Les comptes de la plateforme, dans l'administration.

Contrairement aux comptes des salons - que la plateforme heberge sans les
tenir, et qui sont donc en lecture seule - ceux-ci lui appartiennent : elle
les saisit, les corrige et les supprime.

Seules les lignes nees d'une facture reglee resistent : elles sont le reflet
d'un evenement de facturation, et les modifier ici ferait diverger deux
registres qui doivent dire la meme chose.
"""

from django.contrib import admin
from django.db.models import Q, Sum
from django.utils.translation import gettext_lazy as _

from .models import PlatformEntry


@admin.register(PlatformEntry)
class PlatformEntryAdmin(admin.ModelAdmin):
    list_display = (
        "occurred_on",
        "kind",
        "category_label",
        "label",
        "amount",
        "currency",
        "tenant",
        "source",
    )
    list_filter = ("kind", "source", "currency", "occurred_on")
    search_fields = ("label", "note", "tenant__name")
    date_hierarchy = "occurred_on"
    autocomplete_fields = ("tenant",)
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        (None, {"fields": ("kind", "category", "label", "amount", "currency")}),
        (_("Rattachement"), {"fields": ("occurred_on", "tenant", "invoice", "note")}),
        (_("Traçabilité"), {"fields": ("source", "created_at", "updated_at")}),
    )

    @admin.display(description=_("poste"))
    def category_label(self, obj) -> str:
        return obj.category_label

    def get_readonly_fields(self, request, obj=None):
        base = super().get_readonly_fields(request, obj)
        if obj is not None and obj.source == PlatformEntry.Source.SUBSCRIPTION:
            # Ligne miroir d'une facture : la corriger ici ferait diverger le
            # registre de la plateforme et celui du salon.
            return (*base, "kind", "category", "label", "amount", "currency",
                    "occurred_on", "tenant", "invoice", "source")
        return base

    def has_delete_permission(self, request, obj=None) -> bool:
        if obj is not None and obj.source == PlatformEntry.Source.SUBSCRIPTION:
            return False
        return super().has_delete_permission(request, obj)

    def changelist_view(self, request, extra_context=None):
        """Ajoute les totaux en haut de la liste.

        Une liste de mouvements sans son total oblige a exporter pour
        repondre a la seule question qu'on se pose en l'ouvrant : combien.
        Les totaux suivent les filtres appliques, sinon ils mentiraient des
        qu'on restreint a un mois.
        """
        response = super().changelist_view(request, extra_context)

        try:
            queryset = response.context_data["cl"].queryset
        except (AttributeError, KeyError):
            return response

        totals = queryset.aggregate(
            income=Sum("amount", filter=Q(kind=PlatformEntry.Kind.INCOME)),
            expense=Sum("amount", filter=Q(kind=PlatformEntry.Kind.EXPENSE)),
        )
        income = totals["income"] or 0
        expense = totals["expense"] or 0

        response.context_data["ledger_totals"] = {
            "income": income,
            "expense": expense,
            "net": income - expense,
        }
        return response
