from django.contrib import admin, messages

from apps.common.admin import ADMIN_DB, TenantScopedAdmin

from .models import Invoice, Plan, Subscription
from .services import BillingError, issue_invoice, mark_invoice_paid


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "reference_price", "max_staff", "active")
    list_filter = ("active",)
    search_fields = ("name", "code")
    ordering = ("position",)


@admin.register(Subscription)
class SubscriptionAdmin(TenantScopedAdmin):
    list_display = (
        "tenant",
        "plan",
        "status",
        "price_amount",
        "currency",
        "current_period_end",
    )
    list_filter = ("status", "plan", "currency")
    search_fields = ("tenant__name", "tenant__slug")
    autocomplete_fields = ("plan",)
    actions = ("action_issue_invoice",)

    @admin.action(description="Émettre la facture de la période en cours")
    def action_issue_invoice(self, request, queryset):
        emises = []
        for subscription in queryset:
            if subscription.price_amount <= 0:
                continue
            emises.append(issue_invoice(subscription).number)

        if emises:
            self.message_user(
                request, "Factures émises : " + ", ".join(emises), messages.SUCCESS
            )
        else:
            self.message_user(
                request,
                "Aucune facture : ces abonnements sont à 0.",
                messages.WARNING,
            )


@admin.register(Invoice)
class InvoiceAdmin(TenantScopedAdmin):
    list_display = (
        "number",
        "tenant",
        "amount",
        "currency",
        "status",
        "issued_at",
        "due_at",
        "paid_at",
    )
    list_filter = ("status", "currency", "payment_method")
    search_fields = ("number", "tenant__name", "payment_reference")
    autocomplete_fields = ("subscription",)
    date_hierarchy = "issued_at"
    # Le numero est attribue a l'emission et ne se recycle pas.
    readonly_fields = ("number",)
    actions = ("action_mark_paid",)

    @admin.action(description="Marquer comme réglée (espèces)")
    def action_mark_paid(self, request, queryset):
        reglees = 0
        for invoice in queryset:
            try:
                mark_invoice_paid(invoice, method=Invoice.Method.CASH)
                reglees += 1
            except BillingError:
                continue
        self.message_user(request, f"{reglees} facture(s) réglée(s).", messages.SUCCESS)

    def get_queryset(self, request):
        return Invoice.all_tenants.using(ADMIN_DB).select_related(
            "tenant", "subscription"
        )
