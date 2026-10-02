from django.conf import settings
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.http import urlsafe_base64_decode
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import BaseThrottle
from rest_framework.views import APIView

from apps.common.permissions import HasTenantRole, IsTenantMember
from apps.tenants.models import Tenant

from . import journal, mfa_api, securite, tasks
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
    signup_salon,
)


def _ip(request) -> str:
    """L'adresse du client, en tenant compte du proxy (meme regle que DRF)."""
    return BaseThrottle().get_ident(request) or ""


TROP_DE_TENTATIVES = Response(
    {
        "detail": "Trop de tentatives. Patientez quelques minutes avant de réessayer.",
        "code": "too_many_attempts",
    },
    status=status.HTTP_429_TOO_MANY_REQUESTS,
)


class LoginView(APIView):
    """Ouvre une session Django. Le cookie est pose sur le domaine parent,
    ce qui le rend valable pour app. et api. sans duplication."""

    permission_classes = [AllowAny]
    throttle_scope = "login"

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].strip().lower()
        ip = _ip(request)

        # Frein par adresse visee et par IP, en plus de celui de DRF (par IP
        # seulement). Il porte sur l'adresse saisie, que le compte existe ou
        # non : la reponse ne dit donc rien de l'annuaire.
        if securite.connexion_bloquee(email, ip):
            return TROP_DE_TENTATIVES

        user = authenticate(
            request,
            username=email,
            password=serializer.validated_data["password"],
        )
        if user is None:
            if securite.noter_echec(email, ip):
                journal.consigner("AUTH_ACCOUNT_LOCKED", request=request, email=email)
                journal.alerter_plateforme(
                    "Connexions suspendues après des échecs répétés",
                    f"{email} : {securite.ECHECS_PAR_ADRESSE} mots de passe faux en "
                    f"{securite.FENETRE_CONNEXION // 60} minutes.",
                )
            journal.consigner("AUTH_LOGIN_FAILED", request=request, email=email)
            # Message volontairement identique pour un e-mail inconnu, un mot
            # de passe faux ou un compte desactive : ne pas reveler quels
            # comptes existent.
            return Response(
                {
                    "detail": "Adresse e-mail ou mot de passe incorrect.",
                    "code": "invalid_credentials",
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        securite.noter_succes(email)
        # Double authentification active : le mot de passe ne suffit pas, la
        # session attend le code (voir mfa_api.py).
        if mfa_api.active(user):
            return mfa_api.mettre_en_attente(request, user)
        # `login` change la cle de session : une session fixee avant la
        # connexion ne survit pas.
        login(request, user)
        journal.consigner("AUTH_LOGIN_SUCCEEDED", request=request, user=user, mfa=False)
        return Response(UserSerializer(user).data)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class EmailVerifyView(APIView):
    """Le clic sur le lien recu par e-mail. Ouvert : on n'est pas forcement connecte."""

    permission_classes = [AllowAny]
    throttle_scope = "email_verification"

    def post(self, request):
        from . import verification

        try:
            user = verification.verifier(str(request.data.get("token", ""))[:512])
        except verification.JetonInvalide as exc:
            return Response(
                {"detail": str(exc), "code": "invalid_token"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        journal.consigner("AUTH_EMAIL_VERIFIED", request=request, user=user)
        return Response({"detail": "Adresse e-mail confirmée.", "verified": True})


class EmailVerifyResendView(APIView):
    """Renvoyer le lien, depuis une session ouverte. Freine par adresse."""

    permission_classes = [IsAuthenticated]
    throttle_scope = "email_verification"

    def post(self, request):
        user = request.user
        if user.email_verified_at is not None:
            return Response({"detail": "Votre adresse est déjà confirmée.", "verified": True})
        if not securite.envoi_autorise("verification", user.email):
            return Response(
                {
                    "detail": "Un e-mail vient d'être envoyé. Patientez quelques minutes "
                    "avant d'en demander un autre.",
                    "code": "too_many_attempts",
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        langue = str(request.data.get("lang", "fr"))[:2]
        base = tasks.base_cliente(user, langue) if hasattr(user, "client_profile") else ""
        user_id = str(user.pk)
        transaction.on_commit(lambda: tasks.verification.delay(user_id, base, langue))
        return Response({"detail": "Un nouveau lien vient de vous être envoyé.", "verified": False})


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
                code_parrainage=data.get("code_parrainage", ""),
                # L'IP n'est gardee qu'en empreinte, pour rapprocher des
                # inscriptions parrainees en serie.
                ip=BaseThrottle().get_ident(request),
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
        # Toujours une tache, que le compte existe ou non : la recherche et
        # l'envoi ont lieu hors de la requete, le temps de reponse est donc
        # le meme dans les deux cas. Voir `tasks.py`.
        email = serializer.validated_data["email"].strip().lower()
        transaction.on_commit(lambda: tasks.reinitialisation.delay(email))

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
        champs = ["password", "updated_at"]
        if user.email_verified_at is None:
            # Le lien est arrive dans cette boite : l'adresse est prouvee.
            user.email_verified_at = timezone.now()
            champs.append("email_verified_at")
        user.save(update_fields=champs)
        # Changer le mot de passe invalide le jeton (il derive du hash) et
        # ferme toutes les sessions ouvertes : Django verifie a chaque
        # requete l'empreinte du mot de passe gardee dans la session.
        securite.noter_succes(user.email)
        journal.consigner("AUTH_PASSWORD_RESET", request=request, user=user)
        transaction.on_commit(
            lambda: tasks.alerte_securite.delay(user.email, "mot_de_passe", nom=user.display_name)
        )
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
        # Les autres sessions sont fermees ; celle-ci est gardee, sinon
        # changer son mot de passe deconnecterait la personne qui le fait.
        update_session_auth_hash(request, request.user)
        user = request.user
        journal.consigner("AUTH_PASSWORD_CHANGED", request=request, user=user)
        transaction.on_commit(
            lambda: tasks.alerte_securite.delay(user.email, "mot_de_passe", nom=user.display_name)
        )

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
                utilisateur_connecte=request.user,
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

    def _verifier_droits(self, membership, nouveau_role=None) -> None:
        """Qui peut toucher a quoi dans l'equipe.

        Sans ces regles, une gerante pouvait se nommer proprietaire elle-meme
        (PATCH de son propre role), puis retirer la proprietaire : la
        facturation, la suppression du salon et le parrainage lui revenaient.
        Le role vient du membre qui agit, jamais de la requete.
        """
        acteur = self.request.membership
        est_proprio = acteur.role == Membership.Role.OWNER
        if membership.pk == acteur.pk and nouveau_role not in (None, membership.role):
            raise DRFValidationError({"role": "Vous ne pouvez pas changer votre propre rôle."})
        touche_un_proprio = membership.role == Membership.Role.OWNER or (
            nouveau_role == Membership.Role.OWNER
        )
        if touche_un_proprio and not est_proprio:
            raise DRFValidationError(
                {"role": "Seul un propriétaire peut nommer ou modifier un propriétaire."}
            )

    def perform_update(self, serializer):
        membership = self.get_object()
        self._verifier_droits(membership, serializer.validated_data.get("role"))
        # Un salon doit toujours garder au moins un proprietaire : sinon
        # plus personne ne peut inviter, facturer ou fermer le compte.
        if (
            membership.role == Membership.Role.OWNER
            and serializer.validated_data.get("role", membership.role) != Membership.Role.OWNER
            and self._last_owner(membership)
        ):
            raise DRFValidationError(
                {"role": "Ce salon doit conserver au moins un propriétaire."}
            )
        serializer.save()

    def perform_destroy(self, instance):
        self._verifier_droits(instance)
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
        if (
            payload.validated_data["role"] == Membership.Role.OWNER
            and request.membership.role != Membership.Role.OWNER
        ):
            return Response(
                {
                    "detail": "Seul un propriétaire peut inviter un propriétaire.",
                    "code": "invitation_refused",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

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
