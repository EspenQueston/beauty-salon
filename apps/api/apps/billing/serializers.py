from decimal import Decimal

from rest_framework import serializers

from .models import Invoice, Plan, Subscription


class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = (
            "id",
            "code",
            "name",
            "description",
            "max_staff",
            "allows_custom_domain",
            "reference_price",
        )


class InvoiceSerializer(serializers.ModelSerializer):
    is_overdue = serializers.BooleanField(read_only=True)

    class Meta:
        model = Invoice
        fields = (
            "id",
            "number",
            "label",
            "period_start",
            "period_end",
            "amount",
            "currency",
            "status",
            "issued_at",
            "due_at",
            "paid_at",
            "payment_method",
            "is_overdue",
        )


class SubscriptionSerializer(serializers.ModelSerializer):
    plan = PlanSerializer(read_only=True)
    days_left_in_trial = serializers.IntegerField(read_only=True)

    class Meta:
        model = Subscription
        fields = (
            "id",
            "plan",
            "status",
            "price_amount",
            "currency",
            "trial_ends_at",
            "days_left_in_trial",
            "current_period_start",
            "current_period_end",
            "setup_fee_amount",
            "setup_fee_paid",
        )


class DepositSerializer(serializers.Serializer):
    """Encaissement d'un acompte, constate par le salon.

    `amount` est facultatif : a defaut, le montant attendu fait foi. Il
    existe parce qu'une cliente laisse parfois ce qu'elle a sur elle, ou
    arrondit — noter le montant demande a la place du montant recu fausserait
    la caisse du salon des le premier arrondi.
    """

    method = serializers.ChoiceField(
        choices=[
            ("cash", "Espèces"),
            ("mobile_money", "Mobile Money"),
            ("transfer", "Virement"),
            ("other", "Autre"),
        ]
    )
    amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        min_value=Decimal("0.01"),
    )
