"""Endpoints publics de reservation.

Ces vues sont les seules de l'API accessibles sans compte. Elles sont donc
les plus exposees : limitation de debit, champ piege, plage de dates bornee
et validation stricte des identifiants recus.
"""

import logging

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.models import Service, ServiceOption
from apps.common.permissions import IsTenantResolved
from apps.customers.models import Customer
from apps.salons.models import ServiceMode, TravelZone
from apps.staff.models import StaffMember, StaffService
from apps.tenants.models import Tenant

from .serializers import (
    AvailabilityQuerySerializer,
    PublicBookingConfirmationSerializer,
    PublicBookingCreateSerializer,
    SlotSerializer,
)
from .services.availability import available_slots
from .services.booking import (
    BookingRefused,
    CustomerDetails,
    create_booking,
    replay_booking,
)

logger = logging.getLogger(__name__)


def _resolve_options(service, ids):
    """Options reellement proposees pour cette prestation, ou None.

    Le tarif et la duree ne viennent jamais de la requete : seuls les
    identifiants circulent, tout le reste est relu en base. Sans cela, il
    suffirait de modifier le corps de la requete pour s'offrir une option
    gratuite - ou pour reserver une pose XL sur un creneau court.

    Le queryset est borne au tenant courant par le manager ; on y ajoute la
    prestation, sinon une option d'une autre prestation du meme salon
    passerait.
    """
    if not ids:
        return []

    unique = list(dict.fromkeys(str(value) for value in ids))
    found = list(
        ServiceOption.objects.filter(id__in=unique, service=service, active=True)
    )
    # Un identifiant inconnu n'est pas ignore en silence : la cliente a vu un
    # prix a l'ecran, il doit correspondre a ce qui est enregistre.
    return found if len(found) == len(unique) else None


def _options_duration(service, ids) -> int:
    options = _resolve_options(service, ids)
    return sum(option.duration_delta_minutes for option in options or [])


def _eligible_staff(service, staff_member_id=None):
    """Prestataires actifs capables de realiser la prestation."""
    staff_ids = StaffService.objects.filter(service=service).values_list(
        "staff_member_id", flat=True
    )
    queryset = StaffMember.objects.filter(id__in=staff_ids, active=True)
    if staff_member_id:
        queryset = queryset.filter(id=staff_member_id)
    return list(queryset.order_by("position", "name"))


class PublicAvailabilityView(APIView):
    permission_classes = [AllowAny, IsTenantResolved]
    throttle_scope = "public_read"

    def get(self, request):
        query = AvailabilityQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        data = query.validated_data

        tenant = get_object_or_404(Tenant, pk=request.tenant_id)
        service = get_object_or_404(Service, pk=data["service"], active=True)
        staff_members = _eligible_staff(service, data.get("staff_member"))

        # Le queryset est borne au tenant courant et a cette prestation :
        # une option devinee, ou empruntee a une autre prestation, ne peut pas
        # rallonger un creneau qu'elle n'accompagne pas.
        extra_minutes = _options_duration(service, data.get("options") or [])

        if not staff_members:
            return Response({"slots": []})

        slots = available_slots(
            tenant=tenant,
            service=service,
            staff_members=staff_members,
            date_from=data["date_from"],
            date_to=data["date_to"],
            extra_minutes=extra_minutes,
        )
        return Response({"slots": SlotSerializer(slots, many=True).data})


