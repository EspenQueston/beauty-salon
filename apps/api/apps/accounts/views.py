from django.conf import settings
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.http import urlsafe_base64_decode
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import HasTenantRole, IsTenantMember
from apps.tenants.models import Tenant

from .models import Invitation, Membership, User
from .serializers import (
    AcceptInvitationSerializer,
    InvitationCreateSerializer,
    InvitationSerializer,
    LoginSerializer,
    MembershipSerializer,
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    SignupSerializer,
    SlugAvailabilitySerializer,
    UserSerializer,
)
from .services import (
    InvitationError,
    SignupError,
    accept_invitation,
    find_invitation,
    invite_member,
    request_password_reset,
    signup_salon,
)


class LoginView(APIView):
    """Ouvre une session Django. Le cookie est pose sur le domaine parent,
    ce qui le rend valable pour app. et api. sans duplication."""

    permission_classes = [AllowAny]
    throttle_scope = "login"

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = authenticate(
            request,
            username=serializer.validated_data["email"].lower(),
            password=serializer.validated_data["password"],
        )
        if user is None:
            # Message volontairement identique pour un e-mail inconnu et un
            # mot de passe faux : ne pas reveler quels comptes existent.
            return Response(
                {"detail": "Identifiants invalides.", "code": "invalid_credentials"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        login(request, user)
        return Response(UserSerializer(user).data)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class SessionView(APIView):
    """Utilisateur courant et salons auxquels il appartient."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)


# ---------------------------------------------------------------------------
# Inscription d'un salon
# ---------------------------------------------------------------------------


class SlugAvailabilityView(APIView):
    """Verifie une adresse de sous-domaine pendant la saisie."""

    permission_classes = [AllowAny]
    throttle_scope = "public_read"

    def get(self, request):
        serializer = SlugAvailabilitySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        slug = serializer.validated_data["slug"].lower()

        taken = (
            slug in settings.RESERVED_SUBDOMAINS
            or Tenant.objects.filter(slug=slug).exists()
        )
        return Response(
            {
                "slug": slug,
                "available": not taken,
                "hostname": f"{slug}.{settings.PLATFORM_DOMAIN}",
            }
        )


class SignupView(APIView):
    """Creation d'un salon par son proprietaire.

    Le salon nait « en preparation » : il n'est pas public tant que l'equipe
    plateforme ne l'a pas valide.

    **Aucune session n'est ouverte ici.** L'inscription prouve qu'on sait
    remplir un formulaire ; la connexion prouve qu'on connait le mot de passe
    qu'on vient de choisir. Les separer a trois effets concrets :

      - la personne verifie tout de suite ses identifiants, au lieu de les
        decouvrir faux a la prochaine visite ;
      - une inscription depuis un poste partage ne laisse pas une session
        ouverte derriere elle ;
      - le formulaire d'inscription cesse d'etre un moyen d'obtenir une
        session authentifiee sans jamais presenter de mot de passe.
    """

    permission_classes = [AllowAny]
    throttle_scope = "signup"

    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            tenant, user = signup_salon(
                name=data["salon_name"],
                slug=data["slug"],
                email=data["email"],
                password=data["password"],
                display_name=data.get("display_name", ""),
                phone=data.get("phone", ""),
                country=data["country"],
                timezone_name=data["timezone_name"],
                currency=data["currency"],
                theme_config=data.get("theme_config"),
            )
        except SignupError as exc:
            return Response(
                {"detail": str(exc), "code": "signup_refused"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                # L'adresse est renvoyee pour que l'ecran de connexion la
                # pre-remplisse : on ne fait pas retaper ce qui vient d'etre
                # saisi deux lignes plus haut.
                "email": user.email,
                "tenant": {
                    "id": str(tenant.id),
                    "name": tenant.name,
                    "slug": tenant.slug,
                    "status": tenant.status,
                    "hostname": f"{tenant.slug}.{settings.PLATFORM_DOMAIN}",
                },
            },
            status=status.HTTP_201_CREATED,
        )


# ---------------------------------------------------------------------------
# Mots de passe
# ---------------------------------------------------------------------------


class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "password_reset"

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        request_password_reset(serializer.validated_data["email"])

        # Reponse identique que le compte existe ou non : sinon ce
        # formulaire deviendrait un annuaire des adresses inscrites.
        return Response(
            {"detail": "Si un compte existe, un e-mail vient d'être envoyé."}
        )


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "password_reset"

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        user = self._user_from_uid(data["uid"])
        if user is None or not default_token_generator.check_token(user, data["token"]):
            return Response(
                {"detail": "Lien invalide ou expiré.", "code": "invalid_token"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.set_password(data["password"])
        user.save(update_fields=["password", "updated_at"])
        # Changer le mot de passe invalide le jeton : il derive du hash.
        return Response({"detail": "Mot de passe mis à jour."})

    def _user_from_uid(self, uid: str):
        try:
            pk = urlsafe_base64_decode(uid).decode()
            return User.objects.get(pk=pk, is_active=True)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist, DjangoValidationError):
            return None


class PasswordChangeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = PasswordChangeSerializer(
            data=request.data, context={"user": request.user}
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if not request.user.check_password(data["current_password"]):
            return Response(
                {"detail": "Mot de passe actuel incorrect.", "code": "invalid_password"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        request.user.set_password(data["new_password"])
        request.user.save(update_fields=["password", "updated_at"])
        # Sans cela, changer son mot de passe deconnecterait la session en cours.
        update_session_auth_hash(request, request.user)

        return Response({"detail": "Mot de passe mis à jour."})


# ---------------------------------------------------------------------------
# Invitations
# ---------------------------------------------------------------------------


class PublicInvitationView(APIView):
    """Consultation d'une invitation depuis son lien, sans etre connecte."""

    permission_classes = [AllowAny]
    throttle_scope = "public_read"

    def get(self, request):
        try:
            invitation = find_invitation(request.query_params.get("token", ""))
        except InvitationError as exc:
            return Response(
                {"detail": str(exc), "code": "invalid_invitation"},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            {
                "email": invitation.email,
                "role": invitation.role,
                "role_display": invitation.get_role_display(),
                "salon_name": invitation.tenant.name,
                # Indique au frontend s'il doit demander un mot de passe.
                "account_exists": User.objects.filter(email=invitation.email).exists(),
            }
        )


class AcceptInvitationView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "invitation_accept"

    def post(self, request):
        serializer = AcceptInvitationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            user, invitation = accept_invitation(
                token=data["token"],
                password=data.get("password") or None,
                display_name=data.get("display_name", ""),
            )
        except InvitationError as exc:
            return Response(
                {"detail": str(exc), "code": "invalid_invitation"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        login(request, user)
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Equipe, cote salon
# ---------------------------------------------------------------------------

MANAGERS = (Membership.Role.OWNER, Membership.Role.MANAGER)
EVERYONE = (*MANAGERS, Membership.Role.RECEPTIONIST, Membership.Role.STAFF)


class MembershipViewSet(
    mixins.ListModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """Membres de l'equipe du salon courant."""

    serializer_class = MembershipSerializer
    permission_classes = [IsTenantMember, HasTenantRole]
    required_roles = MANAGERS
    safe_roles = EVERYONE
    pagination_class = None

    def get_queryset(self):
        return Membership.objects.filter(
            tenant_id=self.request.tenant_id
        ).select_related("user", "tenant")

    def perform_update(self, serializer):
        membership = self.get_object()
        # Un salon doit toujours garder au moins un proprietaire : sinon
        # plus personne ne peut inviter, facturer ou fermer le compte.
        if membership.role == Membership.Role.OWNER and self._last_owner(membership):
            raise DRFValidationError(
                {"role": "Ce salon doit conserver au moins un propriétaire."}
            )
        serializer.save()

    def perform_destroy(self, instance):
        if instance.role == Membership.Role.OWNER and self._last_owner(instance):
            raise DRFValidationError(
                {"role": "Ce salon doit conserver au moins un propriétaire."}
            )
        instance.delete()

    def _last_owner(self, membership) -> bool:
        return (
            Membership.objects.filter(
                tenant_id=membership.tenant_id,
                role=Membership.Role.OWNER,
                status=Membership.Status.ACTIVE,
            )
            .exclude(pk=membership.pk)
            .count()
            == 0
        )


class InvitationViewSet(
    mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet
):
    """Invitations envoyees par le salon courant."""

    serializer_class = InvitationSerializer
    permission_classes = [IsTenantMember, HasTenantRole]
    required_roles = MANAGERS
    safe_roles = MANAGERS
    pagination_class = None

    def get_queryset(self):
        return Invitation.objects.select_related("invited_by")

    def create(self, request, *args, **kwargs):
        payload = InvitationCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        tenant = get_object_or_404(Tenant, pk=request.tenant_id)
        try:
            invitation = invite_member(
                tenant=tenant,
                email=payload.validated_data["email"],
                role=payload.validated_data["role"],
                invited_by=request.user,
            )
        except InvitationError as exc:
            return Response(
                {"detail": str(exc), "code": "invitation_refused"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except IntegrityError:
            return Response(
                {
                    "detail": "Une invitation est déjà en attente pour cette adresse.",
                    "code": "invitation_pending",
                },
                status=status.HTTP_409_CONFLICT,
            )

        return Response(
            InvitationSerializer(invitation).data, status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=["post"])
    def revoke(self, request, pk=None):
        invitation = self.get_object()
        if not invitation.is_pending:
            return Response(
                {"detail": "Cette invitation n'est plus en attente.", "code": "not_pending"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        invitation.revoked_at = timezone.now()
        invitation.save(update_fields=["revoked_at", "updated_at"])
        return Response(InvitationSerializer(invitation).data)
