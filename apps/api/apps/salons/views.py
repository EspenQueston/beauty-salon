"""Vitrine publique : lecture seule, sans authentification."""

from django.shortcuts import get_object_or_404
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.models import Service, ServiceCategory, ServiceOption
from apps.common.permissions import IsTenantResolved
from apps.media.models import MediaAsset
from apps.media.reserved import duplicate_media_ids, reserved_media_ids
from apps.scheduling.models import BusinessHours
from apps.staff.models import StaffMember, StaffService
from apps.tenants.models import Tenant
from apps.translations.langue import table_pour

from .models import SalonProfile, TravelZone
from .serializers import PublicSalonSerializer


class PublicSalonView(APIView):
    """Tout le contenu du mini-site en une reponse.

    Le tenant vient du hostname, resolu par TenantContextMiddleware ; aucun
    identifiant de salon ne circule dans l'URL.
    """

    permission_classes = [AllowAny, IsTenantResolved]
    throttle_scope = "public_read"

    def get(self, request):
        tenant = get_object_or_404(Tenant, pk=request.tenant_id)

        if tenant.status == Tenant.Status.SUSPENDED:
            return Response(
                {"detail": "Ce salon est momentanément indisponible.", "code": "suspended"},
                status=503,
            )

        # Un salon inscrit mais pas encore valide par l'equipe plateforme ne
        # publie rien. Sans ce controle, n'importe qui pourrait mettre en
        # ligne une page sous le domaine en s'inscrivant.
        if tenant.status != Tenant.Status.ACTIVE:
            return Response(
                {"detail": "Ce salon n'est pas encore en ligne.", "code": "not_published"},
                status=404,
            )

        profile = (
            SalonProfile.objects.filter(tenant=tenant)
            # Trois images sur la fiche : sans jointure, c'est trois requetes
            # de plus sur chaque affichage de mini-site.
            .select_related("logo", "banner", "about_image")
            .first()
        )
        if profile is None:
            # Le salon existe mais n'a pas encore ete configure.
            return Response(
                {"detail": "Ce salon n'est pas encore en ligne.", "code": "not_published"},
                status=404,
            )

        traductions = table_pour(request, profile.tenant_id)

        def traduit(objet, champ):
            return traductions.get(
                (objet._meta.label_lower, str(objet.pk), champ)
            ) or getattr(objet, champ)

        services = list(
            Service.objects.filter(active=True)
            .select_related("image")
            .order_by("position", "name")
        )
        categories = list(
            ServiceCategory.objects.filter(active=True).order_by("position", "name")
        )

        services_by_category: dict = {}
        for service in services:
            services_by_category.setdefault(service.category_id, []).append(service)

        # Fournitures a prevoir, et ce que la boutique propose pour chacune.
        #
        # Deux requetes en tout, quel que soit le nombre de prestations. Les
        # articles en rupture sont conserves et marques indisponibles :
        # les faire disparaitre laisserait croire que le salon n'en vend pas.
        from apps.store.models import Requirement

        requirements_by_service: dict = {}
        for requirement in (
            Requirement.objects.all()
            .prefetch_related("offers__product__image")
            .order_by("position", "id")
        ):
            requirements_by_service.setdefault(requirement.service_id, []).append(
                {
                    "id": str(requirement.id),
                    "label": traduit(requirement, "label"),
                    "detail": traduit(requirement, "detail"),
                    "mandatory": requirement.mandatory,
                    "products": [
                        {
                            "id": str(offer.product.id),
                            "name": traduit(offer.product, "name"),
                            "description": traduit(offer.product, "description"),
                            "price": str(offer.product.price),
                            "unit": offer.product.unit,
                            "available": offer.product.available,
                            "image": (
                                request.build_absolute_uri(offer.product.image.file.url)
                                if offer.product.image_id and offer.product.image
                                else ""
                            ),
                            # Une video ne se rend pas dans une balise <img> :
                            # le mini-site a besoin de savoir laquelle poser.
                            "image_type": (
                                offer.product.image.content_type
                                if offer.product.image_id and offer.product.image
                                else ""
                            ),
                        }
                        for offer in requirement.offers.all()
                        if offer.product.active
                    ],
                }
            )

        # Une seule requete pour toutes les options, plutot qu'une par
        # prestation dans le serializer.
        options_by_service: dict = {}
        for option in ServiceOption.objects.filter(active=True).order_by(
            "position", "name"
        ):
            options_by_service.setdefault(option.service_id, []).append(option)

        # Une seule requete pour toutes les competences, plutot qu'une par
        # prestation dans le serializer.
        staff_by_service: dict = {}
        for service_id, staff_id in StaffService.objects.values_list(
            "service_id", "staff_member_id"
        ):
            staff_by_service.setdefault(service_id, []).append(staff_id)

        context = {
            "request": request,
            "categories": [c for c in categories if services_by_category.get(c.id)],
            "services_by_category": services_by_category,
            "options_by_service": options_by_service,
            "requirements_by_service": requirements_by_service,
            "staff_by_service": staff_by_service,
            "staff_members": list(
                StaffMember.objects.filter(active=True)
                .select_related("photo")
                .order_by("position", "name")
            ),
            "business_hours": list(
                BusinessHours.objects.filter(staff_member__isnull=True).order_by(
                    "weekday", "starts_at"
                )
            ),
            # Tout ce qui a un emploi ailleurs sort de la galerie : logo,
            # banniere, photo de la page « A propos », QR codes de paiement,
            # photos d'articles. Ils partagent la meme reserve que les
            # realisations parce que le selecteur de medias est commun, et
            # ils se retrouvaient sinon au milieu des coiffures.
            #
            # La liste est deduite des cles etrangeres vers MediaAsset, pas
            # ecrite a la main : une liste manuelle s'est deja perimee deux
            # fois, au logo puis aux QR codes. Voir `media/reserved.py`.
            "gallery": _gallery(),
            # Seules les zones actives : une zone desactivee reste en base
            # pour l'historique du salon, mais n'est plus proposee.
            "travel_zones": list(
                TravelZone.objects.filter(active=True).order_by("position", "name")
            ),
            "rating": _rating_summary(),
            # Toutes les traductions du salon, en une requete.
            #
            # Une par champ aurait ajoute une requete par prestation, sur la
            # page qui doit s ouvrir le plus vite du produit. Vide quand la
            # langue demandee est le francais : il n y a alors rien a
            # remplacer, et la requete serait perdue.
            "traductions": traductions,
        }

        return Response(PublicSalonSerializer(profile, context=context).data)


