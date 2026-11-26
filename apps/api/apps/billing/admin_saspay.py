"""Le suivi des paiements SASPAY, et l'etat de la configuration serveur.

Lecture seule : un paiement SASPAY se confirme aupres de l'API, jamais a la
main. La page dit ce qui manque pour ouvrir l'integration — sans jamais
afficher une cle.
"""

from django.conf import settings
from django.contrib import admin
from django.urls import reverse

from apps.common.admin import ADMIN_DB

from . import saspay
from .models import SaspayIntent


@admin.register(SaspayIntent)
class SaspayIntentAdmin(admin.ModelAdmin):
    change_list_template = "admin/billing/saspayintent/change_list.html"
    list_display = ("id", "tenant", "sandbox", "statut", "transaction_id", "expire_le")
    list_filter = ("sandbox", "statut", "tenant")
    search_fields = ("session_id", "transaction_id", "tenant__name", "tenant__slug")
    list_select_related = ("tenant",)

    def changelist_view(self, request, extra_context=None):
        sandbox = settings.SASPAY_SANDBOX
        autorises = sorted(saspay.pays_autorises())
        extra_context = {
            **(extra_context or {}),
            "saspay_enabled": settings.SASPAY_ENABLED,
            "saspay_ready": saspay.disponible() and bool(autorises),
            "saspay_sandbox": sandbox,
            "saspay_countries": [
                {
                    "code": code,
                    "devises": " / ".join(sorted(saspay.devises_acceptees(code))),
                }
                for code in autorises
            ],
            "saspay_credentials": [
                {"nom": "Clé secrète", "presente": bool(saspay.cle(sandbox))},
                {
                    "nom": "Secret de signature des webhooks",
                    "presente": bool(saspay.secret_webhook(sandbox)),
                },
            ],
            "saspay_webhook_path": reverse(
                "saspay-webhook", kwargs={"environnement": "test" if sandbox else "live"}
            ),
            "saspay_method_url": reverse("admin:billing_platformpaymentmethod_changelist")
            + "?kind__exact=saspay"
            if request.user.has_perm("billing.view_platformpaymentmethod")
            else None,
            "saspay_prices_url": reverse("admin:billing_planprice_changelist")
            if request.user.has_perm("billing.view_planprice")
            else None,
        }
        return super().changelist_view(request, extra_context)

    def get_queryset(self, request):
        return super().get_queryset(request).using(ADMIN_DB)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return tuple(f.name for f in self.model._meta.fields)
