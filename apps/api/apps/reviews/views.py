"""Avis : lecture publique, ecriture sur jeton, consultation par le salon."""

from django.db.models import Avg, Count
from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Membership
from apps.common.permissions import HasTenantRole, IsTenantMember, IsTenantResolved
from apps.scheduling.models import Booking
from apps.tenants.models import Tenant

from .models import Review
from .serializers import (
    DashboardReviewSerializer,
    PublicReviewSerializer,
    ReviewCreateSerializer,
    ReviewInvitationSerializer,
)
from .services import InvalidReviewToken, is_eligible, read_token

EVERYONE = (
    Membership.Role.OWNER,
    Membership.Role.MANAGER,
    Membership.Role.RECEPTIONIST,
    Membership.Role.STAFF,
)


class PublicReviewListView(APIView):
    """Avis publies d'un salon, avec leur moyenne.

    La moyenne est calculee par la base et non cote client : une page qui
    additionne elle-meme les notes affiche un chiffre different selon la
    pagination.
    """

    permission_classes = [AllowAny, IsTenantResolved]
    throttle_scope = "public_read"

    def get(self, request):
        published = Review.objects.filter(status=Review.Status.PUBLISHED)

        summary = published.aggregate(
            average=Avg("rating"),
            total=Count("id"),
            # Une moyenne par critere, dans la meme requete : c'est ce qui
            # transforme « 3,8 sur 5 » en « votre ponctualite est votre point
            # faible », la seule chose qu'un avis apporte vraiment.
            **{field: Avg(field) for field, _ in Review.CRITERIA},
        )
        reviews = published.select_related("booking").order_by("-created_at")[:30]

        return Response(
            {
                "average": round(summary["average"], 1) if summary["average"] else None,
                "count": summary["total"],
                "criteria": [
                    {
                        "field": field,
                        "label": str(label),
                        "average": round(summary[field], 1),
                    }
                    for field, label in Review.CRITERIA
                    # Un critere que personne n'a note n'a pas de moyenne : le
                    # montrer a zero le ferait passer pour catastrophique.
                    if summary[field] is not None
                ],
                "results": PublicReviewSerializer(reviews, many=True).data,
            }
        )


class ReviewInvitationView(APIView):
    """Verifie un jeton et decrit le rendez-vous a noter."""

    permission_classes = [AllowAny, IsTenantResolved]
    throttle_scope = "public_read"

    def get(self, request):
        booking, error = _booking_from_token(request)
        if error:
            return error

        ok, reason = is_eligible(booking)
        if not ok:
            return Response(
                {"detail": reason, "code": "not_eligible"},
                status=status.HTTP_409_CONFLICT,
            )

        return Response(
            ReviewInvitationSerializer(
                {
                    "salon_name": booking.tenant.name,
                    "service_name": booking.service_name,
                    "staff_member_name": booking.staff_member.name
                    if booking.staff_member
                    else "",
                    "starts_at": booking.starts_at,
                    "customer_name": booking.customer.full_name,
                }
            ).data
        )


class PublicReviewCreateView(APIView):
    permission_classes = [AllowAny, IsTenantResolved]
    throttle_scope = "booking_create"

    def post(self, request):
        payload = ReviewCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        # Champ piege rempli : on repond comme si tout allait bien, sans rien
        # ecrire. Un robot qui recoit une erreur ajuste son formulaire.
        if payload.validated_data.get("website"):
            return Response({"detail": "Merci."}, status=status.HTTP_201_CREATED)

        booking, error = _booking_from_token(request)
        if error:
            return error

        ok, reason = is_eligible(booking)
        if not ok:
            return Response(
                {"detail": reason, "code": "not_eligible"},
                status=status.HTTP_409_CONFLICT,
            )

        review = Review.objects.create(
            tenant_id=request.tenant_id,
            booking=booking,
            customer=booking.customer,
            author_name=booking.customer.full_name,
            # La note d'ensemble est calculee, jamais recue : voir
            # `ReviewCreateSerializer.overall`.
            rating=payload.overall(),
            comment=payload.validated_data.get("comment", "").strip(),
            **{
                field: payload.validated_data.get(field)
                for field, _ in Review.CRITERIA
            },
        )

        from apps.notifications import evenements

        evenements.nouvel_avis(review)

        return Response(
            PublicReviewSerializer(review).data, status=status.HTTP_201_CREATED
        )


class ReviewViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Consultation par le salon. En lecture seule, et c'est voulu.

    Un salon qui pourrait supprimer les avis qui le derangent ne publierait
    que des cinq etoiles, et la note ne vaudrait plus rien. La moderation
    reste a l'equipe plateforme, via l'administration.
    """

    serializer_class = DashboardReviewSerializer
    permission_classes = [IsTenantMember, HasTenantRole]
    required_roles = EVERYONE
    safe_roles = EVERYONE
    pagination_class = None

    def get_queryset(self):
        return Review.objects.select_related(
            "booking", "booking__staff_member"
        ).order_by("-created_at")


def _booking_from_token(request):
    """(booking, None) ou (None, Response d'erreur)."""
    token = request.query_params.get("token") or request.data.get("token", "")
    if not token:
        return None, Response(
            {"detail": "Lien incomplet.", "code": "missing_token"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        booking_id = read_token(token)
    except InvalidReviewToken as exc:
        return None, Response(
            {"detail": str(exc), "code": "invalid_token"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Le jeton designe un rendez-vous, mais la requete arrive sur l'hote d'un
    # salon : le filtre tenant du gestionnaire garantit qu'un jeton d'un
    # salon ne note pas un autre salon.
    booking = (
        Booking.objects.select_related("customer", "staff_member")
        .filter(id=booking_id)
        .first()
    )
    if booking is None:
        return None, Response(
            {"detail": "Ce rendez-vous est introuvable.", "code": "not_found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    booking.tenant = get_object_or_404(Tenant, pk=booking.tenant_id)
    return booking, None
