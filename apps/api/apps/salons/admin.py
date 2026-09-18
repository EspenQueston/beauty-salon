from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from apps.catalog.models import Service
from apps.common.admin import TenantScopedAdmin

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

        zones = TravelZone.objects.filter(
            tenant_id=profile.tenant_id, active=True
        ).count()
        if not zones:
            return mark_safe(
                '<span style="color:var(--bs-warn)">aucune zone déclarée</span>'
            )

        ouvertes = (
            Service.objects.filter(tenant_id=profile.tenant_id, active=True)
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
