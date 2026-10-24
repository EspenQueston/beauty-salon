from django.conf import settings
from django.contrib import admin
from django.urls import reverse

from apps.common.admin import ADMIN_DB

from . import kkiapay
from .models import KkiapayIntent


@admin.register(KkiapayIntent)
class KkiapayIntentAdmin(admin.ModelAdmin):
    change_list_template = "admin/billing/kkiapayintent/change_list.html"
    list_display = ("id", "tenant", "sandbox", "statut", "transaction_id", "expire_le")
    list_filter = ("sandbox", "statut", "tenant")
    search_fields = ("transaction_id", "tenant__name", "tenant__slug")
    list_select_related = ("tenant",)

    def changelist_view(self, request, extra_context=None):
        sandbox = settings.KKIAPAY_SANDBOX
        autorises = sorted(kkiapay.PAYS_DOCUMENTES.intersection(settings.KKIAPAY_ALLOWED_COUNTRIES))
        extra_context = {
            **(extra_context or {}),
            "kkiapay_enabled": settings.KKIAPAY_ENABLED,
            "kkiapay_ready": kkiapay.disponible() and bool(autorises),
            "kkiapay_sandbox": sandbox,
            "kkiapay_countries": ", ".join(autorises),
            "kkiapay_credentials": [
                {"nom": nom, "presente": bool(valeur)}
                for nom, valeur in kkiapay.credentials().items()
            ],
            "kkiapay_webhook_path": reverse(
                "kkiapay-webhook",
                kwargs={"environnement": "test" if sandbox else "live"},
            ),
            "kkiapay_method_url": reverse("admin:billing_platformpaymentmethod_changelist")
            + "?kind__exact=kkiapay"
            if request.user.has_perm("billing.view_platformpaymentmethod")
            else None,
            "kkiapay_prices_url": reverse("admin:billing_planprice_changelist")
            + "?currency__exact=XOF"
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
