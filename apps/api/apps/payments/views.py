"""Encaissement : ce que voit la cliente, ce que fait le salon."""

from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Membership
from apps.common.permissions import IsTenantResolved
from apps.common.viewsets import TenantModelViewSet
from apps.media.models import MediaAsset
from apps.scheduling.models import Booking

from . import services
from .models import DepositProof, PaymentChannel
from .tokens import (
    booking_from_cancel,
    booking_from_status,
    booking_from_token,
    checkin_code,
    checkin_token,
    payment_token,
    status_token,
)

MANAGERS = (Membership.Role.OWNER, Membership.Role.MANAGER)
FRONT_DESK = (*MANAGERS, Membership.Role.RECEPTIONIST)
EVERYONE = (*FRONT_DESK, Membership.Role.STAFF)


# ---------------------------------------------------------------------------
# Cote salon : declarer ses QR codes
# ---------------------------------------------------------------------------


class PaymentChannelSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    qr_url = serializers.SerializerMethodField()
    usable = serializers.BooleanField(read_only=True)

    class Meta:
        model = PaymentChannel
        fields = (
            "id",
            "kind",
            "kind_label",
            "qr_image",
            "qr_url",
            "account_name",
            "instructions",
            "active",
            "position",
            "usable",
        )

    def get_qr_url(self, channel) -> str:
        if not channel.qr_image_id or not channel.qr_image:
            return ""
        request = self.context.get("request")
        url = channel.qr_image.file.url
        return request.build_absolute_uri(url) if request else url


class PaymentChannelViewSet(TenantModelViewSet):
    serializer_class = PaymentChannelSerializer
    model = PaymentChannel
    select_related = ("qr_image",)
    required_roles = MANAGERS
    safe_roles = EVERYONE
    pagination_class = None  # un salon a deux ou trois moyens, pas cent


# ---------------------------------------------------------------------------
# Cote cliente : payer, puis envoyer sa preuve
# ---------------------------------------------------------------------------


