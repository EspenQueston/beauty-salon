from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Membership
from apps.common.permissions import HasTenantRole, IsTenantMember
from apps.common.viewsets import TenantModelViewSet

from .fetch import RemoteMediaError, fetch_remote_media
from .models import MediaAsset
from .serializers import MediaAssetSerializer


class RemoteMediaSerializer(serializers.Serializer):
    url = serializers.URLField(max_length=2000)
    kind = serializers.ChoiceField(choices=MediaAsset.Kind.choices, default=MediaAsset.Kind.GALLERY)
    alt_text = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


MANAGERS = (Membership.Role.OWNER, Membership.Role.MANAGER)
EVERYONE = (*MANAGERS, Membership.Role.RECEPTIONIST, Membership.Role.STAFF)


class MediaAssetViewSet(TenantModelViewSet):
    serializer_class = MediaAssetSerializer
    model = MediaAsset
    # Le televersement arrive en multipart ; la description et l'ordre
    # d'affichage se modifient ensuite en JSON. Sans JSONParser, ces
    # modifications repartaient en « Type de media non supporte » et la
    # legende saisie n'etait jamais enregistree.
    parser_classes = (MultiPartParser, FormParser, JSONParser)
    required_roles = MANAGERS
    safe_roles = EVERYONE

    def get_queryset(self):
        # Les preuves de versement n'entrent jamais dans la mediatheque : ni
        # listees, ni modifiables, ni supprimables par cette route. Elles ont
        # leurs propres chemins (l'acompte au rendez-vous, l'abonnement a la
        # page Abonnement), avec leurs propres droits. Supprimer une preuve
        # ici effacait la piece qu'un administrateur doit verifier.
        queryset = super().get_queryset().exclude(kind=MediaAsset.Kind.PROOF)
        if kind := self.request.query_params.get("kind"):
            queryset = queryset.filter(kind=kind)
        return queryset

    def perform_create(self, serializer):
        asset = serializer.save(tenant_id=self.request.tenant_id)
        # Dimensions et derives WebP sont calcules hors requete : un upload
        # depuis un mobile sur reseau lent ne doit pas attendre le
        # redimensionnement.
        from .tasks import process_media_asset

        process_media_asset.delay(str(asset.id), str(self.request.tenant_id))

    @action(detail=False, methods=["post"], url_path="from-url")
    def from_url(self, request):
        """Importe une photo ou une video depuis une adresse web.

        Le geste vise est celui-ci : le salon trouve une image sur Pexels ou
        Unsplash, copie son adresse, la colle. Sans cette route, il devait
        telecharger le fichier puis le reteleverser - deux etapes de plus sur
        un telephone, la ou tout se joue.

        Le fichier est recopie chez nous plutot que pointe a distance : le
        mini-site ne doit pas dependre d'un serveur tiers pour s'afficher.
        Les protections contre les adresses internes vivent dans `fetch.py`.
        """
        payload = RemoteMediaSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        try:
            content, content_type = fetch_remote_media(data["url"])
        except RemoteMediaError as exc:
            return Response(
                {"detail": str(exc), "code": "remote_media_refused"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        asset = MediaAsset.objects.create(
            tenant_id=request.tenant_id,
            file=content,
            content_type=content_type,
            byte_size=content.size,
            kind=data["kind"],
            alt_text=data.get("alt_text", ""),
        )

        from .tasks import process_media_asset

        process_media_asset.delay(str(asset.id), str(request.tenant_id))

        return Response(
            MediaAssetSerializer(asset, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class PrivateMediaView(APIView):
    """Sert un fichier prive, apres verification de l'appartenance au salon.

    -----------------------------------------------------------------------
    Ce qu'elle repare
    -----------------------------------------------------------------------

    Une preuve de versement - une capture d'ecran de paiement, portant le nom
    de la cliente et parfois son solde bancaire - etait rangee en
    `visibility=private`. Ce drapeau la tenait hors de la vitrine publique et
    hors de la mediatheque du salon, mais **le fichier lui-meme restait servi
    a une adresse publique**. Sa seule protection etait l'imprevisibilite de
    deux UUID.

    244 bits ne se devinent pas. Mais une adresse se partage, se copie dans
    une conversation, se retrouve dans le journal d'un proxy ou dans un
    en-tete `Referer`. Le jour ou elle sort, elle sort pour toujours : rien
    ne permet de la revoquer.

    Ici, chaque lecture est verifiee. Le fichier vit sous `prive/`, que le
    serveur de fichiers statiques ne sert pas.

    -----------------------------------------------------------------------
    Pourquoi 404 et non 403 quand le salon ne correspond pas
    -----------------------------------------------------------------------

    `MediaAsset.objects` est filtre sur le salon courant, et les politiques
    RLS le sont aussi : l'objet d'un autre salon n'existe tout simplement
    pas pour cette requete. Repondre 403 reviendrait a confirmer qu'un
    media porte bien cet identifiant ailleurs sur la plateforme - une
    reponse a une question qu'on n'a pas a traiter.
    """

    permission_classes = [IsTenantMember, HasTenantRole]
    # Toute l'equipe peut lire : la reception encaisse au comptoir et doit
    # pouvoir retrouver un versement. Personne n'ecrit par cette route.
    safe_roles = EVERYONE
    required_roles = EVERYONE

    def get(self, request, pk):
        asset = get_object_or_404(MediaAsset.objects.all(), pk=pk)

        # Exception : la preuve d'un paiement d'abonnement. Elle montre ce que
        # le proprietaire a verse a la plateforme, parfois son solde, et la
        # facturation lui est reservee partout ailleurs. Meme reponse qu'un
        # media inexistant, pour la raison dite plus haut.
        if asset.kind == MediaAsset.Kind.PROOF:
            from apps.billing.models import SubscriptionPaymentRequest

            membership = getattr(request, "membership", None)
            proprietaire = membership is not None and membership.role == Membership.Role.OWNER
            if not proprietaire and SubscriptionPaymentRequest.objects.filter(proof=asset).exists():
                raise Http404

        try:
            fichier = asset.file.open("rb")
        except (FileNotFoundError, ValueError, OSError) as exc:
            # Le fichier a disparu du stockage alors que la ligne existe
            # encore. On ne renvoie pas la trace : elle contiendrait le
            # chemin sur disque.
            raise Http404("Fichier introuvable.") from exc

        reponse = FileResponse(
            fichier,
            content_type=asset.content_type or "application/octet-stream",
        )
        # `inline` : la capture s'affiche dans la page du rendez-vous, on ne
        # la telecharge pas. Le nom est celui du fichier d'origine.
        nom = asset.file.name.rsplit("/", 1)[-1]
        reponse["Content-Disposition"] = f'inline; filename="{nom}"'
        # Le navigateur s'en tient au type declare : une image qui
        # contiendrait du HTML ne sera jamais interpretee comme une page.
        reponse["X-Content-Type-Options"] = "nosniff"
        # Ouvert seul dans un onglet, le fichier est un document sans script,
        # quoi qu'il contienne : il est servi sur le domaine de la session.
        reponse["Content-Security-Policy"] = (
            "default-src 'none'; style-src 'unsafe-inline'; sandbox"
        )
        # Jamais de cache partage : ce fichier n'appartient qu'a ce salon, et
        # un proxy intermediaire ne doit pas pouvoir le resservir a un autre.
        reponse["Cache-Control"] = "private, max-age=0, no-store"
        return reponse
