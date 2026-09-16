from rest_framework import serializers

from apps.catalog.models import Service
from apps.common.serializers import TenantPrimaryKeyRelatedField

from .models import StaffMember, StaffService


class StaffMemberSerializer(serializers.ModelSerializer):
    # Les competences se pilotent depuis la fiche du prestataire : c'est la
    # que le salon raisonne ("Fatou fait les tresses"), pas depuis le service.
    service_ids = TenantPrimaryKeyRelatedField(
        Service, many=True, required=False, write_only=True
    )
    services = serializers.SerializerMethodField()

    # Realiser des prestations et pouvoir se connecter sont deux choses
    # differentes. Rien ne le disait a l'ecran, et la liste des prestataires
    # semblait contredire celle de l'equipe.
    has_access = serializers.SerializerMethodField()
    access_email = serializers.SerializerMethodField()

    class Meta:
        model = StaffMember
        fields = (
            "id",
            "membership",
            "name",
            "specialty",
            "bio",
            "photo",
            "position",
            "active",
            "services",
            "service_ids",
            "has_access",
            "access_email",
        )

    def get_has_access(self, staff_member) -> bool:
        """Cette personne peut-elle ouvrir le tableau de bord ?

        Realiser des prestations et avoir un compte sont deux choses
        differentes - une coiffeuse peut tres bien figurer a l'agenda sans
        jamais se connecter. Mais rien ne le disait a l'ecran, et la liste
        des prestataires semblait alors en contradiction avec celle de
        l'equipe.
        """
        return staff_member.membership_id is not None

    def get_access_email(self, staff_member) -> str:
        if not staff_member.membership_id:
            return ""
        return getattr(staff_member.membership.user, "email", "")

    def get_services(self, staff_member) -> list[dict]:
        return [
            {"id": str(row.service_id), "name": row.service.name}
            for row in staff_member.staff_services.select_related("service")
        ]

    def create(self, validated_data):
        services = validated_data.pop("service_ids", [])
        staff_member = super().create(validated_data)
        self._sync_services(staff_member, services)
        return staff_member

    def update(self, instance, validated_data):
        services = validated_data.pop("service_ids", None)
        staff_member = super().update(instance, validated_data)
        if services is not None:
            self._sync_services(staff_member, services)
        return staff_member

    def _sync_services(self, staff_member, services):
        wanted = {service.id for service in services}
        existing = {
            row.service_id: row for row in staff_member.staff_services.all()
        }

        for service_id, row in existing.items():
            if service_id not in wanted:
                row.delete()

        for service in services:
            if service.id not in existing:
                StaffService.objects.create(
                    tenant_id=staff_member.tenant_id,
                    staff_member=staff_member,
                    service=service,
                )
