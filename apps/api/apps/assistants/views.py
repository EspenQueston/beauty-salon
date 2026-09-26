"""Les assistants IA, cote API (offre Pro).

Chaque route verifie la fonction Pro cote serveur (`ExigeFonctionPro`) : un
salon Standard recoit 403 « offre_pro_requise », quoi que montre l'ecran.
"""

from __future__ import annotations

import logging
import secrets

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Membership
from apps.billing.droits import ExigeFonctionPro, fonctions_du_salon
from apps.common.permissions import HasTenantRole, IsTenantMember, IsTenantResolved
from apps.tenants.models import Tenant

from . import evolution, ia, whatsapp
from .models import AssistantReglages

logger = logging.getLogger(__name__)

DIRECTION = (Membership.Role.OWNER, Membership.Role.MANAGER)
PROPRIETAIRE = (Membership.Role.OWNER,)
QUOTA_PUBLIC_JOUR = 300
INDISPONIBLE = "L'assistant est momentanément indisponible. Réessayez dans un instant."
QUOTA_ATTEINT = "L'assistant a beaucoup répondu aujourd'hui : contactez le salon directement."


def _reglages(tenant_id) -> AssistantReglages:
    reglages, _ = AssistantReglages.objects.get_or_create(tenant_id=tenant_id)
    return reglages


def _repli(tenant_id) -> dict:
    """Ou joindre le salon quand l'assistant ne peut pas repondre."""
    from apps.salons.models import SalonProfile

    profil = SalonProfile.objects.filter(tenant_id=tenant_id).first()
    return {
        "whatsapp": getattr(profil, "whatsapp_number", ""),
        "telephone": getattr(profil, "phone", ""),
        "email": getattr(profil, "contact_email", ""),
    }


def _journaliser(request, geste: str, **extra) -> None:
    from apps.audit.models import AuditLog

    AuditLog.objects.create(
        tenant_id=request.tenant_id,
        actor_user=request.user if request.user.is_authenticated else None,
        action=AuditLog.Action.ASSISTANT_SETTINGS_CHANGED,
        resource_type="assistant",
        metadata={"geste": geste, **extra},
    )


# ---------------------------------------------------------------------------
# Assistant de l'espace pro
# ---------------------------------------------------------------------------


