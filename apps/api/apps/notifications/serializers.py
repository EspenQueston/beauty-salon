"""Ce qui traverse vers le navigateur.

La notification est envoyee telle qu'elle est stockee : le genre brut, pas
son libelle traduit. C'est le frontend qui choisit l'icone, la couleur et la
formulation — il est le seul a savoir sur quel ecran il se trouve, et un
libelle fige en base vieillirait mal.
"""

from __future__ import annotations

from rest_framework import serializers

from apps.common.reseau import AdresseInterdite, verifier_adresse_publique

from .models import Notification, PlatformNotification, PushSubscription


class NotificationSerializer(serializers.ModelSerializer):
    lue = serializers.BooleanField(read_only=True)

    class Meta:
        model = Notification
        fields = ("id", "genre", "titre", "corps", "lien", "lue", "created_at")
        read_only_fields = fields


class PlatformNotificationSerializer(serializers.ModelSerializer):
    lue = serializers.BooleanField(read_only=True)
    salon = serializers.CharField(source="tenant.name", read_only=True, default="")

    class Meta:
        model = PlatformNotification
        fields = ("id", "genre", "titre", "corps", "lien", "lue", "salon", "created_at")
        read_only_fields = fields


class AbonnementSerializer(serializers.Serializer):
    """L'abonnement tel que `PushManager.subscribe()` le rend.

    La forme vient de la norme, pas de nous : `endpoint` et un objet `keys`
    a deux entrees. On la recopie telle quelle plutot que de la remodeler,
    pour que le code du navigateur reste `JSON.stringify(abonnement)`.
    """

    endpoint = serializers.URLField(max_length=2000)
    cle_p256dh = serializers.CharField(max_length=200)
    cle_auth = serializers.CharField(max_length=100)
    appareil = serializers.CharField(max_length=80, required=False, allow_blank=True)
    portee = serializers.ChoiceField(
        choices=PushSubscription.Portee.choices,
        default=PushSubscription.Portee.SALON,
    )

    def validate_endpoint(self, valeur: str) -> str:
        """Refuse tout ce qui n'est pas une adresse de push.

        Ce champ decide ou le serveur ira poster, plus tard, depuis le
        worker Celery. Sans controle, n'importe quel compte connecte
        emprunterait notre place sur le reseau pour joindre une machine
        interne : c'est la faille SSRF, et elle se referme mal une fois
        ouverte.

        On ne peut pas lister les hotes autorises — chaque navigateur a les
        siens et ils changent. On verifie donc ce qui ne change pas : HTTPS
        obligatoire, et une adresse qui ne pointe pas vers notre propre
        reseau. La regle est partagee avec l'import de medias.
        """
        try:
            verifier_adresse_publique(valeur, schemes=("https",))
        except AdresseInterdite as exc:
            raise serializers.ValidationError(str(exc)) from exc
        return valeur
