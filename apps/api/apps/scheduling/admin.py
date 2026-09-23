from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html

from apps.common.admin import ADMIN_DB, SuppressionTracee, TenantScopedAdmin

from .models import AvailabilityException, Booking, BusinessHours
from .waitlist import WaitlistEntry


@admin.register(BusinessHours)
class BusinessHoursAdmin(TenantScopedAdmin):
    list_display = ("tenant", "staff_member", "weekday", "starts_at", "ends_at")
    list_filter = ("weekday", "tenant")
    search_fields = ("tenant__name", "staff_member__name")
    autocomplete_fields = ("staff_member",)
    ordering = ("tenant__name", "weekday", "starts_at")
    list_select_related = ("tenant", "staff_member")


@admin.register(AvailabilityException)
class AvailabilityExceptionAdmin(TenantScopedAdmin):
    list_display = ("tenant", "staff_member", "kind", "starts_at", "ends_at", "reason")
    list_filter = ("kind", "tenant")
    search_fields = ("tenant__name", "staff_member__name", "reason")
    autocomplete_fields = ("staff_member",)
    date_hierarchy = "starts_at"
    ordering = ("-starts_at",)
    list_select_related = ("tenant", "staff_member")


@admin.register(Booking)
class BookingAdmin(SuppressionTracee, TenantScopedAdmin):
    """Toutes les commandes des salons, en lecture seule.

    -----------------------------------------------------------------------
    Pourquoi la plateforme regarde sans toucher
    -----------------------------------------------------------------------

    Elle en a besoin pour le support : « ma cliente dit avoir reserve et je
    ne vois rien », « pourquoi ce montant ». Repondre demande de voir.

    Modifier, non. Un rendez-vous appartient au salon : il porte son chiffre
    d'affaires, ses acomptes, ses engagements envers une cliente. Une
    correction faite ici passerait sous ses yeux sans trace dans son agenda,
    et ses comptes ne tomberaient plus juste. Le geste correct est toujours
    de lui dire quoi faire, jamais de le faire a sa place.

    La suppression est fermee pour la meme raison, en plus fort : les lignes
    de recette pointent vers ces rendez-vous.
    """

    list_display = (
        "starts_at",
        "tenant",
        "service_name",
        "customer",
        "staff_member",
        "status",
        "total_amount",
        "money_detail",
        "source",
    )
    list_filter = ("status", "source", "tenant")
    search_fields = (
        "service_name",
        "customer__full_name",
        "customer__phone",
        "staff_member__name",
        "tenant__name",
    )
    autocomplete_fields = ("customer", "staff_member", "service")
    date_hierarchy = "starts_at"
    ordering = ("-starts_at",)
    list_select_related = ("tenant", "customer", "staff_member")

    fieldsets = (
        (None, {"fields": ("tenant", "customer", "staff_member", "service")}),
        ("Creneau", {"fields": ("starts_at", "ends_at")}),
        ("Etat", {"fields": ("status", "source", "cancelled_at", "cancellation_reason")}),
        (
            "Montants",
            {
                "fields": (
                    "service_name",
                    "total_amount",
                    "options_amount",
                    "items_amount",
                    "travel_fee_amount",
                    "deposit_amount",
                    "deposit_received",
                    "deposit_paid",
                    "deposit_method",
                )
            },
        ),
        ("Detail vendu", {"fields": ("options_snapshot", "items_snapshot")}),
        ("Lieu", {"fields": ("location_mode", "address", "travel_zone_name")}),
        ("Notes", {"fields": ("customer_note", "internal_note")}),
        ("Dates", {"fields": ("created_at", "updated_at", "reminder_sent_at")}),
    )

    @admin.display(description="detail")
    def money_detail(self, booking) -> str:
        """Ce qui s'ajoute a la prestation, resume en une colonne.

        Sans elle, un total de 690 pour une prestation a 450 obligeait a
        ouvrir la fiche pour comprendre - c'est la question la plus frequente
        du support.
        """
        parts = []
        if booking.options_amount:
            parts.append(f"options {booking.options_amount}")
        if booking.items_amount:
            parts.append(f"boutique {booking.items_amount}")
        if booking.travel_fee_amount:
            parts.append(f"déplacement {booking.travel_fee_amount}")
        return " · ".join(parts) or "—"

    def get_readonly_fields(self, request, obj=None):
        """Tout, sans exception.

        Calcule depuis les fieldsets plutot qu'ecrit a la main : un champ
        ajoute au modele demain apparaitra ici en lecture seule sans que
        personne n'ait a y penser. Une liste figee finirait par laisser
        passer un champ modifiable.
        """
        fields = []
        for _, options in self.fieldsets:
            fields.extend(options["fields"])
        return tuple(fields)

    def has_add_permission(self, request) -> bool:
        # Une reservation naît du parcours public ou de l'agenda du salon.
        # En creer une ici sauterait la verification de creneau, et poserait
        # un rendez-vous sur un autre.
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    # -----------------------------------------------------------------
    # La suppression emporte les ecritures comptables
    # -----------------------------------------------------------------
    #
    # Elle etait fermee parce que les lignes de recette pointent vers le
    # rendez-vous. Le risque etait reel, mais mal traite : `on_delete` vaut
    # SET_NULL, donc supprimer aurait laisse une recette **sans origine** -
    # un montant dans les comptes que plus rien ne justifie.
    #
    # Interdire tout court ne tenait pas non plus : pres de la moitie des
    # rendez-vous portent une ecriture, et l'equipe qui exploite la
    # plateforme doit pouvoir effacer une donnee de test ou repondre a une
    # demande de suppression de compte.
    #
    # On supprime donc les deux ensemble, et on le **dit** : la page de
    # confirmation liste les ecritures et leur total. Django ne les
    # montrerait pas seul - son collecteur affiche les cascades, pas les
    # mises a NULL.

    def ecritures_liees(self, objs):
        from apps.finance.models import Transaction

        return (
            Transaction.all_tenants.using(ADMIN_DB)
            .filter(booking__in=objs)
            .order_by("occurred_on")
        )

    def get_deleted_objects(self, objs, request):
        """Ajoute les ecritures a ce que la confirmation annonce."""
        a_supprimer, comptes, permissions, proteges = super().get_deleted_objects(
            objs, request
        )

        ecritures = list(self.ecritures_liees(objs))
        if ecritures:
            total = sum(ecriture.amount for ecriture in ecritures)
            a_supprimer = list(a_supprimer) + [
                format_html(
                    "<strong>Écritures comptables supprimées avec : "
                    "{} ligne{}, {} {}</strong>",
                    len(ecritures),
                    "s" if len(ecritures) > 1 else "",
                    total,
                    ecritures[0].currency,
                ),
                [str(ecriture) for ecriture in ecritures],
            ]
            comptes["écritures comptables"] = len(ecritures)

        return a_supprimer, comptes, permissions, proteges

    def supprimer_les_ecritures(self, request, objs) -> None:
        ecritures = list(self.ecritures_liees(objs))
        if not ecritures:
            return
        for ecriture in ecritures:
            self.tracer_suppression(request, ecriture)
        type(ecritures[0]).all_tenants.using(ADMIN_DB).filter(
            pk__in=[ecriture.pk for ecriture in ecritures]
        ).delete()

    def delete_model(self, request, obj):
        self.supprimer_les_ecritures(request, [obj])
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        self.supprimer_les_ecritures(request, list(queryset))
        super().delete_queryset(request, queryset)


