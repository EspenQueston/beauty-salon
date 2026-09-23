"""Ce que la cloche lit, et ce que l'appareil declare.

---------------------------------------------------------------------------
Deux familles, deux portes
---------------------------------------------------------------------------

`/notifications` sert le tableau de bord d'un salon : le tenant vient du
middleware, et la politique RLS tient la porte en dessous.

`/plateforme/notifications` sert l'administration. Elle travaille hors
contexte tenant — c'est tout son objet — et son controle d'acces est donc
entierement applicatif : `is_platform_admin`, et rien d'autre.

Les deux sont volontairement separees. Une seule vue qui aurait bascule
d'une table a l'autre selon le drapeau de l'utilisateur aurait mis la seule
chose qui protege les donnees de la plateforme dans un `if`.

---------------------------------------------------------------------------
Pourquoi la liste n'est pas paginee
---------------------------------------------------------------------------

Une cloche n'est pas une archive. Elle montre ce qui est arrive recemment,
et l'on agit ou l'on oublie. Trente lignes couvrent plusieurs jours pour un
salon actif ; au-dela, ce qu'on cherche n'est plus une notification mais un
rendez-vous, et il se cherche dans l'agenda.

Le compteur des non-lues, lui, est exact : c'est lui qu'on lit du coin de
l'oeil, et un « 9+ » qui mentirait ferait douter de tout le reste.
"""

from __future__ import annotations

from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import IsPlatformAdmin, IsTenantResolved

from . import push
from .models import Notification, PlatformNotification, PushSubscription
from .serializers import (
    AbonnementSerializer,
    NotificationSerializer,
    PlatformNotificationSerializer,
)

# Ce que la cloche affiche d'un coup.
FENETRE = 30


