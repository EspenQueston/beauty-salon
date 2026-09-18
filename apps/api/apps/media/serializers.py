from django.urls import reverse
from rest_framework import serializers

from .models import ALLOWED_IMAGE_TYPES, ALLOWED_VIDEO_TYPES, MAX_UPLOAD_BYTES, MediaAsset


def media_url(asset, request=None) -> str:
    """L'adresse a laquelle ce media se lit.

    Deux chemins, et c'est la visibilite qui tranche :

      - **public** : l'adresse du fichier, servie par le serveur de fichiers
        statiques. C'est le cas de tout ce qui habille un mini-site.
      - **prive** : la route authentifiee. Le fichier vit sous `prive/`, que
        le serveur statique ne sert pas ; il ne sort que par une requete
        portant la session d'un membre du salon.

    Une seule fonction pour les deux, appelee partout ou une adresse de
    media est produite. Recalculer `asset.file.url` a la main quelque part,
    c'est rouvrir le trou a cet endroit-la sans que rien ne le signale.
    """
    if not asset or not asset.file:
        return ""

    if asset.visibility == MediaAsset.Visibility.PRIVATE:
        chemin = reverse("media-fichier", kwargs={"pk": asset.pk})
    else:
        chemin = asset.file.url

    return request.build_absolute_uri(chemin) if request else chemin


class MediaAssetSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = MediaAsset
        fields = (
            "id",
            "file",
            "url",
            "content_type",
            "byte_size",
            "kind",
            "visibility",
            "alt_text",
            "width",
            "height",
            "position",
            "featured",
            "created_at",
        )
        read_only_fields = ("content_type", "byte_size", "width", "height")
        extra_kwargs = {"file": {"write_only": True}}

    def get_url(self, asset) -> str:
        return media_url(asset, self.context.get("request"))

    def validate_file(self, uploaded):
        """Le type declare par le navigateur ne suffit pas, mais il elimine
        deja l'essentiel ; la verification du contenu reel a lieu ensuite,
        dans la tache de generation des derives."""
        if uploaded.size > MAX_UPLOAD_BYTES:
            limit_mb = MAX_UPLOAD_BYTES // (1024 * 1024)
            raise serializers.ValidationError(f"Fichier trop volumineux (max {limit_mb} Mo).")

        content_type = (uploaded.content_type or "").lower()
        if content_type not in ALLOWED_IMAGE_TYPES | ALLOWED_VIDEO_TYPES:
            raise serializers.ValidationError(
                "Format non accepté. Images JPEG, PNG, WebP ou vidéos MP4, WebM."
            )
        return uploaded

    def create(self, validated_data):
        uploaded = validated_data["file"]
        validated_data["content_type"] = (uploaded.content_type or "").lower()
        validated_data["byte_size"] = uploaded.size
        return super().create(validated_data)
