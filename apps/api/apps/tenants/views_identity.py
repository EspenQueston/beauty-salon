"""L'identité du salon et de qui le tient.

---------------------------------------------------------------------------
Pourquoi une route à part
---------------------------------------------------------------------------

Ces cinq champs vivent dans trois tables — `Tenant` pour le nom du salon,
`User` pour le nom, l'e-mail et le téléphone de la gérante, `SalonProfile`
pour ce que voient les clientes. Ils n'ont rien à faire ensemble d'un point
de vue de modèle, et tout à faire ensemble d'un point de vue d'usage : on
vient les changer au même moment, quand on corrige une faute dans le nom du
salon ou qu'on change de numéro.

Les éparpiller sur trois écrans obligeait à savoir dans lequel chercher.

---------------------------------------------------------------------------
Ce que cette route ne fait pas
---------------------------------------------------------------------------

  - **Le sous-domaine ne change pas.** Il est imprimé sur des flyers, collé
    en QR code au mur du salon, partagé en story. Le changer casserait tous
    ces liens sans que personne ne s'en aperçoive avant la première cliente
    perdue. Il s'affiche donc, en lecture seule.
  - **Le mot de passe non plus.** Il a son propre écran, avec la vérification
    de l'ancien : le glisser dans un formulaire d'identité en ferait une
    case parmi d'autres.
  - **Personne d'autre que la gérante** ne modifie ces champs. Une réception
    qui renommerait le salon serait une surprise pour tout le monde.

---------------------------------------------------------------------------
Ce que la plateforme voit
---------------------------------------------------------------------------

Le nom écrit ici est celui de la ligne `Tenant`, et c'est exactement celui
que lit l'administration plateforme. Il n'y a pas de recopie, donc pas de
divergence possible : la supervision affiche le nom du salon, pas une copie
prise au moment de l'inscription.
"""

from django.db import transaction
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Membership, User
from apps.audit.models import AuditLog
from apps.common.permissions import HasTenantRole, IsTenantMember
from apps.tenants.models import Tenant

MANAGERS = (Membership.Role.OWNER, Membership.Role.MANAGER)
EVERYONE = (*MANAGERS, Membership.Role.RECEPTIONIST, Membership.Role.STAFF)


class IdentitySerializer(serializers.Serializer):
    """Les champs modifiables, et ceux qui ne le sont pas."""

    salon_name = serializers.CharField(max_length=120)
    owner_name = serializers.CharField(max_length=120, allow_blank=True)
    owner_email = serializers.EmailField()
    owner_phone = serializers.CharField(max_length=32, allow_blank=True)

    # Affichés, jamais écrits.
    slug = serializers.CharField(read_only=True)
    site_url = serializers.CharField(read_only=True)
    role = serializers.CharField(read_only=True)

    def validate_salon_name(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Le nom du salon ne peut pas être vide.")
        return value

    def validate_owner_email(self, value: str) -> str:
        """Une adresse déjà prise appartient à quelqu'un d'autre.

        L'e-mail sert d'identifiant de connexion : en laisser deux identiques
        rendrait l'un des deux comptes inaccessible. Le message ne dit pas à
        qui elle appartient — ce serait apprendre qui est inscrit.
        """
        value = value.strip().lower()
        current = self.context["user"]
        if User.objects.filter(email=value).exclude(pk=current.pk).exists():
            raise serializers.ValidationError(
                "Cette adresse est déjà utilisée par un autre compte."
            )
        return value


class SalonIdentityView(APIView):
    """Le nom du salon, et les coordonnées de qui le tient."""

    permission_classes = [IsTenantMember, HasTenantRole]
    required_roles = (Membership.Role.OWNER,)
    safe_roles = EVERYONE

    def get(self, request):
        return Response(self._payload(request))

    def patch(self, request):
        tenant = Tenant.objects.get(pk=request.tenant_id)
        user = request.user

        payload = IdentitySerializer(
            data=request.data, partial=True, context={"user": user}
        )
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        # On garde l'avant pour le journal : « nom modifié » sans dire depuis
        # quoi n'aide personne à retrouver ce qui s'est passé.
        avant = {
            "salon_name": tenant.name,
            "owner_name": user.display_name,
            "owner_email": user.email,
            "owner_phone": user.phone,
        }

        with transaction.atomic():
            if "salon_name" in data:
                tenant.name = data["salon_name"]
                tenant.save(update_fields=["name", "updated_at"])

            champs = []
            if "owner_name" in data:
                user.display_name = data["owner_name"].strip()
                champs.append("display_name")
            if "owner_email" in data:
                user.email = data["owner_email"]
                champs.append("email")
            if "owner_phone" in data:
                user.phone = data["owner_phone"].strip()
                champs.append("phone")
            if champs:
                user.save(update_fields=champs)

            # La fiche de prestataire de la gérante porte son nom : la laisser
            # à l'ancien ferait apparaître deux personnes sur le mini-site.
            if "owner_name" in data and data["owner_name"].strip():
                from apps.staff.models import StaffMember

                StaffMember.objects.filter(
                    membership__user=user, membership__tenant=tenant
                ).update(name=data["owner_name"].strip())

            apres = {
                "salon_name": tenant.name,
                "owner_name": user.display_name,
                "owner_email": user.email,
                "owner_phone": user.phone,
            }
            modifie = {
                cle: [avant[cle], apres[cle]]
                for cle in avant
                if avant[cle] != apres[cle]
            }
            if modifie:
                AuditLog.objects.create(
                    tenant=tenant,
                    actor_user=user,
                    action=AuditLog.Action.TENANT_STATUS_CHANGED,
                    resource_type="tenant",
                    resource_id=str(tenant.id),
                    metadata={"identite": modifie},
                )

        return Response(self._payload(request), status=status.HTTP_200_OK)

    def _payload(self, request) -> dict:
        from django.conf import settings

        tenant = Tenant.objects.get(pk=request.tenant_id)
        user = request.user
        scheme = "http" if settings.DEBUG else "https"
        port = f":{settings.WEB_PORT}" if settings.DEBUG else ""

        return {
            "salon_name": tenant.name,
            "owner_name": user.display_name,
            "owner_email": user.email,
            "owner_phone": user.phone,
            "slug": tenant.slug,
            "site_url": f"{scheme}://{tenant.slug}.{settings.PLATFORM_DOMAIN}{port}",
            "role": request.membership.role,
        }
