"""Facturation vue par le salon.

Lecture seule : un salon consulte son abonnement et ses factures, il ne les
modifie pas. Le document est explicite — aucun role salon n'accede a la
facturation interne de la plateforme, et le reglement se constate cote
plateforme tant qu'aucune passerelle n'est branchee.
"""

from django.shortcuts import get_object_or_404
from rest_framework import mixins, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Membership
from apps.common.permissions import HasTenantRole, IsTenantMember

from .models import Invoice, Subscription
from .serializers import InvoiceSerializer, SubscriptionSerializer

# La facturation regarde le proprietaire, pas l'equipe.
OWNERS = (Membership.Role.OWNER,)


class SubscriptionView(APIView):
    permission_classes = [IsTenantMember, HasTenantRole]
    required_roles = OWNERS
    safe_roles = OWNERS

    def get(self, request):
        subscription = get_object_or_404(
            Subscription.objects.select_related("plan"), tenant_id=request.tenant_id
        )
        return Response(SubscriptionSerializer(subscription).data)


class InvoiceViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = InvoiceSerializer
    permission_classes = [IsTenantMember, HasTenantRole]
    required_roles = OWNERS
    safe_roles = OWNERS
    pagination_class = None

    def get_queryset(self):
        return Invoice.objects.select_related("subscription")