class PublicBookingCreateView(APIView):
    permission_classes = [AllowAny, IsTenantResolved]
    throttle_scope = "booking_create"

    def post(self, request):
        payload = PublicBookingCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        if data.get("website"):
            # Robot : on repond 201 sans rien creer, pour ne pas lui apprendre
            # quel champ l'a trahi.
            logger.info("Soumission piegee ignoree (tenant=%s).", request.tenant_id)
            return Response({"detail": "ok"}, status=status.HTTP_201_CREATED)

        tenant = get_object_or_404(Tenant, pk=request.tenant_id)
        if tenant.status != Tenant.Status.ACTIVE:
            return Response(
                {"detail": "Ce salon n'accepte pas de réservation.", "code": "inactive"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Rejeu d'une requete deja traitee (double clic, reseau instable) :
        # on renvoie la reservation d'origine. Ce test vient avant le controle
        # de disponibilite, sinon le creneau apparaitrait pris - par la
        # reservation que cette meme requete avait elle-meme creee.
        idempotency_key = request.headers.get("Idempotency-Key")
        if idempotency_key:
            existing = replay_booking(tenant, idempotency_key)
            if existing is not None:
                return Response(
                    PublicBookingConfirmationSerializer(existing).data,
                    status=status.HTTP_201_CREATED,
                )

        service = get_object_or_404(Service, pk=data["service"], active=True)
        staff_members = _eligible_staff(service, data.get("staff_member"))
        if not staff_members:
            return Response(
                {"detail": "Aucun prestataire ne réalise cette prestation.",
                 "code": "no_staff"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # « Peu importe la personne » : on choisit le premier prestataire
        # reellement libre sur ce creneau, pas simplement le premier de la liste.
        chosen = self._pick_staff(tenant, service, staff_members, data["starts_at"])
        if chosen is None:
            return Response(
                {"detail": "Ce créneau n'est plus disponible.", "code": "slot_unavailable"},
                status=status.HTTP_409_CONFLICT,
            )

        # ----- options retenues ---------------------------------------------
        options = _resolve_options(service, data.get("options") or [])
        if options is None:
            return Response(
                {"detail": "Une des options choisies n'est plus proposée.",
                 "code": "unknown_option"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ----- fournitures : apportees ou achetees ---------------------------
        from apps.store.services import StoreError, missing_mandatory, resolve_items

        try:
            items = resolve_items(service, data.get("items") or [])
        except StoreError as exc:
            return Response(
                {"detail": str(exc), "code": "store_refused"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        unanswered = missing_mandatory(
            service, items, data.get("owned_requirements") or []
        )
        if unanswered:
            # On ne refuse pas de croire la cliente, on refuse le silence :
            # reserver quatre heures sans avoir dit ce qu'on fait des meches
            # finit en rendez-vous annule sur place.
            return Response(
                {
                    "detail": "Indiquez ce que vous apportez : "
                    + ", ".join(item.label for item in unanswered),
                    "code": "requirement_unanswered",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ----- prestation a domicile ---------------------------------------
        zone, error = self._resolve_travel_zone(service, data)
        if error is not None:
            return error

        details = CustomerDetails(
            full_name=data["full_name"],
            phone=data["phone"],
            email=data.get("email", ""),
            contact_preference=data.get(
                "contact_preference", Customer.ContactPreference.WHATSAPP
            ),
            marketing_consent=data.get("marketing_consent", False),
        )

        try:
            booking = create_booking(
                tenant=tenant,
                service=service,
                staff_member=chosen,
                starts_at=data["starts_at"],
                customer=details,
                customer_note=data.get("customer_note", ""),
                options=options,
                items=items,
                travel_zone=zone,
                address=data.get("address", "").strip(),
                idempotency_key=idempotency_key,
            )
        except BookingRefused as exc:
            return Response(
                {"detail": str(exc), "code": "booking_refused"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from apps.notifications.tasks import send_booking_notifications

        send_booking_notifications.delay(str(booking.id), str(tenant.id))

        # Si la cliente est connectee a son espace, le rendez-vous
        # rejoint son historique. Sans ce rattachement il existerait bel et
        # bien, mais resterait invisible dans son compte - et elle croirait
        # que sa reservation n'a pas pris.
        if request.user.is_authenticated and hasattr(request.user, "client_profile"):
            from apps.clients.services import attach

            attach(request.user, request.tenant_id, booking.customer_id)

        return Response(
            PublicBookingConfirmationSerializer(booking).data,
            status=status.HTTP_201_CREATED,
        )

    def _resolve_travel_zone(self, service, data):
        """Valide le deplacement demande, ou explique pourquoi il est refuse.

        Le tarif ne vient jamais de la requete : seul l'identifiant circule,
        le montant est relu en base. Sans cela, il suffirait de modifier le
        corps de la requete pour se faire livrer a domicile au prix d'une
        zone voisine - ou gratuitement.

        Renvoie `(zone, None)` si tout va bien, `(None, Response)` sinon.
        """
        zone_id = data.get("travel_zone")

        if not zone_id:
            # Une prestation exclusivement a domicile n'a de sens qu'avec une
            # zone, des lors que le salon en a defini. Sans ce controle, le
            # rendez-vous partirait sans adresse et sans frais.
            if service.location_mode == ServiceMode.HOME and TravelZone.objects.filter(
                active=True
            ).exists():
                return None, Response(
                    {"detail": "Choisissez la zone de votre domicile.",
                     "code": "travel_zone_required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            return None, None

        if service.location_mode == ServiceMode.SALON:
            return None, Response(
                {"detail": "Cette prestation se fait uniquement au salon.",
                 "code": "travel_not_available"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        zone = TravelZone.objects.filter(pk=zone_id, active=True).first()
        if zone is None:
            # Le queryset est deja borne au tenant courant : une zone d'un
            # autre salon est introuvable ici, pas seulement interdite.
            return None, Response(
                {"detail": "Cette zone n'est pas desservie.",
                 "code": "unknown_travel_zone"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not data.get("address", "").strip():
            return None, Response(
                {"detail": "Indiquez l'adresse où vous souhaitez être reçue.",
                 "code": "address_required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return zone, None

    def _pick_staff(self, tenant, service, staff_members, starts_at):
        from .services.availability import is_slot_available

        for member in staff_members:
            if is_slot_available(
                tenant=tenant, service=service, staff_member=member, starts_at=starts_at
            ):
                return member
        return None


class PublicWaitlistView(APIView):
    """Inscription en liste d'attente depuis le mini-site.

    Ouverte sans compte, comme la reservation : demander une inscription
    pour pouvoir demander un rappel serait une marche de trop pour quelqu'un
    qui vient de constater qu'il n'y a pas de place.
    """

    permission_classes = [AllowAny, IsTenantResolved]
    throttle_scope = "waitlist_create"

    def post(self, request):
        from .models import WaitlistEntry
        from .serializers import PublicWaitlistSerializer

        payload = PublicWaitlistSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        # La prestation est relue en base et doit appartenir au salon
        # courant : le manager tenant s'en charge, on ajoute `active`.
        service = get_object_or_404(Service, pk=data["service"].id, active=True)

        entry = WaitlistEntry.objects.create(
            tenant_id=request.tenant_id,
            service=service,
            staff_member=data.get("staff_member"),
            full_name=data["full_name"].strip(),
            phone=data["phone"].strip(),
            email=data.get("email", "").strip(),
            preferred_from=data["preferred_from"],
            preferred_to=data["preferred_to"],
            note=data.get("note", "").strip(),
        )

        return Response(
            {
                "id": str(entry.id),
                "detail": "Vous êtes inscrite. Le salon vous préviendra si une place se libère.",
            },
            status=status.HTTP_201_CREATED,
        )