@admin.register(WaitlistEntry)
class WaitlistEntryAdmin(TenantScopedAdmin):
    """La liste d'attente d'un salon.

    -----------------------------------------------------------------------
    Pourquoi elle merite un ecran
    -----------------------------------------------------------------------

    C'est la seule table du produit ou une cliente a laisse ses coordonnees
    **sans obtenir de rendez-vous**. Quand un salon dit « je n'ai jamais eu
    de demande », c'est ici qu'on regarde — et souvent la reponse est qu'il
    a des inscriptions qu'il n'a jamais ouvertes.

    La colonne « Depuis » porte tout l'interet : une inscription de la
    semaine est une file normale, la meme vieille d'un mois est une cliente
    partie ailleurs, et c'est ce qu'il faut dire au salon.
    """

    list_display = (
        "created_at",
        "tenant",
        "full_name",
        "service",
        "fenetre",
        "status",
        "depuis",
    )
    list_filter = ("status", "tenant")
    search_fields = ("tenant__name", "full_name", "phone", "email", "note")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    list_select_related = ("tenant", "service", "staff_member")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Souhaite")
    def fenetre(self, entry):
        """La fenêtre demandée, et si elle est déjà passée.

        Une inscription dont la période est révolue n'attend plus rien : la
        proposer au salon lui ferait rappeler quelqu'un pour un créneau qui
        n'existe plus.
        """
        fenetre = (
            f"{entry.preferred_from.strftime('%d/%m')} "
            f"→ {entry.preferred_to.strftime('%d/%m')}"
        )
        if entry.preferred_to < timezone.localdate():
            return format_html(
                '<span style="color:var(--bs-ink-muted)">{} — période passée</span>', fenetre
            )
        return fenetre

    @admin.display(description="Depuis", ordering="created_at")
    def depuis(self, entry):
        if entry.status != WaitlistEntry.Status.WAITING:
            return format_html(
                '<span style="color:var(--bs-ink-muted)">{}</span>', entry.get_status_display()
            )

        jours = (timezone.now() - entry.created_at).days
        if jours >= 14:
            return format_html(
                '<span style="color:var(--bs-bad)">{} jours sans réponse</span>', jours
            )
        return f"{jours} j"
