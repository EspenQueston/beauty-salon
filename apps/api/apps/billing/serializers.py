from decimal import Decimal

from django.urls import reverse
from rest_framework import serializers

from apps.media.models import ALLOWED_IMAGE_TYPES, MAX_UPLOAD_BYTES

from .models import (
    Invoice,
    Plan,
    PlatformPaymentMethod,
    Subscription,
    SubscriptionPaymentRequest,
)


class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = (
            "id",
            "code",
            "group",
            "name",
            "description",
            "max_staff",
            "allows_custom_domain",
            "reference_price",
            "billing_months",
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


def acces_en_donnees(acces) -> dict:
    """L'acces calcule, sous la forme que lisent les ecrans."""
    return {
        "ouvert": acces.ouvert,
        "raison": acces.raison,
        "en_grace": acces.en_grace,
        "fin_periode": acces.fin_periode,
        "jusqu_au": acces.jusqu_au,
    }


class SubscriptionSerializer(serializers.ModelSerializer):
    plan = PlanSerializer(read_only=True)
    days_left_in_trial = serializers.IntegerField(read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    acces = serializers.SerializerMethodField()
    demande_en_attente = serializers.SerializerMethodField()
    montee_en_gamme = serializers.SerializerMethodField()
    groupe = serializers.SerializerMethodField()
    fonctions = serializers.SerializerMethodField()
    changement_programme = serializers.SerializerMethodField()

    class Meta:
        model = Subscription
        fields = (
            "id",
            "plan",
            "status",
            "status_label",
            "price_amount",
            "currency",
            "trial_ends_at",
            "days_left_in_trial",
            "current_period_start",
            "current_period_end",
            "setup_fee_amount",
            "setup_fee_paid",
            "acces",
            "demande_en_attente",
            "montee_en_gamme",
            "groupe",
            "fonctions",
            "changement_programme",
        )

    def get_groupe(self, abonnement) -> str | None:
        from .droits import groupe_effectif

        return groupe_effectif(abonnement)

    def get_fonctions(self, abonnement) -> dict:
        from .droits import fonctions_du_salon

        return fonctions_du_salon(abonnement.tenant_id)

    def get_changement_programme(self, abonnement) -> dict | None:
        """La descente programmee, a montrer : quelle offre, de quand a quand."""
        if not abonnement.scheduled_plan_id:
            return None
        return {
            "plan": {
                "code": abonnement.scheduled_plan.code,
                "name": abonnement.scheduled_plan.name,
                "group": abonnement.scheduled_plan.group,
            },
            "debut": abonnement.current_period_end,
            "fin": abonnement.scheduled_period_end,
            "montant": str(abonnement.scheduled_price_amount),
            "devise": abonnement.scheduled_currency,
        }

    def get_montee_en_gamme(self, abonnement) -> dict | None:
        from .services import montee_en_gamme

        return montee_en_gamme(abonnement)

    def get_acces(self, abonnement) -> dict:
        from .services import acces_de

        return acces_en_donnees(acces_de(abonnement))

    def get_demande_en_attente(self, abonnement) -> dict | None:
        demande = (
            abonnement.payment_requests.filter(status=SubscriptionPaymentRequest.Status.PENDING)
            .select_related("plan", "proof")
            .first()
        )
        if demande is None:
            return None
        return PaymentRequestSerializer(demande, context=self.context).data


class MoyenDeReglementSerializer(serializers.ModelSerializer):
    """Un moyen tel que le salon le voit : de quoi payer, rien de plus."""

    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    libelle = serializers.CharField(read_only=True)
    qr_url = serializers.SerializerMethodField()

    class Meta:
        model = PlatformPaymentMethod
        fields = (
            "id",
            "kind",
            "kind_label",
            "libelle",
            "account_number",
            "account_holder",
            "instructions",
            "qr_url",
        )

    def get_qr_url(self, moyen) -> str:
        if moyen.kind not in PlatformPaymentMethod.QR_KINDS or not moyen.qr_image:
            return ""
        chemin = reverse("subscription-method-qr", kwargs={"pk": moyen.pk})
        request = self.context.get("request")
        return request.build_absolute_uri(chemin) if request else chemin


class PaymentRequestSerializer(serializers.ModelSerializer):
    """Une demande de paiement, telle que le salon la relit dans son historique."""

    plan = serializers.SerializerMethodField()
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    method_kind_label = serializers.CharField(source="get_method_kind_display", read_only=True)
    proof_url = serializers.SerializerMethodField()

    class Meta:
        model = SubscriptionPaymentRequest
        fields = (
            "id",
            "created_at",
            "plan",
            "billing_months",
            "country",
            "currency",
            "amount",
            "method_kind",
            "method_kind_label",
            "method_label",
            "method_account_number",
            "method_account_holder",
            "reference",
            "proof_url",
            "status",
            "status_label",
            "rejection_reason",
            "reviewed_at",
            "period_start",
            "period_end",
        )

    def get_plan(self, demande) -> dict:
        return {"code": demande.plan.code, "name": demande.plan.name}

    def get_proof_url(self, demande) -> str:
        if demande.proof_id is None or demande.proof is None:
            return ""
        from apps.media.serializers import media_url

        return media_url(demande.proof, self.context.get("request"))


class PaymentRequestCreateSerializer(serializers.Serializer):
    """Ce que le salon envoie. Le montant n'en fait pas partie : il se calcule."""

    plan = serializers.ChoiceField(
        choices=[
            Plan.Code.MONTHLY,
            Plan.Code.YEARLY,
            Plan.Code.PRO_MONTHLY,
            Plan.Code.PRO_YEARLY,
        ]
    )
    country = serializers.CharField(max_length=2)
    currency = serializers.CharField(max_length=3)
    method = serializers.UUIDField()
    reference = serializers.CharField(max_length=100, trim_whitespace=True)
    proof = serializers.ImageField(required=False, allow_null=True)
    # Le montant que l'ecran affichait. Il ne fixe rien — le serveur calcule
    # toujours le sien — mais s'il differe, le tarif a change entre-temps :
    # le salon a pu verser l'ancien montant, on le lui dit avant d'enregistrer.
    montant_attendu = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True
    )

    def validate_proof(self, fichier):
        if fichier is None:
            return None
        if fichier.size > MAX_UPLOAD_BYTES:
            limite = MAX_UPLOAD_BYTES // (1024 * 1024)
            raise serializers.ValidationError(
                f"La capture dépasse {limite} Mo. Envoyez une image plus légère."
            )
        # `ImageField` a deja ouvert le fichier avec Pillow ; on restreint en
        # plus aux formats qu'un telephone produit pour une capture d'ecran.
        if getattr(fichier, "content_type", "") not in ALLOWED_IMAGE_TYPES:
            raise serializers.ValidationError(
                "Format non accepté : envoyez une capture en JPEG, PNG ou WebP."
            )
        return fichier


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
