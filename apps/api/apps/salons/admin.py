from django.contrib import admin
from django.db.models import Count, IntegerField, OuterRef, Subquery
from django.db.models.functions import Coalesce
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from apps.catalog.models import Service
from apps.common.admin import ADMIN_DB, TenantScopedAdmin

from .models import SalonProfile, ServiceMode, TravelZone


@admin.register(SalonProfile)
class SalonProfileAdmin(TenantScopedAdmin):
    list_display = (
        "tenant",
        "city",
        "service_mode",
        "phone",
        "whatsapp_number",
        "wechat",
        "deplacement",
    )
    list_filter = ("service_mode", "tenant")
    search_fields = ("tenant__name", "city", "address", "wechat_id")
    autocomplete_fields = ("logo", "banner", "wechat_qr")
    readonly_fields = ("apercu_wechat",)

    fieldsets = (
        (None, {"fields": ("tenant", "description", "logo", "banner")}),
        ("Coordonnees", {"fields": ("address", "city", "phone", "whatsapp_number",
                                    "social_links")}),
        (
            "WeChat",
            {
                "fields": ("wechat_id", "wechat_qr", "apercu_wechat"),
                "description": (
                    "Comment une cliente ajoute ce salon sur WeChat. Le QR sert "
                    "quand elle lit la page sur un ecran qu'elle peut scanner ; "
                    "l'identifiant sert quand elle la lit <em>dans</em> WeChat, "
                    "ou l'on ne peut pas scanner son propre telephone. Les deux "
                    "sont affiches ensemble sur le mini-site.<br>"
                    "Ce n'est pas un QR de paiement : celui-la vit dans "
                    "&laquo;&nbsp;Moyens de paiement&nbsp;&raquo;."
                ),
            },
        ),
        ("Apparence", {"fields": ("theme_config",)}),
        (
            "Reservation",
            {
                "fields": (
                    "service_mode",
                    "slot_granularity_minutes",
                    "buffer_minutes",
                    "min_lead_time_minutes",
                    "max_advance_days",
                )
            },
        ),
        (
            "Annulation",
            {"fields": ("cancellation_policy", "cancellation_deadline_hours")},
        ),
        (
            "Retard",
            {"fields": ("late_tolerance_minutes", "late_policy")},
        ),
        (
            "Déplacement",
            {"fields": ("service_area", "latitude", "longitude")},
        ),
    )

    @admin.display(description="WeChat", ordering="wechat_id")
    def wechat(self, profile):
        """Ce salon est-il joignable sur WeChat, et par quel bout.

        La question du support est binaire — « la cliente peut-elle nous
        ajouter ? » — mais la reponse a trois etats utiles. Un salon qui n'a
        que le QR est injoignable depuis WeChat lui-meme ; un salon qui n'a
        que l'identifiant est injoignable depuis une affichette. Une colonne
        « oui/non » aurait cache les deux cas qu'on doit corriger.
        """
        identifiant = (profile.wechat_id or "").strip()
        code = profile.wechat_qr_id is not None

        if identifiant and code:
            return format_html("{} + QR", identifiant)
        if identifiant:
            return format_html(
                '{} <span style="color:var(--bs-warn)">(sans QR)</span>', identifiant
            )
        if code:
            return mark_safe('QR seul <span style="color:var(--bs-warn)">(sans '
                             "identifiant)</span>")
        return mark_safe('<span style="color:var(--bs-ink-muted)">—</span>')

    def get_queryset(self, request):
        """Compte les zones et les prestations à domicile en une seule requête.

        Deux raisons, et la première est une correction.

        **`objects` ne voit rien ici.** Les managers des modèles tenant
        filtrent sur le contexte courant ; l'administration plateforme n'en
        ouvre aucun, et un `TravelZone.objects.count()` y renvoie donc
        toujours zéro. La colonne annonçait « aucune zone déclarée » à des
        salons qui en avaient cinq — une colonne qui ment est pire que pas
        de colonne. Les sous-requêtes passent par `all_tenants` sur l'alias
        d'administration, comme tout le reste de cet écran.

        **Et une requête par ligne fait une liste lente.** Compter à
        l'affichage aurait coûté deux requêtes par salon.
        """
        zones = (
            TravelZone.all_tenants.using(ADMIN_DB)
            .filter(tenant_id=OuterRef("tenant_id"), active=True)
            .values("tenant_id")
            .annotate(n=Count("id"))
            .values("n")
        )
        prestations = (
            Service.all_tenants.using(ADMIN_DB)
            .filter(tenant_id=OuterRef("tenant_id"), active=True)
            .exclude(location_mode=ServiceMode.SALON)
            .values("tenant_id")
            .annotate(n=Count("id"))
            .values("n")
        )
        return (
            super()
            .get_queryset(request)
            .annotate(
                nb_zones=Coalesce(Subquery(zones, output_field=IntegerField()), 0),
                nb_a_domicile=Coalesce(
                    Subquery(prestations, output_field=IntegerField()), 0
                ),
            )
        )

    @admin.display(description="Déplacement", ordering="service_mode")
    def deplacement(self, profile):
        """Ce salon peut-il reellement etre reserve a domicile.

        Trois reglages doivent concorder pour qu'une cliente puisse choisir
        « chez moi » : le mode du salon, au moins une zone desservie, et des
        prestations qui ne soient pas toutes cantonnees au salon. Deux sur
        trois donnent un parcours qui n'offre jamais le deplacement, sans
        message d'erreur.

        La colonne dit donc laquelle manque, plutot qu'un « oui/non » qui
        obligerait a ouvrir trois ecrans pour comprendre.
        """
        if profile.service_mode == ServiceMode.SALON:
            return mark_safe('<span style="color:var(--bs-ink-muted)">Au salon</span>')

        # Annotes par `get_queryset` ; la fiche isolee, elle, n'a pas ces
        # attributs et retombe sur un comptage direct.
        zones = getattr(profile, "nb_zones", None)
        if zones is None:
            zones = (
                TravelZone.all_tenants.using(ADMIN_DB)
                .filter(tenant_id=profile.tenant_id, active=True)
                .count()
            )
        if not zones:
            return mark_safe(
                '<span style="color:var(--bs-warn)">aucune zone déclarée</span>'
            )

        ouvertes = getattr(profile, "nb_a_domicile", None)
        if ouvertes is None:
            ouvertes = (
                Service.all_tenants.using(ADMIN_DB)
                .filter(tenant_id=profile.tenant_id, active=True)
                .exclude(location_mode=ServiceMode.SALON)
                .count()
            )
        if not ouvertes:
            return mark_safe(
                '<span style="color:var(--bs-warn)">aucune prestation à '
                "domicile</span>"
            )

        return format_html("{} zone(s) · {} prestation(s)", zones, ouvertes)

    @admin.display(description="Le code")
    def apercu_wechat(self, profile):
        """L'image, en petit.

        Un QR ne se relit pas a l'oeil : ce qu'on verifie ici, c'est qu'il y
        en a un, qu'il est net et qu'il n'a pas ete remplace par une capture
        d'ecran illisible. C'est la question que pose le support, et elle ne
        se tranche pas avec un nom de fichier.

        Il s'affiche sur fond blanc quel que soit le theme : un QR inverse
        n'est plus lisible par la moitie des telephones, et l'admin passe en
        sombre chez qui le demande.
        """
        if profile.wechat_qr_id is None or not profile.wechat_qr.file:
            return mark_safe(
                '<span style="color:var(--bs-ink-muted)">Aucun code televerse. '
                "Le mini-site affiche alors le seul identifiant.</span>"
            )
        return format_html(
            '<img src="{}" alt="" style="width:160px;height:160px;'
            'object-fit:contain;background:#fff;padding:8px;border-radius:8px">',
            profile.wechat_qr.file.url,
        )


@admin.register(TravelZone)
class TravelZoneAdmin(TenantScopedAdmin):
    list_display = ("name", "fee_amount", "active", "position", "tenant")
    list_filter = ("active", "tenant")
    search_fields = ("name", "tenant__name")
    ordering = ("tenant", "position", "name")
