import uuid

from django.db import IntegrityError
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from . import kkiapay
from .models import KkiapayIntent
from .services import PaiementRefuse
from .views import _ProprietaireSeulement


class PreparationSerializer(serializers.Serializer):
    plan = serializers.CharField(max_length=30)
    country = serializers.CharField(max_length=2)
    currency = serializers.CharField(max_length=3)
    method = serializers.UUIDField()
    montant_attendu = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)


class ConfirmationSerializer(serializers.Serializer):
    intention = serializers.UUIDField()
    transaction_id = serializers.CharField(max_length=100)


class KkiapayView(_ProprietaireSeulement, APIView):
    throttle_scope = "subscription_payment"

    def post(self, request):
        s = PreparationSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            return Response(
                kkiapay.preparer(request.tenant_id, request.user, s.validated_data), status=201
            )
        except PaiementRefuse as exc:
            return Response({"detail": str(exc), "code": exc.code}, status=400)

    def get(self, request):
        try:
            pk = uuid.UUID(request.query_params.get("demande", ""))
        except ValueError:
            return Response({"detail": "Paiement introuvable."}, status=404)
        i = KkiapayIntent.objects.filter(tenant_id=request.tenant_id, demande_id=pk).first()
        if not i:
            return Response({"detail": "Paiement introuvable."}, status=404)
        return Response(kkiapay.presentation(i, i.demande))


class KkiapayConfirmationView(_ProprietaireSeulement, APIView):
    throttle_scope = "subscription_payment"

    def post(self, request):
        s = ConfirmationSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        i = KkiapayIntent.objects.filter(
            tenant_id=request.tenant_id, pk=s.validated_data["intention"]
        ).first()
        if not i:
            return Response({"detail": "Paiement introuvable."}, status=404)
        try:
            return Response(kkiapay.confirmer(i.pk, s.validated_data["transaction_id"]))
        except (PaiementRefuse, IntegrityError) as exc:
            return Response(
                {
                    "detail": str(exc)
                    if isinstance(exc, PaiementRefuse)
                    else "Transaction déjà utilisée.",
                    "code": getattr(exc, "code", "transaction_deja_utilisee"),
                },
                status=409,
            )


class KkiapayWebhookView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "kkiapay_webhook"

    def post(self, request, environnement):
        if environnement not in ("test", "live"):
            return Response(status=404)
        sandbox = environnement == "test"
        if not kkiapay.secret_valide(request.headers.get("x-kkiapay-secret", ""), sandbox):
            return Response(status=403)
        if not isinstance(request.data, dict):
            return Response(status=400)
        # Un échec n'est jamais irréversible : une confirmation ultérieure fiable gagne.
        if request.data.get("event") != "transaction.success":
            return Response({"recu": True})
        try:
            pk = uuid.UUID(str(request.data.get("partnerId", "")))
        except ValueError:
            return Response(status=400)
        i = KkiapayIntent.objects.filter(pk=pk, sandbox=sandbox).first()
        if not i:
            return Response(status=404)
        tx = request.data.get("transactionId")
        if not isinstance(tx, str):
            return Response(status=400)
        try:
            return Response(kkiapay.confirmer(i.pk, tx, charge_signee=request.data))
        except PaiementRefuse as exc:
            # 503 provoque une nouvelle tentative fournisseur si son API est en panne.
            return Response(
                {"code": exc.code}, status=503 if exc.code == "verification_indisponible" else 409
            )
        except IntegrityError:
            return Response({"code": "transaction_deja_utilisee"}, status=409)
