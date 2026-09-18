"""Traitement des medias apres upload.

C'est aussi le moment ou l'on verifie que le fichier est bien ce qu'il
pretend etre : le Content-Type envoye par le navigateur est declaratif, un
fichier renomme en .jpg passerait la validation du serializer. Pillow, lui,
echoue a ouvrir ce qui n'est pas une image.
"""

import logging

from celery import shared_task
from django.core.files.base import ContentFile

from apps.common.db import tenant_context

logger = logging.getLogger(__name__)

# Largeurs generees pour la galerie du mini-site.
DERIVATIVE_WIDTHS = {"sm": 480, "md": 1024}
WEBP_QUALITY = 82


@shared_task
def process_media_asset(asset_id: str, tenant_id: str):
    from PIL import Image, UnidentifiedImageError

    from .models import MediaAsset

    with tenant_context(tenant_id):
        asset = MediaAsset.objects.filter(id=asset_id).first()
        if asset is None:
            return

        if not asset.content_type.startswith("image/"):
            return  # les videos ne sont pas retaillees pour l'instant

        try:
            with Image.open(asset.file) as image:
                image.load()
                asset.width, asset.height = image.size
                derivatives = {}

                for label, width in DERIVATIVE_WIDTHS.items():
                    if image.width <= width:
                        continue
                    derivatives[label] = _write_derivative(asset, image, label, width)

                asset.derivatives = derivatives
                asset.save(update_fields=["width", "height", "derivatives", "updated_at"])
        except UnidentifiedImageError:
            # Fichier corrompu ou deguise : on le supprime plutot que de le
            # laisser servir tel quel depuis le mini-site.
            logger.warning("Media %s illisible, supprime.", asset_id)
            asset.file.delete(save=False)
            asset.delete()


def _write_derivative(asset, image, label: str, width: int) -> str:
    from io import BytesIO

    from PIL import Image

    ratio = width / image.width
    resized = image.convert("RGB").resize(
        (width, round(image.height * ratio)), Image.LANCZOS
    )

    buffer = BytesIO()
    resized.save(buffer, format="WEBP", quality=WEBP_QUALITY)

    name = f"tenants/{asset.tenant_id}/media/{asset.id}/{label}.webp"
    asset.file.storage.save(name, ContentFile(buffer.getvalue()))
    return name
