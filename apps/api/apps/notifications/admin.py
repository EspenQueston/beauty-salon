"""Les notifications vues depuis l'administration plateforme.

---------------------------------------------------------------------------
Ce qu'on peut y faire, et ce qu'on ne peut pas
---------------------------------------------------------------------------

Rien ne se cree a la main. Une notification est la trace d'un evenement :
en fabriquer une depuis l'administration reviendrait a annoncer a un salon
une reservation qui n'existe pas. Les ecrans sont donc en lecture, avec deux
exceptions utiles — marquer lu, et supprimer.

La suppression reste ouverte parce qu'elle sert : une notification de test,
une trace d'un incident resolu. Elle ne detruit aucune donnee metier, juste
son annonce.

---------------------------------------------------------------------------
Pourquoi les appareils abonnes ont leur ecran
---------------------------------------------------------------------------

C'est le seul endroit ou l'on peut repondre a « pourquoi je ne recois
rien ». Trois questions s'y lisent d'un coup : cette personne a-t-elle un
appareil inscrit, depuis quand, et combien d'echecs consecutifs. Sans cet
ecran, la reponse demanderait un shell Django sur la production.
"""

from django.contrib import admin
from django.utils import timezone
from django.utils.translation import ngettext

from apps.common.admin import ADMIN_DB, AdminDatabaseMixin, TenantScopedAdmin

from .models import Notification, PlatformNotification, PushSubscription


class _LectureSeule:
    """Consultable, jamais redigeable."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.action(description="Marquer comme lues")
def marquer_lues(modeladmin, request, queryset):
    maintenant = timezone.now()
    # `updated_at` a la main : `auto_now` ne se declenche pas sur un
    # `update()` en masse.
    touchees = queryset.using(ADMIN_DB).filter(lu_le__isnull=True).update(
        lu_le=maintenant, updated_at=maintenant
    )
    modeladmin.message_user(
        request,
        ngettext(
            "%(n)d notification marquée comme lue.",
            "%(n)d notifications marquées comme lues.",
            touchees,
        )
        % {"n": touchees},
    )


@admin.register(Notification)
class NotificationAdmin(_LectureSeule, TenantScopedAdmin):
    list_display = ("created_at", "tenant", "genre", "titre", "destinataire", "etat")
    list_filter = ("genre", "tenant", ("lu_le", admin.EmptyFieldListFilter))
    search_fields = ("titre", "corps", "recipient__email")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    actions = [marquer_lues]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("recipient")

    @admin.display(description="destinataire", ordering="recipient__email")
    def destinataire(self, obj):
        return obj.recipient.display_name or obj.recipient.email

    @admin.display(description="état", boolean=True, ordering="lu_le")
    def etat(self, obj):
        return obj.lue


@admin.register(PlatformNotification)
class PlatformNotificationAdmin(_LectureSeule, AdminDatabaseMixin, admin.ModelAdmin):
    """La boite de l'equipe, avec le salon concerne quand il y en a un.

    Pas de `TenantScopedAdmin` : cette table n'appartient a aucun salon. Elle
    porte bien un `tenant`, mais c'est une reference — « de quel salon
    parle-t-on » — et non un rattachement.
    """

    list_display = ("created_at", "genre", "titre", "tenant", "destinataire", "etat")
    list_filter = ("genre", ("lu_le", admin.EmptyFieldListFilter))
    search_fields = ("titre", "corps", "recipient__email", "tenant__name")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    actions = [marquer_lues]

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .using(ADMIN_DB)
            .select_related("recipient", "tenant")
        )

    def save_model(self, request, obj, form, change):
        obj.save(using=ADMIN_DB)

    def delete_model(self, request, obj):
        obj.delete(using=ADMIN_DB)

    def delete_queryset(self, request, queryset):
        queryset.using(ADMIN_DB).delete()

    @admin.display(description="destinataire", ordering="recipient__email")
    def destinataire(self, obj):
        return obj.recipient.display_name or obj.recipient.email

    @admin.display(description="état", boolean=True, ordering="lu_le")
    def etat(self, obj):
        return obj.lue


@admin.register(PushSubscription)
class PushSubscriptionAdmin(_LectureSeule, AdminDatabaseMixin, admin.ModelAdmin):
    """Les appareils qui ont accepte d'etre prevenus.

    L'adresse de remise n'est pas affichee en clair dans la liste : c'est
    elle qui permet de deposer une notification chez quelqu'un, et une liste
    d'administration se laisse trainer ouverte sur un ecran.
    """

    list_display = (
        "created_at",
        "compte",
        "appareil",
        "portee",
        "derniere_reussite",
        "echecs",
    )
    list_filter = ("portee",)
    search_fields = ("user__email", "appareil")
    ordering = ("-created_at",)

    def get_queryset(self, request):
        return super().get_queryset(request).using(ADMIN_DB).select_related("user")

    def delete_model(self, request, obj):
        obj.delete(using=ADMIN_DB)

    def delete_queryset(self, request, queryset):
        queryset.using(ADMIN_DB).delete()

    @admin.display(description="compte", ordering="user__email")
    def compte(self, obj):
        return obj.user.display_name or obj.user.email
