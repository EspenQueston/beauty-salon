"""Les paiements a regulariser : encaisses chez le prestataire, non appliques ici.

Le dossier se lit, il ne se modifie pas : seule la decision (« traite » et
sa note) s'y ecrit. L'action elle-meme — prolonger l'abonnement a la main,
rembourser chez le prestataire — se fait ailleurs ; ce dossier dit qu'elle
reste a faire, et pourquoi. Voir billing/regularisation.py.
"""

from django.contrib import admin, messages
from django.utils import timezone

from apps.common.admin import ADMIN_DB

from .models import PaiementARegulariser
from .regularisation import MOTIFS


@admin.register(PaiementARegulariser)
class PaiementARegulariserAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "prestataire",
        "tenant",
        "motif_lisible",
        "montant",
        "devise",
        "transaction_id",
        "statut",
    )
    list_filter = ("statut", "prestataire", "motif")
    search_fields = ("transaction_id", "intention", "tenant__name", "tenant__slug")
    list_select_related = ("tenant",)
    actions = ("marquer_traite",)
    fields = (
        "prestataire",
        "tenant",
        "demande",
        "intention",
        "transaction_id",
        "montant",
        "devise",
        "motif",
        "detail",
        "statut",
        "traite_le",
        "note",
    )

    @admin.display(description="Motif")
    def motif_lisible(self, obj):
        return MOTIFS.get(obj.motif, obj.motif)

    def get_queryset(self, request):
        return super().get_queryset(request).using(ADMIN_DB)

    def get_readonly_fields(self, request, obj=None):
        return tuple(f for f in self.fields if f not in ("statut", "note"))

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        if obj.statut == PaiementARegulariser.Statut.TRAITE and not obj.traite_le:
            obj.traite_le = timezone.now()
        super().save_model(request, obj, form, change)

    @admin.action(description="Marquer comme traité")
    def marquer_traite(self, request, queryset):
        n = queryset.filter(statut=PaiementARegulariser.Statut.A_TRAITER).update(
            statut=PaiementARegulariser.Statut.TRAITE, traite_le=timezone.now()
        )
        self.message_user(request, f"{n} dossier(s) marqué(s) comme traité(s).", messages.SUCCESS)
