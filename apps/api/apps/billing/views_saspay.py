"""Les routes SASPAY : ouvrir un paiement, le confirmer, recevoir les webhooks.

Voir `saspay.py` pour le parcours. Aucune de ces routes ne fait confiance au
navigateur : la confirmation interroge toujours l'API SASPAY.
"""

import json
import uuid

from django.db import IntegrityError
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from . import saspay
from .models import SaspayIntent
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


class SaspayView(_ProprietaireSeulement, APIView):
    throttle_scope = "subscription_payment"

    def post(self, request):
        s = PreparationSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            return Response(
                saspay.preparer(request.tenant_id, request.user, s.validated_data), status=201
            )
        except PaiementRefuse as exc:
            return Response({"detail": str(exc), "code": exc.code}, status=400)

    def get(self, request):
        """Le paiement en cours d'une demande : pour retourner sur la page."""
        try:
            pk = uuid.UUID(request.query_params.get("demande", ""))
        except ValueError:
            return Response({"detail": "Paiement introuvable."}, status=404)
        i = SaspayIntent.objects.filter(tenant_id=request.tenant_id, demande_id=pk).first()
        if not i:
            return Response({"detail": "Paiement introuvable."}, status=404)
        return Response(saspay.presentation(i, i.demande))


class SaspayConfirmationView(_ProprietaireSeulement, APIView):
    throttle_scope = "payment_confirmation"

    def post(self, request):
        s = ConfirmationSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        i = SaspayIntent.objects.filter(
            tenant_id=request.tenant_id, pk=s.validated_data["intention"]
        ).first()
        if not i:
            return Response({"detail": "Paiement introuvable."}, status=404)
        try:
            return Response(saspay.confirmer(i.pk))
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


class SaspayWebhookView(APIView):
    """Le point de reception a declarer dans le tableau de bord SASPAY.

    Un par environnement : `/api/v1/webhooks/saspay/test` et `.../live`.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "saspay_webhook"

    def post(self, request, environnement):
        if environnement not in ("test", "live"):
            return Response(status=404)
        sandbox = environnement == "test"
        # Le corps brut, lu avant tout analyseur : la signature porte sur ces
        # octets-la, pas sur un JSON reconstruit.
        corps = request.body
        if not saspay.signature_valide(
            corps,
            request.headers.get("X-Webhook-Signature", ""),
            request.headers.get("X-Webhook-Timestamp", ""),
            sandbox,
        ):
            return Response(status=403)
        try:
            evenement = json.loads(corps)
        except ValueError:
            return Response(status=400)
        if not isinstance(evenement, dict):
            return Response(status=400)
        # Un echec n'est jamais definitif : une confirmation ulterieure gagne.
        if evenement.get("event") != "transaction.success":
            return Response({"recu": True})
        donnees = evenement.get("data")
        transaction_id = str(donnees.get("id") or "") if isinstance(donnees, dict) else ""
        if not saspay.disponible() or sandbox != saspay.settings.SASPAY_SANDBOX:
            return Response({"recu": True})
        try:
            trouve = saspay.confirmer_en_attente(sandbox, transaction_id)
        except PaiementRefuse:
            # 503 : SASPAY retentera la livraison quand son API repondra.
            return Response({"code": "verification_indisponible"}, status=503)
        except IntegrityError:
            return Response({"code": "transaction_deja_utilisee"}, status=409)
        return Response({"recu": True, "confirme": trouve})
