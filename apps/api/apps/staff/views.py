from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response

from apps.accounts.models import Membership
from apps.common.viewsets import TenantModelViewSet
from apps.scheduling.models import BLOCKING_BOOKING_STATUSES, Booking

from .models import StaffMember
from .serializers import StaffMemberSerializer

MANAGERS = (Membership.Role.OWNER, Membership.Role.MANAGER)
EVERYONE = (*MANAGERS, Membership.Role.RECEPTIONIST, Membership.Role.STAFF)


class StaffMemberViewSet(TenantModelViewSet):
    serializer_class = StaffMemberSerializer
    model = StaffMember
    prefetch_related = ("staff_services__service",)
    required_roles = MANAGERS
    safe_roles = EVERYONE

    def get_queryset(self):
        queryset = super().get_queryset()
        # Les fiches retirees disparaissent du quotidien, mais restent
        # accessibles a qui les demande explicitement - c'est ainsi qu'un
        # rendez-vous d'il y a six mois garde un nom lisible.
        if self.request.query_params.get("archived") != "true":
            queryset = queryset.filter(archived_at__isnull=True)
        return queryset

    def destroy(self, request, *args, **kwargs):
        """Supprime, ou retire de la liste, selon ce que la personne a déjà fait.

        -------------------------------------------------------------------
        Trois cas, et un seul refus
        -------------------------------------------------------------------

        1. **Des rendez-vous a venir** : on refuse, et on dit combien. Les
           effacer libererait des creneaux deja promis a des clientes, qui
           se presenteraient devant une porte.

        2. **Aucun rendez-vous, jamais** : suppression reelle. La fiche a ete
           creee par erreur ou la personne n'a jamais commence.

        3. **Uniquement des rendez-vous passes** : la fiche sort de la liste
           mais la ligne survit. Ses rendez-vous portent son nom, et ses
           prestations sont dans les comptes du salon : l'effacer reecrirait
           l'historique, y compris financier.

        Le cas 3 etait auparavant traite comme le cas 1 - un refus sec, alors
        que la personne etait partie depuis longtemps et n'avait plus rien a
        faire dans la liste.
        """
        staff_member = self.get_object()
        now = timezone.now()

        upcoming = Booking.objects.filter(
            staff_member=staff_member,
            status__in=BLOCKING_BOOKING_STATUSES,
            starts_at__gte=now,
        )
        pending = upcoming.count()

        if pending:
            first = upcoming.order_by("starts_at").first()
            return Response(
                {
                    "detail": (
                        f"{staff_member.name} a {pending} rendez-vous à venir, "
                        f"dont un le {timezone.localtime(first.starts_at):%d/%m à %H:%M}. "
                        "Déplacez-les ou annulez-les d'abord."
                    ),
                    "code": "has_upcoming_bookings",
                    "extra": {"count": pending},
                },
                status=status.HTTP_409_CONFLICT,
            )

        if not Booking.objects.filter(staff_member=staff_member).exists():
            staff_member.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

        staff_member.archived_at = now
        staff_member.active = False
        staff_member.save(update_fields=["archived_at", "active", "updated_at"])

        return Response(
            {
                "detail": (
                    f"{staff_member.name} a été retirée de votre liste. "
                    "Ses anciens rendez-vous gardent son nom."
                ),
                "code": "archived",
            },
            status=status.HTTP_200_OK,
        )