def _gallery() -> list:
    """Les realisations publiees du salon, et rien d'autre.

    Trois filtres, et chacun a coute un signalement :

      1. **Le genre.** Seules les images televersees *comme* realisations.
         Tout televersement etait autrefois etiquete « galerie » par defaut,
         quel que soit l'ecran d'origine - c'est ainsi que des QR codes de
         paiement se sont retrouves entre deux coiffures.
      2. **L'emploi ailleurs.** Une image rattachee a un logo, une banniere,
         un QR code, un article : elle a deja un role. Voir
         `media/reserved.py`, qui le deduit des cles etrangeres plutot que
         d'une liste ecrite a la main.
      3. **Les doublons.** Le selecteur televerse a chaque choix : essayer
         deux fichiers laisse deux copies. La meme photo deux fois dans une
         mosaique se lit comme un bug.

    Les medias deja employes sont passes en tete au detecteur de doublons :
    c'est ce qui permet d'ecarter le second exemplaire d'un QR code dont le
    premier sert reellement de moyen de paiement.
    """
    reserves = reserved_media_ids()

    candidats = list(
        MediaAsset.objects.filter(
            kind=MediaAsset.Kind.GALLERY,
            visibility=MediaAsset.Visibility.PUBLIC,
        ).order_by("position", "-created_at")[:60]
    )
    employes = list(MediaAsset.objects.filter(id__in=reserves))

    doublons = duplicate_media_ids([*employes, *candidats])

    return [
        asset
        for asset in candidats
        if asset.id not in reserves and asset.id not in doublons
    ]


def _rating_summary() -> dict:
    """Moyenne et volume des avis publies du salon courant.

    Le calcul est fait par la base : additionner les notes cote client
    donnerait un chiffre different selon le nombre d'avis charges.
    """
    from django.db.models import Avg, Count

    from apps.reviews.models import Review

    summary = Review.objects.filter(status=Review.Status.PUBLISHED).aggregate(
        average=Avg("rating"), count=Count("id")
    )
    average = summary["average"]
    return {
        "average": round(average, 1) if average is not None else None,
        "count": summary["count"],
    }
