"""Espace cliente : son compte, ses rendez-vous, son salon favori."""

from django.contrib.auth import login
from django.db import transaction
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Membership, User

from .models import ClientProfile, HiddenBooking
from .serializers import (
    ClientBookingSerializer,
    ClientProfileSerializer,
    ClientSignupSerializer,
)
from .services import bookings_for, linked_salons


class IsClient(IsAuthenticated):
    """Refuse l'espace cliente aux comptes d'equipe.

    Un proprietaire de salon connecte a son tableau de bord n'a rien a faire
    ici : il n'a pas de `ClientProfile`, et le laisser passer creerait un
    espace vide dont personne ne comprendrait le sens.
    """

    message = "Cet espace est réservé aux clientes."

    def has_permission(self, request, view):
        return super().has_permission(request, view) and hasattr(request.user, "client_profile")


class ClientSignupView(APIView):
    """Creation d'un compte cliente, depuis n'importe quel mini-site."""

    permission_classes = [AllowAny]
    throttle_scope = "signup"

    def post(self, request):
        payload = ClientSignupSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        with transaction.atomic():
            user = User.objects.create_user(
                email=data["email"],
                password=data["password"],
                display_name=data["full_name"].strip(),
                phone=data["phone"],
            )
            profile = ClientProfile.objects.create(
                user=user,
                whatsapp=data.get("whatsapp", "").strip(),
                wechat=data.get("wechat", "").strip(),
                # Le salon depuis lequel elle s'inscrit devient son favori :
                # c'est le seul qu'elle connaisse a cet instant, et le
                # redemander serait une question sans interet.
                preferred_salon_id=getattr(request, "tenant_id", None),
            )

        # Connexion immediate : demander de se reconnecter juste apres avoir
        # choisi un mot de passe est une etape que personne ne comprend.
        login(request, user)

        return Response(ClientProfileSerializer(profile).data, status=status.HTTP_201_CREATED)


class ClientPasswordResetView(APIView):
    """« Mot de passe oublié » depuis un mini-site.

    Toujours la même réponse, que l'adresse soit inscrite ou non. Bornée
    comme la réinitialisation de l'espace professionnel : chaque appel peut
    envoyer un e-mail.
    """

    permission_classes = [AllowAny]
    throttle_scope = "password_reset"

    def post(self, request):
        from apps.accounts.serializers import PasswordResetRequestSerializer
        from apps.tenants.models import Tenant

        from .services import demander_nouveau_mot_de_passe

        payload = PasswordResetRequestSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        tenant = Tenant.objects.filter(pk=getattr(request, "tenant_id", None)).first()
        if tenant is not None:
            demander_nouveau_mot_de_passe(
                payload.validated_data["email"],
                tenant,
                langue=str(request.data.get("lang", "fr"))[:2],
            )
        return Response(
            {"detail": "Si un compte existe pour cette adresse, un e-mail vient d'être envoyé."}
        )


class ClientMeView(APIView):
    """Le compte, et ce qu'on peut y changer."""

    permission_classes = [IsClient]

    def get(self, request):
        return Response(ClientProfileSerializer(request.user.client_profile).data)

    def patch(self, request):
        serializer = ClientProfileSerializer(
            request.user.client_profile, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class ClientForgetBookingView(APIView):
    """Retire une visite close de l'historique de la cliente.

    Le rendez-vous n'est pas supprime : il porte le chiffre d'affaires du
    salon. Seule la vue de la cliente change. Voir `HiddenBooking`.

    Un rendez-vous a venir ne se retire pas : la cliente le croirait annule
    alors que le salon l'attend toujours. On annule chez le salon, on
    n'efface pas la ligne.
    """

    permission_classes = [IsClient]

    def post(self, request):

        booking_id = str(request.data.get("booking", "")).strip()
        if not booking_id:
            return Response({"detail": "Rendez-vous manquant.", "code": "missing"}, status=400)

        # On verifie que la visite appartient bien a cette cliente, et
        # qu'elle est close. Sans ce controle, n'importe quel identifiant
        # pourrait etre masque - sans consequence pour autrui, mais autant
        # ne pas laisser ecrire n'importe quoi.
        owned = {row["id"]: row for row in bookings_for(request.user)}
        row = owned.get(booking_id)

        if row is None:
            return Response(
                {"detail": "Ce rendez-vous n'est pas dans votre historique.", "code": "not_yours"},
                status=404,
            )
        if not row.get("can_forget"):
            return Response(
                {
                    "detail": "Ce rendez-vous est encore à venir. "
                    "Contactez le salon pour l'annuler.",
                    "code": "still_upcoming",
                },
                status=400,
            )

        HiddenBooking.objects.get_or_create(user=request.user, booking_id=booking_id)
        return Response({"detail": "Retiré de votre historique."})


class ClientBookingsView(APIView):
    """Historique, tous salons confondus.

    Chaque salon est lu dans son propre contexte : voir `services.py`.
    """

    permission_classes = [IsClient]

    def get(self, request):
        rows = bookings_for(request.user)
        return Response(
            {
                "salons": [
                    {"slug": link.tenant.slug, "name": link.tenant.name}
                    for link in linked_salons(request.user)
                ],
                "bookings": ClientBookingSerializer(rows, many=True).data,
            }
        )


class ClientSessionView(APIView):
    """Qui est connecte, et de quelle nature de compte.

    Une seule route pour les deux natures : le navigateur n'a pas a deviner
    s'il doit interroger l'espace salon ou l'espace cliente.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        is_client = hasattr(request.user, "client_profile")
        return Response(
            {
                "email": request.user.email,
                "display_name": request.user.display_name,
                "is_client": is_client,
                "is_staff_member": Membership.objects.filter(
                    user=request.user, status=Membership.Status.ACTIVE
                ).exists(),
                "client": ClientProfileSerializer(request.user.client_profile).data
                if is_client
                else None,
            }
        )
