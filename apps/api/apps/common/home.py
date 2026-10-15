"""Catalogue public de la plateforme : uniquement les champs commerciaux publiables."""

from django.db.models import F
from django.utils import timezone
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.billing.models import ProCapability
from apps.billing.services import REFERRED_TRIAL_DAYS, TRIAL_DAYS, catalogue_de_paiement
from apps.tenants.models import Tenant

from .db import tenant_context
from .models import HomeMetric, HomeReference, HomeSettings

EVENTS = frozenset(
    {
        "home_view",
        "create_click",
        "preview_used",
        "demo_completed",
        "pricing_view",
        "signup_started",
        "signup_completed",
        "email_verified",
        "salon_published",
        "first_booking",
    }
)


def count_event(event, language="xx", using="default"):
    metric, _ = HomeMetric.objects.using(using).get_or_create(
        day=timezone.localdate(), event=event, language=language
    )
    HomeMetric.objects.using(using).filter(pk=metric.pk).update(count=F("count") + 1)


class HomeView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "public_read"

    def get(self, request):
        language = "en" if request.query_params.get("lang") == "en" else "fr"
        countries = []
        for country in catalogue_de_paiement():
            countries.append(
                {
                    "code": country["code"],
                    "name": country["nom"],
                    "currencies": [
                        {
                            "code": currency["code"],
                            "plans": [
                                {
                                    "code": item["plan"].code,
                                    "group": item["plan"].group,
                                    "months": item["plan"].billing_months,
                                    "amount": str(item["montant"]),
                                    "max_staff": item["plan"].max_staff,
                                }
                                for item in currency["plans"]
                            ],
                            # Les coordonnées, QR codes et secrets de paiement restent privés.
                            "kkiapay": any(
                                method.kind == "kkiapay" for method in currency["moyens"]
                            ),
                            "saspay": any(
                                method.kind == "saspay" for method in currency["moyens"]
                            ),
                            # « mobile_money », « carte », « mobile_money_carte » ou vide.
                            "channel": currency["canal"],
                        }
                        for currency in country["devises"]
                    ],
                }
            )
        references = []
        for reference in HomeReference.objects.filter(
            active=True, consent=True, verified=True, tenant__status=Tenant.Status.ACTIVE
        ).select_related("tenant")[:6]:
            from apps.salons.models import SalonProfile

            with tenant_context(reference.tenant_id):
                if not SalonProfile.objects.filter(tenant_id=reference.tenant_id).exists():
                    continue
            references.append(
                {
                    "salon": reference.tenant.name,
                    "slug": reference.tenant.slug,
                    "country": reference.tenant.country,
                    "author": reference.author,
                    "quote": getattr(reference, f"quote_{language}"),
                    "portrait": reference.portrait
                    if reference.portrait.startswith("https://")
                    else "",
                    "showcase": reference.showcase,
                }
            )
        contact = HomeSettings.objects.first()
        response = Response(
            {
                "trial_days": TRIAL_DAYS,
                "referred_trial_days": REFERRED_TRIAL_DAYS,
                "supported_countries": [
                    {"code": code, "name": str(name)} for code, name in Tenant.Country.choices
                ],
                "countries": countries,
                "pro_features": list(
                    ProCapability.objects.filter(active=True).values_list("code", flat=True)
                ),
                "references": references,
                "support": {
                    "email": contact.support_email if contact else "",
                    "whatsapp": contact.support_whatsapp if contact else "",
                },
            }
        )
        response["Cache-Control"] = "public, max-age=60"
        return response


class HomeMetricView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "home_metric"

    def post(self, request):
        # Compteurs journaliers sans adresse IP, compte, cookie ni nom de salon stockés.
        if not isinstance(request.data, dict):
            return Response({"detail": "Événement invalide."}, status=400)
        event = request.data.get("event")
        language = request.data.get("language", "fr")
        if not isinstance(event, str) or event not in EVENTS or language not in ("fr", "en"):
            return Response({"detail": "Événement invalide."}, status=400)
        # Les étapes confirmées sont comptées côté serveur, jamais sur déclaration publique.
        if event in {"signup_completed", "email_verified", "salon_published", "first_booking"}:
            return Response({"detail": "Événement réservé."}, status=400)
        count_event(event, language)
        return Response(status=204)


class HomeSessionView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        from apps.accounts.serializers import UserSerializer

        response = Response(
            UserSerializer(request.user).data if request.user.is_authenticated else None
        )
        response["Cache-Control"] = "private, no-store"
        return response