class PublicPaymentView(APIView):
    """Comment payer l'acompte de ce rendez-vous.

    Le jeton signe tient lieu d'authentification : la cliente n'a pas de
    compte, et le rendez-vous ne doit pas etre consultable en devinant un
    identifiant. Le jeton porte l'identifiant du rendez-vous et expire.
    """

    permission_classes = [AllowAny, IsTenantResolved]
    throttle_scope = "public_read"

    def get(self, request):
        booking = booking_from_token(request.query_params.get("token", ""))
        if booking is None:
            return Response(
                {"detail": "Ce lien n'est plus valable.", "code": "invalid_token"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Ouvrir cette page apres l'echeance solde le rendez-vous.
        #
        # L'ecran affichait « le delai est depasse » depuis un etat calcule,
        # sans rien inscrire : le rendez-vous restait « en attente de
        # paiement » jusqu'au prochain balayage Celery - donc indefiniment
        # sur un poste sans worker. La cliente lisait « depasse » ici et
        # « un acompte reste a regler » dans son espace, au meme instant.
        services.expirer(booking)

        channels = services.channels_for(request.tenant_id)
        proof = getattr(booking, "deposit_proof", None)

        return Response(
            {
                # Un seul mot a lire cote navigateur : payable, waiting,
                # refused, settled, expired, cancelled. Recomposer cet etat
                # a partir de quatre champs, ici puis la-bas, garantit que
                # les deux versions finiront par ne plus dire la meme chose.
                "state": services.payment_state(booking),
                "expires_at": services.payment_deadline(booking),
                # Vers ou renvoyer quand la page n'a plus lieu d'etre. Le
                # jeton de suivi est emis des la reservation : il ouvre la
                # page de statut, en lecture seule, et rien d'autre.
                "status_token": status_token(booking),
                "booking": {
                    "id": str(booking.id),
                    "service_name": booking.service_name,
                    "starts_at": booking.starts_at,
                    "status": booking.status,
                    "deposit_amount": str(booking.deposit_amount),
                    "total_amount": str(booking.total_amount),
                },
                "channels": PaymentChannelSerializer(
                    channels, many=True, context={"request": request}
                ).data,
                "proof": (
                    {
                        "status": proof.status,
                        "submitted_at": proof.submitted_at,
                        "rejection_reason": proof.rejection_reason,
                    }
                    if proof
                    else None
                ),
            }
        )


def _method_label(method: str) -> str:
    """« Alipay » plutot que « alipay », et rien plutot que « Autre ».

    -----------------------------------------------------------------------
    Pourquoi une table ici
    -----------------------------------------------------------------------

    Le moyen de paiement vient de deux sources qui ne parlent pas la meme
    langue. Quand le salon note un encaissement a la main, c'est un choix du
    modele `Booking` - especes, Mobile Money, virement. Quand il accepte une
    preuve envoyee par la cliente, c'est le canal declare sur la preuve :
    `wechat`, `alipay`, qui ne figurent pas dans ces choix.

    `get_deposit_method_display()` renvoie alors la valeur brute, et la
    cliente lisait « Réglé par alipay » en minuscules au milieu d'une page
    soignee.

    « Autre » est tu volontairement : c'est la valeur de repli quand personne
    n'a precise le moyen, et l'afficher ajoute une ligne a lire pour
    apprendre qu'on ne sait pas.
    """
    if not method or method == "other":
        return ""

    from .models import PaymentChannel

    libelles = {
        **dict(PaymentChannel.Kind.choices),
        "cash": "Espèces",
        "mobile_money": "Mobile Money",
        "transfer": "Virement",
    }
    return str(libelles.get(method, method))


class PublicBookingStatusView(APIView):
    """Le suivi d'un rendez-vous, en lecture seule.

    -----------------------------------------------------------------------
    Pourquoi cette page existe
    -----------------------------------------------------------------------

    La page de reglement a une fin : une fois l'acompte accepte, elle n'a
    plus rien a proposer, et la laisser ouverte invite a payer deux fois.
    Mais la cliente, elle, a toujours des questions apres - c'est quand,
    avec qui, ai-je bien paye, que dois-je montrer en arrivant.

    Sans page de suivi, la seule reponse etait l'e-mail de confirmation,
    qu'on retrouve mal trois semaines plus tard. Celle-ci s'ouvre avec un
    jeton signe, tient dans un signet, et ne permet rien d'autre que lire.

    Elle sert aussi de destination : quand le salon confirme, la page de
    reglement y renvoie d'elle-meme.
    """

    permission_classes = [AllowAny, IsTenantResolved]
    throttle_scope = "public_read"

    def get(self, request):
        booking = booking_from_status(request.query_params.get("token", ""))
        if booking is None or str(booking.tenant_id) != str(request.tenant_id):
            return Response(
                {"detail": "Ce lien n'est plus valable.", "code": "invalid_token"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Meme regle que sur la page de reglement : consulter le suivi d'un
        # rendez-vous echu le solde, plutot que de le laisser afficher un
        # etat que la base contredit.
        services.expirer(booking)

        state = services.payment_state(booking)
        proof = getattr(booking, "deposit_proof", None)

        return Response(
            {
                "booking": {
                    "id": str(booking.id),
                    "service_name": booking.service_name,
                    "starts_at": booking.starts_at,
                    "ends_at": booking.ends_at,
                    "status": booking.status,
                    "status_label": booking.get_status_display(),
                    "staff_member_name": (
                        booking.staff_member.name if booking.staff_member else ""
                    ),
                    "customer_name": booking.customer.full_name,
                    "total_amount": str(booking.total_amount),
                    "options_snapshot": booking.options_snapshot,
                    "items_snapshot": booking.items_snapshot,
                    "travel_zone_name": booking.travel_zone_name,
                    "address": booking.address,
                    "cancellation_reason": booking.cancellation_reason,
                    # La page de suivi porte le bouton d'annulation : c'est
                    # le lien que la cliente garde dans ses e-mails, et celui
                    # qu'elle rouvre quand un imprevu arrive.
                    **_etat_annulation(booking),
                },
                "payment": {
                    "state": state,
                    "expires_at": services.payment_deadline(booking),
                    "deposit_amount": str(booking.deposit_amount),
                    "deposit_paid": booking.deposit_paid,
                    "deposit_received": str(booking.deposit_received),
                    "deposit_paid_at": booking.deposit_paid_at,
                    "deposit_method": _method_label(booking.deposit_method),
                    "rejection_reason": (
                        proof.rejection_reason
                        if proof and proof.status == DepositProof.Status.REJECTED
                        else ""
                    ),
                    # Le chemin de retour vers le reglement, tant qu'il y a
                    # quelque chose a regler. Vide sinon : un bouton « payer »
                    # sur un acompte deja recu est une invitation a payer deux
                    # fois.
                    "payment_token": (
                        payment_token(booking)
                        if state
                        in (
                            services.PaymentState.PAYABLE,
                            services.PaymentState.REFUSED,
                        )
                        else ""
                    ),
                },
                # Le QR d'arrivee n'apparait qu'une fois le salon d'accord :
                # le montrer avant laisserait croire qu'il vaut confirmation,
                # et on se presenterait pour un creneau que personne n'a
                # accepte.
                "checkin_token": (
                    checkin_token(booking)
                    if booking.status == Booking.Status.CONFIRMED
                    else ""
                ),
                # Le meme droit, sous une forme qui se tape : l'appareil photo
                # du salon peut etre en panne ou refuse, et la cliente est
                # deja devant le comptoir.
                "checkin_code": (
                    checkin_code(booking)
                    if booking.status == Booking.Status.CONFIRMED
                    else ""
                ),
            }
        )


class DepositProofSerializer(serializers.Serializer):
    token = serializers.CharField()
    channel = serializers.ChoiceField(
        choices=PaymentChannel.Kind.choices, required=False, allow_blank=True, default=""
    )
    reference = serializers.CharField(
        max_length=120, required=False, allow_blank=True, default=""
    )
    note = serializers.CharField(required=False, allow_blank=True, default="")
    image = serializers.ImageField(required=False, allow_null=True)


class PublicDepositProofView(APIView):
    """La cliente declare avoir paye, capture d'ecran a l'appui.

    Elle ne prouve rien en soi - une image se fabrique - mais elle permet au
    salon de retrouver le versement dans son historique. C'est pour cela
    qu'aucun etat n'avance tout seul ici : le rendez-vous passe simplement
    « en attente d'acceptation ».
    """

    permission_classes = [AllowAny, IsTenantResolved]
    throttle_scope = "deposit_proof"

    def post(self, request):
        payload = DepositProofSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        booking = booking_from_token(data["token"])
        if booking is None:
            return Response(
                {"detail": "Ce lien n'est plus valable.", "code": "invalid_token"},
                status=status.HTTP_404_NOT_FOUND,
            )

        asset = None
        upload = data.get("image")
        if upload is not None:
            # Deux protections, et il en faut deux.
            #
            # Une capture d'ecran de paiement porte le nom de la cliente et
            # parfois son solde. `private` la tient hors de la vitrine
            # publique, mais c'est un drapeau unique : le jour ou quelqu'un
            # le bascule, la capture d'une cliente se retrouve en ligne.
            #
            # Le genre `proof` est la seconde barriere. Il la sort aussi de
            # la mediatheque du salon, ou elle s'affichait entre deux photos
            # de coiffures sous le genre « galerie ».
            asset = MediaAsset.objects.create(
                tenant_id=booking.tenant_id,
                file=upload,
                content_type=getattr(upload, "content_type", "") or "image/jpeg",
                byte_size=getattr(upload, "size", 0) or 0,
                kind=MediaAsset.Kind.PROOF,
                visibility=MediaAsset.Visibility.PRIVATE,
                alt_text="Preuve de versement",
            )

        try:
            services.submit_proof(
                booking=booking,
                image=asset,
                channel=data.get("channel", ""),
                reference=data.get("reference", ""),
                note=data.get("note", ""),
            )
        except services.PaymentRefused as exc:
            return Response(
                {"detail": str(exc), "code": "proof_refused"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "status": booking.status,
                "detail": "Merci. Le salon vérifie le versement et vous confirme.",
            },
            status=status.HTTP_201_CREATED,
        )


# ---------------------------------------------------------------------------
# Cote salon : verifier et accepter
# ---------------------------------------------------------------------------


class DepositReviewSerializer(serializers.Serializer):
    amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True
    )
    method = serializers.CharField(max_length=20, required=False, allow_blank=True)
    reason = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default=""
    )


def _booking_for(request, pk) -> Booking:
    return get_object_or_404(Booking, pk=pk, tenant_id=request.tenant_id)


class PublicBookingCancelView(APIView):
    """Annulation par la cliente, dans la fenetre annoncee par le salon.

    -----------------------------------------------------------------------
    Pourquoi la cliente peut maintenant annuler elle-meme
    -----------------------------------------------------------------------

    Le salon publie « annulation gratuite jusqu'a 24 h avant » sur son
    mini-site, dans son e-mail de confirmation et dans sa page d'infos. C'est
    une promesse — et aucune interface ne permettait de l'exercer. La cliente
    devait telephoner ; le salon recevait des appels pour un geste que la
    page pouvait faire, et les clientes qui n'osaient pas appeler ne venaient
    simplement pas.

    Un creneau libere une journee a l'avance se reproprose. Un creneau
    abandonne en silence coute une demi-journee de travail.

    -----------------------------------------------------------------------
    Le jeton, et pourquoi ce n'est pas celui du suivi
    -----------------------------------------------------------------------

    Le jeton de suivi promet, dans sa propre documentation, de n'autoriser
    aucune ecriture ; il vit cent vingt jours dans un signet. Celui-ci est
    distinct, dure six heures, et n'est emis que lorsque l'annulation est
    reellement ouverte. La regle est revalidee ici : un jeton emis il y a
    cinq heures ne doit pas ouvrir une porte que le delai vient de fermer.
    """

    permission_classes = [AllowAny, IsTenantResolved]
    # Meme borne que l'envoi d'une preuve : c'est une ecriture publique, rare
    # pour un humain, et repetable par un robot.
    throttle_scope = "deposit_proof"

    def post(self, request):
        from apps.scheduling.services.annulation import cliente_peut_annuler
        from apps.scheduling.services.booking import BookingRefused, cancel_booking

        booking = booking_from_cancel(request.data.get("token", ""))
        if booking is None or str(booking.tenant_id) != str(request.tenant_id):
            return Response(
                {"detail": "Ce lien n'est plus valable.", "code": "invalid_token"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if booking.status == Booking.Status.CANCELLED:
            # Deja fait : on repond comme si l'on venait de le faire. Un
            # deuxieme clic, ou un renvoi de formulaire, ne doit pas produire
            # une erreur devant quelqu'un qui a obtenu ce qu'il voulait.
            return Response({"status": booking.status, "detail": "Déjà annulé."})

        if not cliente_peut_annuler(booking):
            return Response(
                {
                    "detail": (
                        "Le délai d'annulation est passé. "
                        "Contactez le salon, il reste joignable."
                    ),
                    "code": "cancel_window_closed",
                },
                status=status.HTTP_409_CONFLICT,
            )

        try:
            cancel_booking(
                booking=booking,
                reason=str(request.data.get("reason", ""))[:280],
                # `by_salon=False` : c'est la cliente. Le message qu'elle
                # recoit dit « votre rendez-vous est bien annule », et le
                # salon en recoit un de son cote — un creneau libere est une
                # information qui vaut de l'argent.
                by_salon=False,
            )
        except BookingRefused as exc:
            return Response(
                {"detail": str(exc), "code": "booking_refused"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({"status": booking.status, "detail": "Rendez-vous annulé."})


def _etat_annulation(booking) -> dict:
    """Import differe : `annulation` importe les modeles de `scheduling`, qui
    importent `payments` pour les jetons. Au niveau du module, la boucle se
    referme au demarrage."""
    from apps.scheduling.services.annulation import etat_annulation

    return etat_annulation(booking)