class AssistantPlateformeView(APIView):
    permission_classes = [IsTenantMember, ExigeFonctionPro]
    fonction_pro = "platform_assistant"
    throttle_scope = "assistant"

    def post(self, request):
        try:
            messages = ia.nettoyer_messages(request.data.get("messages"))
        except ValueError as erreur:
            return Response({"detail": str(erreur), "code": "conversation_invalide"}, status=400)
        tenant = Tenant.objects.get(pk=request.tenant_id)
        contexte = ia.contexte_plateforme(tenant, request.membership)
        try:
            reponse = ia.SERVICE.repondre(
                ia.SYSTEME_PLATEFORME.format(salon=tenant.name), contexte, messages
            )
        except ia.IAIndisponible:
            return Response(
                {
                    "detail": INDISPONIBLE,
                    "code": "assistant_indisponible",
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({"reponse": reponse})


# ---------------------------------------------------------------------------
# Assistant des clientes, sur le mini-site
# ---------------------------------------------------------------------------


class AssistantPublicView(APIView):
    """Toujours joignable ; quand il ne peut pas repondre, il dit qui joindre."""

    permission_classes = [AllowAny, IsTenantResolved, ExigeFonctionPro]
    fonction_pro = "customer_assistant"
    throttle_scope = "assistant_public"

    def post(self, request):
        reglages = _reglages(request.tenant_id)
        repli = _repli(request.tenant_id)
        if not reglages.clientes_actif:
            return Response(
                {
                    "detail": "L'assistant n'est pas activé.",
                    "code": "assistant_inactif",
                    "repli": repli,
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        try:
            messages = ia.nettoyer_messages(request.data.get("messages"))
        except ValueError as erreur:
            return Response({"detail": str(erreur), "code": "conversation_invalide"}, status=400)

        # Plafond par salon et par jour, en plus de la limite par visiteur :
        # un robot qui change d'adresse ne vide pas le budget du salon.
        jour = f"assistant:quota:{request.tenant_id}:{timezone.localdate()}"
        cache.add(jour, 0, 26 * 3600)
        if cache.incr(jour) > QUOTA_PUBLIC_JOUR:
            return Response(
                {
                    "detail": QUOTA_ATTEINT,
                    "code": "quota_atteint",
                    "repli": repli,
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        tenant = Tenant.objects.get(pk=request.tenant_id)
        try:
            reponse = ia.SERVICE.repondre(
                ia.SYSTEME_CLIENTES.format(salon=tenant.name), ia.contexte_public(tenant), messages
            )
        except ia.IAIndisponible:
            return Response(
                {
                    "detail": "L'assistant ne peut pas répondre pour le moment.",
                    "code": "assistant_indisponible",
                    "repli": repli,
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({"reponse": reponse, "repli": repli})


# ---------------------------------------------------------------------------
# Reglages, et WhatsApp
# ---------------------------------------------------------------------------


def _etat(tenant_id) -> dict:
    reglages = _reglages(tenant_id)
    fonctions = fonctions_du_salon(tenant_id)
    return {
        "fonctions": {
            "plateforme": fonctions["platform_assistant"],
            "clientes": fonctions["customer_assistant"],
            "whatsapp": fonctions["whatsapp_assistant"],
        },
        "ia_configuree": ia.SERVICE.disponible(),
        "clientes_actif": reglages.clientes_actif,
        "whatsapp": {
            "configuree": evolution.configuree(),
            "statut": reglages.whatsapp_statut,
            "numero": reglages.whatsapp_numero,
            "actif": reglages.whatsapp_actif,
            "derniere_activite": reglages.whatsapp_derniere_activite,
        },
    }


class ReglagesAssistantView(APIView):
    """GET : l'etat des trois assistants. PATCH : les interrupteurs."""

    permission_classes = [IsTenantMember, HasTenantRole]
    required_roles = DIRECTION
    safe_roles = DIRECTION

    def get(self, request):
        return Response(_etat(request.tenant_id))

    def patch(self, request):
        fonctions = fonctions_du_salon(request.tenant_id)
        reglages = _reglages(request.tenant_id)
        champs = []
        if "clientes_actif" in request.data:
            if not fonctions["customer_assistant"]:
                return Response(
                    {
                        "detail": "Cette fonction fait partie de l'offre Pro.",
                        "code": "offre_pro_requise",
                    },
                    status=403,
                )
            reglages.clientes_actif = bool(request.data["clientes_actif"])
            champs.append("clientes_actif")
        if "whatsapp_actif" in request.data:
            if not fonctions["whatsapp_assistant"]:
                return Response(
                    {
                        "detail": "Cette fonction fait partie de l'offre Pro.",
                        "code": "offre_pro_requise",
                    },
                    status=403,
                )
            reglages.whatsapp_actif = bool(request.data["whatsapp_actif"])
            champs.append("whatsapp_actif")
        if champs:
            reglages.save(update_fields=[*champs, "updated_at"])
            _journaliser(request, "interrupteurs", **{c: getattr(reglages, c) for c in champs})
        return Response(_etat(request.tenant_id))


class WhatsAppConnexionView(APIView):
    """POST : creer l'instance et obtenir le QR code. GET : rafraichir. DELETE : deconnecter."""

    permission_classes = [IsTenantMember, HasTenantRole, ExigeFonctionPro]
    required_roles = PROPRIETAIRE
    safe_roles = PROPRIETAIRE
    fonction_pro = "whatsapp_assistant"

    def _indisponible(self):
        return Response(
            {
                "detail": "La passerelle WhatsApp n'est pas configurée sur la plateforme.",
                "code": "whatsapp_non_configure",
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    def post(self, request):
        if not evolution.configuree():
            return self._indisponible()
        tenant = Tenant.objects.get(pk=request.tenant_id)
        with transaction.atomic():
            reglages = AssistantReglages.objects.select_for_update().get(pk=_reglages(tenant.id).pk)
            if not reglages.whatsapp_instance:
                jeton = secrets.token_urlsafe(32)
                instance = f"bs-{tenant.slug}"[:40] + f"-{secrets.token_hex(3)}"
                base = settings.API_BASE_URL.rstrip("/")
                webhook = f"{base}/api/v1/webhooks/whatsapp/{instance}/{jeton}"
                try:
                    evolution.creer_instance(instance, webhook)
                except evolution.EvolutionIndisponible as erreur:
                    return Response({"detail": str(erreur), "code": "whatsapp_erreur"}, status=502)
                reglages.whatsapp_instance = instance
                reglages.whatsapp_empreinte = whatsapp.empreinte(jeton)
                reglages.whatsapp_statut = AssistantReglages.StatutWhatsApp.EN_ATTENTE
                reglages.save()
                _journaliser(request, "whatsapp_connexion", instance=instance)
        return self.get(request)

    def get(self, request):
        if not evolution.configuree():
            return self._indisponible()
        reglages = _reglages(request.tenant_id)
        if not reglages.whatsapp_instance:
            return Response({"qr": "", **_etat(request.tenant_id)})
        qr = ""
        try:
            etat = evolution.etat(reglages.whatsapp_instance)
            if etat == "open":
                reglages.whatsapp_statut = AssistantReglages.StatutWhatsApp.CONNECTE
            else:
                qr = evolution.qr_code(reglages.whatsapp_instance)
                reglages.whatsapp_statut = AssistantReglages.StatutWhatsApp.EN_ATTENTE
            reglages.save(update_fields=["whatsapp_statut", "updated_at"])
        except evolution.EvolutionIndisponible as erreur:
            return Response({"detail": str(erreur), "code": "whatsapp_erreur"}, status=502)
        return Response({"qr": qr, **_etat(request.tenant_id)})

    def delete(self, request):
        reglages = _reglages(request.tenant_id)
        if reglages.whatsapp_instance:
            if evolution.configuree():
                evolution.supprimer(reglages.whatsapp_instance)
            _journaliser(request, "whatsapp_deconnexion", instance=reglages.whatsapp_instance)
        reglages.whatsapp_instance = ""
        reglages.whatsapp_empreinte = ""
        reglages.whatsapp_statut = AssistantReglages.StatutWhatsApp.AUCUN
        reglages.whatsapp_actif = False
        reglages.whatsapp_numero = ""
        reglages.save()
        return Response(_etat(request.tenant_id))


class WebhookWhatsAppView(APIView):
    """Les evenements d'Evolution. Authentifies par le jeton de l'adresse."""

    authentication_classes: list = []
    permission_classes = [AllowAny]

    def post(self, request, instance: str, jeton: str):
        try:
            resultat = whatsapp.traiter(
                instance, jeton, request.data if isinstance(request.data, dict) else {}
            )
        except whatsapp.WebhookRefuse:
            # Meme reponse qu'une adresse inexistante : rien a apprendre ici.
            return Response(status=status.HTTP_404_NOT_FOUND)
        logger.info("Webhook WhatsApp %s : %s", instance, resultat)
        return Response({"ok": True})
