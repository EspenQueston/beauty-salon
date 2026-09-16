"""La boutique d'un salon, vue depuis le support plateforme.

---------------------------------------------------------------------------
Ce que le support vient y chercher
---------------------------------------------------------------------------

Deux questions, et elles se posent presque toujours ensemble :

  « Ma cliente ne peut pas acheter de meches au moment de reserver. »
  Cause reelle dans neuf cas sur dix : l'article est en rupture, ou il a ete
  retire de la vente, ou il n'est rattache a aucune fourniture — un article
  que rien ne reclame n'est jamais propose.

  « Pourquoi le tunnel me demande de repondre sur les meches ? »
  Parce qu'une fourniture indispensable existe pour cette prestation. Le
  voir depuis ici evite de faire decrire au salon son propre ecran.

---------------------------------------------------------------------------
Lecture seule
---------------------------------------------------------------------------

Un prix, un stock, une fourniture : ce sont les decisions commerciales du
salon. Les corriger ici les changerait sur son mini-site sans qu'il en soit
averti, et le prix que voit sa cliente ne serait plus celui qu'il a fixe.
On regarde, on explique, on ne touche pas.
"""

from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from apps.common.admin import TenantScopedAdmin, TenantScopedTabularInline

from .models import Product, Requirement, RequirementProduct


class LectureSeule:
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class RequirementProductInline(TenantScopedTabularInline):
    """Les articles proposes pour une fourniture.

    En inline plutot qu'en entree de menu : c'est une table de liaison, elle
    ne veut rien dire seule. « Trois paquets de meches » et « Meches
    kanekalon, 350 CNY » se lisent ensemble ou pas du tout.
    """

    model = RequirementProduct
    extra = 0
    autocomplete_fields = ("product",)
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Product)
class ProductAdmin(LectureSeule, TenantScopedAdmin):
    list_display = ("name", "tenant", "prix", "stock_lisible", "etat", "position")
    list_filter = ("active", "unit", "tenant")
    search_fields = ("tenant__name", "name", "description")
    ordering = ("tenant__name", "position", "name")
    list_select_related = ("tenant", "image")

    @admin.display(description="Prix", ordering="price")
    def prix(self, product):
        return f"{product.price} {product.tenant.currency}"

    @admin.display(description="Stock", ordering="stock")
    def stock_lisible(self, product):
        """Vide et zero ne veulent pas dire la meme chose.

        `None` signifie « je n'en manque jamais » — le salon qui vend du
        shampooing au litre ne tient pas d'inventaire. Zero signifie
        rupture. Afficher le champ brut confondait les deux, et c'est
        exactement la distinction qu'on vient verifier.
        """
        if product.stock is None:
            return mark_safe('<span style="color:var(--bs-ink-muted)">illimité</span>')
        if product.stock == 0:
            return mark_safe('<span style="color:var(--bs-bad)">rupture</span>')
        if product.is_low:
            return format_html(
                '<span style="color:var(--bs-warn)">{} — bientôt épuisé</span>', product.stock
            )
        return product.stock

    @admin.display(description="Proposé", ordering="active")
    def etat(self, product):
        if not product.active:
            return mark_safe('<span style="color:var(--bs-ink-muted)">retiré de la vente</span>')
        if not product.in_stock:
            # Un article en rupture reste affiché sur le mini-site, barré :
            # le faire disparaître laisserait croire que le salon n'en vend
            # pas. Il n'est simplement plus achetable.
            return mark_safe(
                '<span style="color:var(--bs-warn)">affiché, non achetable</span>'
            )
        return mark_safe('<span style="color:var(--bs-ok)">● en vente</span>')


@admin.register(Requirement)
class RequirementAdmin(LectureSeule, TenantScopedAdmin):
    list_display = ("label", "tenant", "service", "exigence", "offres", "position")
    list_filter = ("mandatory", "tenant")
    search_fields = ("tenant__name", "label", "detail", "service__name")
    ordering = ("tenant__name", "position")
    list_select_related = ("tenant", "service")
    autocomplete_fields = ("service",)
    inlines = (RequirementProductInline,)

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("offers")

    @admin.display(description="Exigence", ordering="mandatory")
    def exigence(self, requirement):
        """Indispensable veut dire « la cliente ne peut pas réserver sans
        répondre ». C'est la seule ligne de cet écran qui peut bloquer une
        réservation, donc la seule à mériter une couleur."""
        if requirement.mandatory:
            return mark_safe(
                '<span style="color:var(--bs-warn)">indispensable — bloque la réservation</span>'
            )
        return mark_safe('<span style="color:var(--bs-ink-muted)">facultative</span>')

    @admin.display(description="Articles proposés")
    def offres(self, requirement):
        """Zéro article proposé n'est pas une anomalie : une fourniture vaut
        comme information même sans rien à vendre. Mais c'est souvent la
        réponse au ticket — « on me demande des mèches et on ne m'en propose
        pas »."""
        total = requirement.offers.count()
        if total == 0:
            return mark_safe(
                '<span style="color:var(--bs-ink-muted)">aucun — information seule</span>'
            )
        return total
