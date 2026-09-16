"""Agenda et gestion des rendez-vous cote salon."""

from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Membership
from apps.audit.models import AuditLog
from apps.billing.serializers import DepositSerializer
from apps.common.exceptions import SlotUnavailable
from apps.common.permissions import IsTenantResolved
from apps.common.viewsets import TenantModelViewSet
from apps.customers.models import Customer
from apps.payments.views import DepositReviewSerializer
from apps.tenants.models import Tenant

from . import overview
from .models import AvailabilityException, Booking, BusinessHours, WaitlistEntry
from .serializers import (
    AvailabilityExceptionSerializer,
    BookingSerializer,
    BusinessHoursSerializer,
    StaffBookingCreateSerializer,
    WaitlistEntrySerializer,
)
from .services.booking import BookingRefused, cancel_booking, reschedule_booking

MANAGERS = (Membership.Role.OWNER, Membership.Role.MANAGER)
FRONT_DESK = (*MANAGERS, Membership.Role.RECEPTIONIST)
EVERYONE = (*FRONT_DESK, Membership.Role.STAFF)


class BusinessHoursViewSet(TenantModelViewSet):
    serializer_class = BusinessHoursSerializer
    model = BusinessHours
    select_related = ("staff_member",)
    required_roles = MANAGERS
    safe_roles = EVERYONE
    pagination_class = None  # une grille hebdomadaire tient en une reponse


class AvailabilityExceptionViewSet(TenantModelViewSet):
    serializer_class = AvailabilityExceptionSerializer
    model = AvailabilityException
    select_related = ("staff_member",)
    required_roles = FRONT_DESK
    safe_roles = EVERYONE

    def get_queryset(self):
        queryset = super().get_queryset()
        starts_after = self.request.query_params.get("from")
        if starts_after:
            queryset = queryset.filter(ends_at__gte=parse_datetime(starts_after))
        return queryset


