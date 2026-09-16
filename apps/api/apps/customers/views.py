from django.db import models
from django.db.models import Count, Max, Q
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.models import Membership
from apps.audit.models import AuditLog
from apps.common.viewsets import TenantModelViewSet
from apps.scheduling.models import Booking

from .models import Customer
from .serializers import CustomerBookingSerializer, CustomerSerializer

HONOURED = Booking.Status.COMPLETED
MISSED = Booking.Status.NO_SHOW
CALLED_OFF = Booking.Status.CANCELLED

# Deux rendez-vous honores suffisent a distinguer une habituee d'un passage.
RECURRING_FROM = 2

# Un historique se consulte, il ne se depouille pas : au-dela, on cherche
# autrement.
HISTORY_LIMIT = 50

MANAGERS = (Membership.Role.OWNER, Membership.Role.MANAGER)
EVERYONE = (*MANAGERS, Membership.Role.RECEPTIONIST, Membership.Role.STAFF)


class CustomerViewSet(TenantModelViewSet):
    serializer_class = CustomerSerializer
    model = Customer
    required_roles = (*MANAGERS, Membership.Role.RECEPTIONIST)
    safe_roles = EVERYONE

    def get_queryset(self):
        # Les compteurs sont annotes par la base plutot que comptes par le
        # serializer : une liste de cent clientes declenchait sinon quatre
        # cents requetes, une par cliente et par compteur.
        queryset = super().get_queryset().annotate(
            visits=Count("bookings", filter=Q(bookings__status=HONOURED)),
            no_shows=Count("bookings", filter=Q(bookings__status=MISSED)),
            cancellations=Count("bookings", filter=Q(bookings__status=CALLED_OFF)),
            bookings_total=Count("bookings"),
            last_booking=Max("bookings__starts_at"),
        )

        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                Q(full_name__icontains=search) | Q(phone__icontains=search)
            )

        # Les clientes qui reviennent : celles qui ont deja honore au moins
        # deux rendez-vous. C'est la liste qu'on sort pour une relance, et
        # celle qu'on ne veut surtout pas melanger avec les nouvelles.
        if self.request.query_params.get("recurring") == "true":
            queryset = queryset.filter(visits__gte=RECURRING_FROM)

        # Un ordre explicite dans tous les cas : `annotate()` efface celui du
        # modele, et paginer une liste non ordonnee renvoie des lignes
        # differentes d'une page a l'autre - la meme cliente vue deux fois,
        # une autre jamais.
        ordering = self.request.query_params.get("ordering")
        if ordering == "visits":
            return queryset.order_by("-visits", "full_name", "id")
        if ordering == "recent":
            return queryset.order_by(
                models.F("last_booking").desc(nulls_last=True), "id"
            )
        return queryset.order_by("full_name", "id")

    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        """Rendez-vous d'une cliente, du plus recent au plus ancien.

        Route separee plutot que champ imbrique : la liste des clientes n'a
        pas besoin de l'historique complet de chacune, et l'y inclure
        multiplierait par vingt le poids d'un ecran qu'on ouvre a chaque
        appel telephonique.
        """
        customer = self.get_object()
        bookings = (
            customer.bookings.select_related("staff_member")
            .order_by("-starts_at")[:HISTORY_LIMIT]
        )
        return Response(CustomerBookingSerializer(bookings, many=True).data)

    @action(detail=True, methods=["get"])
    def notes(self, request, pk=None):
        """Consultation tracee des notes sensibles.

        L'acces est deja restreint par le serializer ; l'ecriture d'un
        evenement d'audit permet en plus de savoir *qui* a lu quoi, ce qui
        est la seule protection reelle contre une curiosite interne.
        """
        # `safe_roles` ouvre la lecture des fiches a toute l'equipe ; les
        # notes sensibles restent, elles, reservees a la direction.
        if request.membership.role not in MANAGERS:
            return Response(
                {"detail": "Notes réservées au propriétaire et au gérant.",
                 "code": "forbidden"},
                status=403,
            )

        customer = self.get_object()
        AuditLog.objects.create(
            tenant_id=request.tenant_id,
            actor_user=request.user,
            action=AuditLog.Action.CUSTOMER_NOTES_VIEWED,
            resource_type="customer",
            resource_id=str(customer.id),
        )
        return Response({"private_notes": customer.private_notes})
