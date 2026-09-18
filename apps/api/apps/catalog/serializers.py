from rest_framework import serializers

from .models import Resource, Service, ServiceCategory, ServiceOption, ServiceResource


class ServiceCategorySerializer(serializers.ModelSerializer):
    service_count = serializers.SerializerMethodField()

    class Meta:
        model = ServiceCategory
        fields = ("id", "name", "position", "active", "service_count")

    def get_service_count(self, category) -> int:
        return category.services.count()


class ResourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Resource
        fields = ("id", "name", "kind", "capacity", "active")

    def validate_name(self, value):
        return value.strip()


class ServiceResourceSerializer(serializers.ModelSerializer):
    resource_name = serializers.CharField(source="resource.name", read_only=True)
    resource_capacity = serializers.IntegerField(
        source="resource.capacity", read_only=True
    )
    # Le nom de la prestation voyage avec le lien : sans lui, l'ecran des
    # ressources ne pourrait pas dire *ce qui* mobilise un bac sans
    # recharger tout le catalogue et faire la jointure cote navigateur.
    service_name = serializers.CharField(source="service.name", read_only=True)

    class Meta:
        model = ServiceResource
        fields = (
            "id",
            "service",
            "service_name",
            "resource",
            "resource_name",
            "resource_capacity",
        )


class ServiceOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceOption
        fields = (
            "id",
            "service",
            "name",
            "description",
            "price_delta",
            "duration_delta_minutes",
            "position",
            "active",
        )

    def validate_name(self, value):
        return value.strip()


class ServiceSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    staff_member_ids = serializers.SerializerMethodField()
    options = ServiceOptionSerializer(many=True, read_only=True)

    class Meta:
        model = Service
        fields = (
            "id",
            "category",
            "category_name",
            "name",
            "description",
            "duration_minutes",
            "price_kind",
            "price_amount",
            "requires_deposit",
            "location_mode",
            "image",
            "position",
            "active",
            "staff_member_ids",
            "options",
        )

    def get_staff_member_ids(self, service) -> list[str]:
        return [str(row.staff_member_id) for row in service.staff_services.all()]

    # Plus rien à valider ici sur l'acompte : la prestation ne porte qu'un
    # oui/non, et « l'acompte dépasse le prix » ne peut plus se produire —
    # le calcul le borne au total du rendez-vous.

    def create(self, validated_data):
        validated_data.setdefault("location_mode", _lieu_du_salon(self.context))
        service = super().create(validated_data)
        _link_solo_provider(service)
        return service


def _lieu_du_salon(context) -> str:
    """Le lieu par defaut d'une nouvelle prestation : celui du salon.

    -----------------------------------------------------------------------
    Le piege que ceci ferme
    -----------------------------------------------------------------------

    `Service.location_mode` valait « au salon » par defaut, quoi qu'ait
    declare le salon par ailleurs. Une gerante qui reglait son profil sur
    « au salon ou a domicile », declarait trois quartiers et leurs forfaits,
    puis creait ses prestations, obtenait un parcours de reservation ou
    l'etape « a domicile » n'apparaissait jamais.

    Rien n'etait casse : le moteur lit bien `service.location_mode`, et il
    disait « au salon ». Simplement, deux reglages qui parlent de la meme
    chose vivaient dans deux ecrans differents, et rien ne les reliait. Le
    symptome - « mes zones ne servent a rien » - ne designe pas sa cause.

    Le reglage du salon devient donc la valeur de depart. La prestation garde
    son champ : c'est ainsi qu'un salon qui se deplace declare la seule
    prestation qu'il ne fait qu'en cabine.
    """
    from apps.salons.models import SalonProfile, ServiceMode

    requete = context.get("request")
    tenant_id = getattr(requete, "tenant_id", None)
    if tenant_id is None:
        return ServiceMode.SALON

    profil = SalonProfile.objects.filter(tenant_id=tenant_id).first()
    return profil.service_mode if profil else ServiceMode.SALON


def _link_solo_provider(service) -> None:
    """Dans un salon d'une personne, elle fait tout.

    -----------------------------------------------------------------------
    Le piege que ceci ferme
    -----------------------------------------------------------------------

    Une prestation n'est reservable que si un `StaffService` relie quelqu'un
    a elle. Rien ne creait ce lien automatiquement : une gerante seule
    s'inscrivait, creait sa premiere prestation, ouvrait son mini-site et y
    lisait « aucune disponibilite ». Rien n'etait casse - il manquait une
    ligne dans une table dont elle n'a aucune raison de connaitre
    l'existence.

    C'est le premier abandon du parcours, et le plus silencieux : la page ne
    signale pas d'erreur, elle ne propose simplement rien.

    -----------------------------------------------------------------------
    Pourquoi seulement quand il n'y a qu'une personne
    -----------------------------------------------------------------------

    Parce que le lien n'y porte aucune information. Dans un salon a une
    personne, dire « c'est elle qui la realise » est une tautologie : il n'y
    a personne d'autre.

    Des qu'ils sont deux, le lien devient un choix reel - la prothesiste
    ongulaire ne pose pas les box braids - et le deviner produirait des
    creneaux que le salon ne peut pas tenir. Au-dela d'une personne, c'est
    donc a l'ecran « Prestataires » de trancher, et il le demande.
    """
    from apps.staff.models import StaffMember, StaffService

    actifs = list(StaffMember.objects.filter(active=True)[:2])
    if len(actifs) != 1:
        return

    StaffService.objects.get_or_create(
        tenant_id=service.tenant_id,
        staff_member=actifs[0],
        service=service,
    )