class BookingViewSet(TenantModelViewSet):
    """Agenda du salon.

    La creation manuelle passe par une route dediee (`POST .../manual`) plutot
    que par le POST standard : la reception a le droit de forcer un rendez-vous
    hors grille, ce qui n'est pas le cas du parcours public.
    """

    serializer_class = BookingSerializer
    model = Booking
    select_related = ("customer", "staff_member", "service")
    required_roles = FRONT_DESK
    safe_roles = EVERYONE

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params

        starts_from = params.get("from")
        starts_to = params.get("to")
        if starts_from:
            queryset = queryset.filter(starts_at__gte=parse_datetime(starts_from))
        if starts_to:
            queryset = queryset.filter(starts_at__lt=parse_datetime(starts_to))

        if staff_member := params.get("staff_member"):
            queryset = queryset.filter(staff_member_id=staff_member)
        if statuses := params.get("status"):
            queryset = queryset.filter(status__in=statuses.split(","))

        # Recherche libre : nom, telephone, prestation.
        #
        # Elle ignore volontairement la periode affichee. Chercher « Chantal »
        # et ne rien trouver parce qu'elle vient le mois prochain serait le
        # contraire d'une recherche - c'est l'appelant qui cesse d'envoyer
        # `from` et `to` quand il cherche.
        #
        # Le telephone est compare tel qu'il est stocke : on cherche par les
        # derniers chiffres, qui sont ce dont on se souvient.
        if search := params.get("search", "").strip():
            from django.db.models import Q

            queryset = queryset.filter(
                Q(customer__full_name__icontains=search)
                | Q(customer__phone__icontains=search)
                | Q(service_name__icontains=search)
            )

        # Un prestataire ne voit que son propre agenda, sauf s'il gere le salon.
        membership = self.request.membership
        if membership.role == Membership.Role.STAFF:
            queryset = queryset.filter(staff_member__membership=membership)

        return queryset.order_by("starts_at")

    @action(detail=False, methods=["post"], url_path="manual")
    def manual(self, request):
        payload = StaffBookingCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        customer = data.get("customer")
        if customer is None:
            customer, _ = Customer.objects.get_or_create(
                tenant_id=request.tenant_id,
                phone=data["phone"].strip(),
                defaults={"full_name": data["full_name"].strip()},
            )

        service = data["service"]
        starts_at = data["starts_at"]

        # L'acompte d'une saisie manuelle suit la meme regle que celui d'une
        # reservation en ligne. Il lisait auparavant le montant porte par la
        # prestation - un champ qui n'existe plus, et qui de toute facon ne
        # disait pas ce que la cliente payait.
        from apps.salons.models import SalonProfile

        from .services.deposit import compute_for

        tenant = Tenant.objects.get(pk=request.tenant_id)
        profile = SalonProfile.objects.filter(tenant_id=request.tenant_id).first()
        deposit_due = compute_for(
            service,
            profile,
            options_amount=Decimal("0"),
            items_amount=Decimal("0"),
            travel_amount=Decimal("0"),
            currency=tenant.currency,
        )

        booking = Booking(
            tenant_id=request.tenant_id,
            customer=customer,
            staff_member=data["staff_member"],
            service=service,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=service.duration_minutes),
            status=Booking.Status.CONFIRMED,
            source=Booking.Source.STAFF,
            service_name=service.name,
            total_amount=service.price_amount,
            deposit_amount=deposit_due,
            location_mode=service.location_mode,
            internal_note=data.get("internal_note", ""),
        )

        from django.db import IntegrityError, transaction

        try:
            with transaction.atomic():
                booking.save()
        except IntegrityError:
            # Meme forcee, une saisie manuelle ne peut pas superposer deux
            # rendez-vous chez la meme personne.
            return Response(
                {"detail": "Ce prestataire a déjà un rendez-vous sur ce créneau.",
                 "code": "slot_unavailable"},
                status=status.HTTP_409_CONFLICT,
            )

        AuditLog.objects.create(
            tenant_id=request.tenant_id,
            actor_user=request.user,
            action=AuditLog.Action.BOOKING_CREATED,
            resource_type="booking",
            resource_id=str(booking.id),
            metadata={"source": "staff"},
        )
        return Response(
            BookingSerializer(booking).data, status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        booking = self.get_object()
        try:
            cancel_booking(
                booking=booking,
                reason=request.data.get("reason", ""),
                actor=request.user,
            )
        except BookingRefused as exc:
            return Response(
                {"detail": str(exc), "code": "booking_refused"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(BookingSerializer(booking).data)

    @action(detail=True, methods=["post"])
    def reschedule(self, request, pk=None):
        booking = self.get_object()
        starts_at = parse_datetime(request.data.get("starts_at", ""))
        if starts_at is None:
            return Response(
                {"detail": "Date invalide.", "code": "invalid_datetime"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            reschedule_booking(booking=booking, starts_at=starts_at, actor=request.user)
        except SlotUnavailable as exc:
            return Response(
                {"detail": str(exc.detail), "code": "slot_unavailable",
                 "extra": exc.extra},
                status=status.HTTP_409_CONFLICT,
            )
        except BookingRefused as exc:
            # `cancel` attrapait deja ce refus, pas `reschedule` : depuis que
            # le service refuse de deplacer un rendez-vous clos, l'oubli
            # transformait un refus metier en erreur 500.
            return Response(
                {"detail": str(exc), "code": "booking_refused"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(BookingSerializer(booking).data)

    @action(detail=True, methods=["post"], url_path="status")
    def change_status(self, request, pk=None):
        """Arrivee, prestation terminee, absence."""
        booking = self.get_object()
        new_status = request.data.get("status")

        allowed = {
            Booking.Status.CONFIRMED,
            Booking.Status.CHECKED_IN,
            Booking.Status.COMPLETED,
            Booking.Status.NO_SHOW,
        }
        if new_status not in allowed:
            return Response(
                {"detail": "Statut non autorisé par cette route.",
                 "code": "invalid_status"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        previous = booking.status
        booking.status = new_status
        booking.save(update_fields=["status", "updated_at"])

        # Une prestation honoree produit sa recette toute seule.
        #
        # Sans cela, le salon devrait ressaisir a la main ce que le logiciel
        # sait deja - et un cahier de comptes qu'on remplit deux fois n'est
        # jamais rempli. L'operation est idempotente : repasser par
        # « terminee » apres une correction ne double pas la recette.
        if new_status == Booking.Status.COMPLETED:
            from apps.finance.services import record_booking_income

            record_booking_income(booking)

            # Et la demande d'avis part dans la foulee.
            #
            # Elle etait auparavant accrochee a l'heure de fin *prevue*, avec
            # quatre heures de politesse : une prestation qui debordait
            # recevait sa demande avant d'etre finie, et une prestation
            # marquee terminee le lendemain n'en recevait aucune. En marquant
            # « Terminée », le salon affirme que c'est fini - il n'y a plus
            # rien a deviner.
            #
            # `previous != COMPLETED` : repasser par « terminee » apres une
            # correction ne doit pas relancer l'envoi. La tache le verifie
            # aussi de son cote, via `review_invited_at`.
            if previous != Booking.Status.COMPLETED:
                from apps.notifications.tasks import send_review_request

                send_review_request.delay(str(booking.id), str(request.tenant_id))

        AuditLog.objects.create(
            tenant_id=request.tenant_id,
            actor_user=request.user,
            action=AuditLog.Action.BOOKING_STATUS_CHANGED,
            resource_type="booking",
            resource_id=str(booking.id),
            metadata={"from": previous, "to": new_status},
        )
        return Response(BookingSerializer(booking).data)

    @action(detail=True, methods=["post"])
    def deposit(self, request, pk=None):
        """Constate un acompte recu.

        Aucune passerelle n'est branchee : le salon encaisse comme il le fait
        deja - especes, Mobile Money, virement - et le note ici. C'est
        l'etape 1 prevue par le document, et elle suffit a rendre le suivi
        des acomptes utilisable des maintenant.
        """
        booking = self.get_object()

        if booking.deposit_amount <= 0:
            return Response(
                {"detail": "Cette prestation ne demande pas d'acompte.",
                 "code": "no_deposit"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if booking.deposit_paid:
            return Response(
                {"detail": "Cet acompte est déjà encaissé.", "code": "already_paid"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        payload = DepositSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        booking.deposit_paid = True
        booking.deposit_paid_at = timezone.now()
        booking.deposit_method = payload.validated_data["method"]
        # A defaut de montant precise, le montant attendu fait foi.
        booking.deposit_received = payload.validated_data.get(
            "amount", booking.deposit_amount
        )
        booking.save(
            update_fields=[
                "deposit_paid",
                "deposit_paid_at",
                "deposit_method",
                "deposit_received",
                "updated_at",
            ]
        )

        # L'acompte entre en caisse le jour ou il est verse, pas le jour de
        # la prestation : un salon qui encaisse en mars pour une pose en mai
        # doit voir la recette en mars, sinon sa tresorerie du mois est
        # fausse.
        from apps.finance.services import record_deposit_income

        record_deposit_income(booking)

        AuditLog.objects.create(
            tenant_id=request.tenant_id,
            actor_user=request.user,
            action=AuditLog.Action.BOOKING_STATUS_CHANGED,
            resource_type="booking",
            resource_id=str(booking.id),
            metadata={
                "deposit_expected": str(booking.deposit_amount),
                "deposit_received": str(booking.deposit_received),
                "method": booking.deposit_method,
            },
        )
        return Response(BookingSerializer(booking).data)

    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        """Accepte le rendez-vous : acompte recu **et** prestation assurable.

        Les deux en un geste, volontairement. Les separer aurait permis
        d'encaisser pour un creneau qu'on ne peut pas tenir - la pire issue
        pour la cliente, qui a paye et n'aura rien.
        """
        from apps.payments.services import PaymentRefused, accept

        booking = self.get_object()
        payload = DepositReviewSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        try:
            accept(
                booking=booking,
                actor=request.user,
                amount=payload.validated_data.get("amount"),
                method=payload.validated_data.get("method", ""),
            )
        except PaymentRefused as exc:
            return Response(
                {"detail": str(exc), "code": "accept_refused"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(BookingSerializer(booking).data)

    @action(detail=True, methods=["post"], url_path="deposit/reject")
    def reject_deposit(self, request, pk=None):
        """Le versement n'a pas ete retrouve.

        Le rendez-vous retourne en attente de paiement plutot que d'etre
        annule : une capture floue ou un mauvais compte se corrigent, et
        annuler seche ferait perdre une cliente qui a peut-etre paye.
        """
        from apps.payments.services import PaymentRefused, reject_proof

        booking = self.get_object()
        payload = DepositReviewSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        try:
            reject_proof(
                booking=booking,
                actor=request.user,
                reason=payload.validated_data.get("reason", ""),
            )
        except PaymentRefused as exc:
            return Response(
                {"detail": str(exc), "code": "reject_refused"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(BookingSerializer(booking).data)

    @action(detail=True, methods=["post"], url_path="deposit/cancel")
    def cancel_deposit(self, request, pk=None):
        """Annule un encaissement noté par erreur.

        Sans cette route, un clic malencontreux marquait un acompte comme
        recu **definitivement** : la route d'encaissement refuse un second
        appel, et rien ne permettait de revenir en arriere. Le salon se
        retrouvait avec une caisse fausse et aucun recours.

        L'annulation est tracee au meme titre que l'encaissement : c'est une
        correction comptable, elle doit laisser une trace.
        """
        booking = self.get_object()

        if not booking.deposit_paid:
            return Response(
                {"detail": "Aucun acompte n'est noté comme encaissé.",
                 "code": "not_paid"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        previous = {
            "amount": str(booking.deposit_received),
            "method": booking.deposit_method,
        }

        booking.deposit_paid = False
        booking.deposit_paid_at = None
        booking.deposit_method = ""
        booking.deposit_received = Decimal("0")
        booking.save(
            update_fields=[
                "deposit_paid",
                "deposit_paid_at",
                "deposit_method",
                "deposit_received",
                "updated_at",
            ]
        )

        # La recette part avec l'encaissement annule. Sans cela, la
        # correction serait cosmetique : la caisse resterait fausse, et
        # personne ne saurait pourquoi.
        from apps.finance.services import remove_deposit_income

        remove_deposit_income(booking)

        AuditLog.objects.create(
            tenant_id=request.tenant_id,
            actor_user=request.user,
            action=AuditLog.Action.BOOKING_STATUS_CHANGED,
            resource_type="booking",
            resource_id=str(booking.id),
            metadata={"deposit_cancelled": previous},
        )
        return Response(BookingSerializer(booking).data)

    @action(detail=False, methods=["post"], url_path="check-in")
    def check_in(self, request):
        """Marque une arrivee, par le QR de la cliente ou par son code court.

        -------------------------------------------------------------------
        Pourquoi un QR plutot qu'un clic dans la liste
        -------------------------------------------------------------------

        Parce que le clic se fait de memoire. A midi, avec quatre clientes
        dans le salon, on marque « arrivee » sur la mauvaise ligne - et
        l'agenda ment jusqu'au soir. Le QR est porte par la cliente
        elle-meme : il designe *son* rendez-vous, pas celui qu'on croit.

        -------------------------------------------------------------------
        Et pourquoi deux chemins
        -------------------------------------------------------------------

        Parce que l'appareil photo manque les jours ou il faudrait qu'il
        marche : permission refusee, objectif raye, poste fixe a l'accueil,
        page ouverte en HTTP sur le reseau du salon. Le code a six
        caracteres se tape, se dicte au telephone, et aboutit exactement au
        meme endroit - memes controles, meme trace.

        Ni le jeton ni le code ne donnent de droit a eux seuls. C'est la
        session du salon qui autorise l'ecriture : quelqu'un qui
        photographierait l'ecran d'une cliente n'en ferait rien sans un
        compte du salon.
        """
        from apps.payments.tokens import (
            booking_from_checkin,
            booking_from_code,
            checkin_code_is_wellformed,
            normalize_checkin_code,
        )

        raw_token = str(request.data.get("token", "")).strip()
        raw_code = str(request.data.get("code", "")).strip()

        if raw_token:
            booking = booking_from_checkin(raw_token)
        elif raw_code:
            typed = normalize_checkin_code(raw_code)

            # Un caractere hors alphabet n'est pas un code inconnu : c'est une
            # lecture erronee, et le dire evite de chercher une cliente qui
            # n'existe pas.
            if not checkin_code_is_wellformed(typed):
                return Response(
                    {
                        "detail": "Ce code n'a pas la bonne forme : six "
                        "caractères, sans les lettres I, O, S, B, U ni les "
                        "chiffres 0, 1, 2, 5, 6, 8, 9.",
                        "code": "malformed_code",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            booking, ambiguous = booking_from_code(typed, request.tenant_id)
            if ambiguous:
                return Response(
                    {
                        "detail": "Deux rendez-vous portent ce code. "
                        "Scannez le QR de la cliente pour lever le doute.",
                        "code": "ambiguous_code",
                    },
                    status=status.HTTP_409_CONFLICT,
                )
            if booking is None:
                return Response(
                    {
                        "detail": "Aucun rendez-vous des deux prochains jours "
                        "ne porte ce code.",
                        "code": "unknown_code",
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )
        else:
            return Response(
                {"detail": "Scannez un QR ou saisissez un code d'arrivée.",
                 "code": "missing_code"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Le rendez-vous doit appartenir au salon connecte. Sans ce controle,
        # le QR d'une cliente d'un autre salon serait accepte ici.
        if booking is None or str(booking.tenant_id) != str(request.tenant_id):
            return Response(
                {"detail": "Ce code ne correspond à aucun rendez-vous de votre salon.",
                 "code": "unknown_code"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Le rendez-vous vise, quand le scanner a ete ouvert depuis une ligne
        # de l'agenda.
        #
        # Sans ce controle, scanner le QR de la voisine pendant qu'on est sur
        # la ligne d'Espoir noterait arrivee la mauvaise cliente - la seule
        # erreur que le QR existe pour empecher. La verification se fait ici
        # et non dans le navigateur : une comparaison cote client se contourne
        # en rejouant la requete.
        expected = str(request.data.get("booking", "")).strip()
        if expected and expected != str(booking.id):
            try:
                attendu = (
                    Booking.objects.select_related("customer")
                    .filter(id=expected, tenant_id=request.tenant_id)
                    .first()
                )
            except (ValidationError, ValueError):
                attendu = None

            return Response(
                {
                    "detail": (
                        f"Ce code est celui de {booking.customer.full_name}, "
                        + (
                            f"pas de {attendu.customer.full_name}."
                            if attendu
                            else "pas du rendez-vous ouvert."
                        )
                    ),
                    "code": "wrong_booking",
                    "booking": BookingSerializer(booking).data,
                },
                status=status.HTTP_409_CONFLICT,
            )

        if booking.status == Booking.Status.CHECKED_IN:
            return Response(
                {"detail": f"{booking.customer.full_name} est déjà notée arrivée.",
                 "code": "already_checked_in",
                 "booking": BookingSerializer(booking).data}
            )

        if booking.status != Booking.Status.CONFIRMED:
            return Response(
                # Le rendez-vous accompagne le refus : savoir *lequel* est
                # annule, et pour qui, est ce qui permet de trancher au
                # comptoir. Sans lui, le salon relit tout son agenda pour
                # comprendre ce que le message lui reproche.
                {"detail": "Ce rendez-vous n'est pas confirmé : "
                           f"il est « {booking.get_status_display().lower()} ».",
                 "code": "not_confirmed",
                 "booking": BookingSerializer(booking).data},
                status=status.HTTP_400_BAD_REQUEST,
            )

        previous = booking.status
        booking.status = Booking.Status.CHECKED_IN
        booking.save(update_fields=["status", "updated_at"])

        AuditLog.objects.create(
            tenant_id=request.tenant_id,
            actor_user=request.user,
            action=AuditLog.Action.BOOKING_STATUS_CHANGED,
            resource_type="booking",
            resource_id=str(booking.id),
            metadata={"from": previous, "to": booking.status, "via": "qr"},
        )

        return Response(
            {
                "detail": f"{booking.customer.full_name} est arrivée.",
                "booking": BookingSerializer(booking).data,
            }
        )

    @action(detail=False, methods=["get"])
    def summary(self, request):
        """Chiffres d'en-tete du tableau de bord."""
        from apps.salons.models import SalonProfile

        tenant = Tenant.objects.get(pk=request.tenant_id)
        now = timezone.now()
        horizon = now + timedelta(days=7)

        upcoming = Booking.objects.filter(
            starts_at__gte=now,
            starts_at__lt=horizon,
            status__in=Booking.BLOCKING_STATUSES,
        )

        # La tolerance voyage avec les chiffres d'en-tete plutot que dans un
        # second appel : l'agenda en a besoin a chaque rendu pour signaler les
        # rendez-vous en retard, et c'est une requete de moins au chargement.
        profile = SalonProfile.objects.filter(tenant_id=request.tenant_id).first()

        return Response(
            {
                "currency": tenant.currency,
                "late_tolerance_minutes": (
                    profile.late_tolerance_minutes if profile else 15
                ),
                "upcoming_count": upcoming.count(),
                "today_count": upcoming.filter(
                    starts_at__lt=now + timedelta(days=1)
                ).count(),
                "no_show_last_30_days": Booking.objects.filter(
                    status=Booking.Status.NO_SHOW,
                    starts_at__gte=now - timedelta(days=30),
                ).count(),
                "cancelled_last_30_days": Booking.objects.filter(
                    status=Booking.Status.CANCELLED,
                    starts_at__gte=now - timedelta(days=30),
                ).count(),
            }
        )


class WaitlistViewSet(TenantModelViewSet):
    """La file de rappel du salon.

    Elle ne reserve rien : c'est une liste de gens a rappeler, pas une file
    qui distribue automatiquement les creneaux liberes. Un rendez-vous
    attribue sans que la cliente l'ait redemande finit en absence.
    """

    serializer_class = WaitlistEntrySerializer
    model = WaitlistEntry
    select_related = ("service", "staff_member")
    required_roles = FRONT_DESK
    safe_roles = EVERYONE

    def get_queryset(self):
        queryset = super().get_queryset()

        # Par defaut on ne montre que ce qui reste a traiter : une liste qui
        # accumule les demandes classees depuis six mois ne se regarde plus.
        if self.request.query_params.get("status") == "all":
            return queryset.order_by("created_at")

        return queryset.filter(
            status__in=(WaitlistEntry.Status.WAITING, WaitlistEntry.Status.CONTACTED)
        ).order_by("created_at")

    @action(detail=True, methods=["post"])
    def contacted(self, request, pk=None):
        """Marque qu'on a rappele. Repond aussi a « qui reste-t-il ? »."""
        entry = self.get_object()
        entry.status = WaitlistEntry.Status.CONTACTED
        entry.contacted_at = timezone.now()
        entry.save(update_fields=["status", "contacted_at", "updated_at"])
        return Response(WaitlistEntrySerializer(entry).data)

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        """Classe une demande : rendez-vous pris ailleurs, ou sans suite."""
        entry = self.get_object()
        entry.status = (
            WaitlistEntry.Status.BOOKED
            if request.data.get("booked")
            else WaitlistEntry.Status.CLOSED
        )
        entry.save(update_fields=["status", "updated_at"])
        return Response(WaitlistEntrySerializer(entry).data)


class OverviewView(APIView):
    """La page d'accueil du tableau de bord, en une reponse.

    Vue simple plutot qu'une action sur un ViewSet : elle ne porte aucune
    ressource, elle assemble une lecture de six tables. L'accrocher a
    `BookingViewSet` laisserait croire qu'elle ne parle que de rendez-vous.

    Le detail des calculs, et ce que chaque chiffre promet, vivent dans
    `overview.py`.
    """

    permission_classes = [IsAuthenticated, IsTenantResolved]

    def get(self, request):
        tenant = Tenant.objects.get(pk=request.tenant_id)

        # `?brief=1` : uniquement ce qui attend un geste.
        #
        # La coquille du tableau de bord affiche une pastille sur la cloche,
        # sur **toutes** les pages. Lui faire charger le fil d'activite, le
        # classement des prestations et la repartition des notes a chaque
        # navigation serait payer une dizaine d'agregats pour un chiffre.
        if request.query_params.get("brief"):
            return Response({"attention": overview.attention()})

        data = overview.build(tenant)
        data["occupancy"] = overview.occupancy(tenant)
        return Response(data)