class _BoiteMixin:
    """Le comportement commun aux deux boites.

    Les sous-classes n'ont qu'a dire *quelles* lignes leur appartiennent et
    avec quel serialiseur les rendre. Tout le reste — le compteur, le
    marquage, la fenetre — est identique, et doit le rester : deux cloches
    qui compteraient differemment seraient impossibles a expliquer.
    """

    serializer_class: type
    model: type

    def lignes(self, request):  # pragma: no cover - redefini
        raise NotImplementedError

    def get(self, request):
        lignes = self.lignes(request)
        recentes = lignes[:FENETRE]

        return Response(
            {
                "non_lues": lignes.filter(lu_le__isnull=True).count(),
                "resultats": self.serializer_class(recentes, many=True).data,
                # Le navigateur n'a pas besoin de la connaitre pour afficher
                # la liste, mais il en a besoin pour proposer l'abonnement —
                # et proposer une permission qu'on ne saurait pas utiliser
                # serait la faire accorder pour rien.
                "push_actif": push.configure(),
            }
        )

    def post(self, request):
        """Marque des notifications comme lues.

        `{"toutes": true}` ou `{"ids": [...]}`. Deux formes parce qu'il y a
        deux gestes : ouvrir le panneau (on a tout vu) et cliquer une ligne
        (on a vu celle-la, on part ailleurs).
        """
        lignes = self.lignes(request).filter(lu_le__isnull=True)

        if not request.data.get("toutes"):
            ids = request.data.get("ids") or []
            if not isinstance(ids, list):
                return Response(
                    {"detail": "`ids` doit être une liste."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            lignes = lignes.filter(pk__in=ids)

        # Une seule requete plutot qu'une boucle de `marquer_lue()` : ouvrir
        # le panneau ne doit pas couter trente ecritures.
        #
        # `updated_at` est pose a la main : `auto_now` ne se declenche que sur
        # `save()`, jamais sur un `update()` en masse.
        maintenant = timezone.now()
        touchees = lignes.update(lu_le=maintenant, updated_at=maintenant)
        return Response({"marquees": touchees})


class NotificationView(_BoiteMixin, APIView):
    """La boite d'une personne, dans un salon."""

    permission_classes = [IsAuthenticated, IsTenantResolved]
    serializer_class = NotificationSerializer
    model = Notification

    def lignes(self, request):
        # `objects` filtre deja sur le tenant du contexte ; le filtre sur le
        # destinataire est ce qui separe deux gerantes du meme salon.
        return Notification.objects.filter(recipient=request.user)


class PlatformNotificationView(_BoiteMixin, APIView):
    """La boite de l'equipe de la plateforme."""

    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    serializer_class = PlatformNotificationSerializer
    model = PlatformNotification

    def lignes(self, request):
        return PlatformNotification.objects.filter(
            recipient=request.user
        ).select_related("tenant")


class PushView(APIView):
    """L'inscription d'un appareil, et son retrait.

    -----------------------------------------------------------------------
    Pourquoi la portee n'est pas simplement deduite
    -----------------------------------------------------------------------

    Le tableau de bord et l'administration sont deux sites distincts pour le
    navigateur, mais ils s'adressent au meme serveur : rien dans la requete
    ne dit lequel appelle de facon fiable — un en-tete `Origin` se forge.

    Le client declare donc sa portee, et le serveur verifie la seule qui
    accorde quelque chose : reclamer la portee « plateforme » exige d'etre
    administrateur. Reclamer « salon » sans l'etre n'ouvre rien, puisque les
    notifications de salon ne partent qu'aux membres du salon concerne.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """La cle publique, et les appareils deja inscrits pour ce compte."""
        if not push.configure():
            return Response({"actif": False, "cle": "", "appareils": []})

        # L'adresse de remise figure dans la reponse, et c'est voulu : elle
        # permet au navigateur de reconnaitre **le sien** parmi ceux du
        # compte. Sans elle, un appareil dont la ligne a disparu cote serveur
        # se croirait inscrit et n'aurait jamais rien recu.
        #
        # Elle n'apprend rien a celui qui la lit : c'est son propre navigateur
        # qui la lui a donnee. Les cles, elles, ne ressortent jamais — sans
        # elles, on ne peut chiffrer aucun message.
        appareils = [
            {
                "id": str(abonnement.pk),
                "endpoint": abonnement.endpoint,
                "appareil": abonnement.appareil,
                "portee": abonnement.portee,
                "depuis": abonnement.created_at,
            }
            for abonnement in PushSubscription.objects.filter(user=request.user)
        ]
        return Response(
            {"actif": True, "cle": push.cle_publique(), "appareils": appareils}
        )

    def post(self, request):
        serializer = AbonnementSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        donnees = serializer.validated_data

        if (
            donnees["portee"] == PushSubscription.Portee.PLATEFORME
            and not request.user.is_platform_admin
        ):
            return Response(
                {"detail": "Réservé aux administrateurs de la plateforme."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # `update_or_create` sur l'endpoint : il designe un navigateur, pas
        # un compte. Sur un poste partage a l'accueil, la derniere personne
        # qui accepte reprend l'abonnement a son nom — et l'ancienne cesse
        # d'y recevoir ses notifications, ce qui est le sens le plus sur.
        abonnement, cree = PushSubscription.objects.update_or_create(
            endpoint=donnees["endpoint"],
            defaults={
                "user": request.user,
                "cle_p256dh": donnees["cle_p256dh"],
                "cle_auth": donnees["cle_auth"],
                "appareil": donnees.get("appareil", ""),
                "portee": donnees["portee"],
                "echecs": 0,
            },
        )
        return Response(
            {"id": str(abonnement.pk), "cree": cree},
            status=status.HTTP_201_CREATED if cree else status.HTTP_200_OK,
        )

    def delete(self, request):
        """Retire un appareil.

        Filtre sur le compte en plus de l'adresse : sans cela, connaitre
        l'adresse de remise de quelqu'un suffirait a le priver de ses
        notifications.
        """
        endpoint = request.data.get("endpoint") or ""
        if not endpoint:
            return Response(
                {"detail": "`endpoint` est requis."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        supprimes, _ = PushSubscription.objects.filter(
            user=request.user, endpoint=endpoint
        ).delete()
        return Response({"supprimes": supprimes})
