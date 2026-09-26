"""Les messages WhatsApp recus, et la reponse de l'assistant.

---------------------------------------------------------------------------
Qui peut appeler le webhook
---------------------------------------------------------------------------

L'adresse du webhook porte l'instance et un jeton aleatoire de 32 octets,
donnes a Evolution a la creation de l'instance. On ne garde que l'empreinte
SHA-256 du jeton, comparee en temps constant : une fuite de la base ne
suffit pas a forger un appel, et une instance devinee sans son jeton est
refusee comme une instance inconnue.

---------------------------------------------------------------------------
Rejeu, boucles, abus
---------------------------------------------------------------------------

  - chaque message n'est traite qu'une fois (identifiant retenu 48 h) ;
  - un message de plus de dix minutes est ignore : un evenement rejoue plus
    tard ne declenche pas de reponse ;
  - les messages envoyes par le salon lui-meme, les groupes et les statuts
    sont ignores — l'assistant ne se repond pas et ne parle pas en groupe ;
  - vingt reponses par heure et par contact au plus.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time

from django.core.cache import cache
from django.utils import timezone

from .models import AssistantReglages

logger = logging.getLogger(__name__)

FENETRE_REJEU = 600
DUREE_DEDOUBLONNAGE = 48 * 3600
REPONSES_PAR_HEURE = 20
# Reponses d'IA par salon et par jour : le meme plafond que le mini-site.
QUOTA_WHATSAPP_JOUR = 300
FIL_MAX = 8


def _accuse_de_reception(tenant) -> str:
    return f"Merci pour votre message ! {tenant.name} vous répond dès que possible."


class WebhookRefuse(Exception):
    pass


def empreinte(jeton: str) -> str:
    return hashlib.sha256(jeton.encode()).hexdigest()


def reglages_de_l_instance(instance: str, jeton: str) -> AssistantReglages:
    """Les reglages du salon, si l'instance et son jeton concordent."""
    reglages = (
        AssistantReglages.all_tenants.using("admin").filter(whatsapp_instance=instance).first()
        if instance
        else None
    )
    attendu = reglages.whatsapp_empreinte if reglages else "0" * 64
    # Comparaison en temps constant, meme pour une instance inconnue.
    if not hmac.compare_digest(empreinte(jeton or ""), attendu) or reglages is None:
        raise WebhookRefuse("Instance ou jeton inconnu.")
    return reglages


def traiter(instance: str, jeton: str, charge: dict) -> str:
    """Traite un evenement Evolution ; renvoie ce qui a ete fait (pour le journal)."""
    reglages = reglages_de_l_instance(instance, jeton)
    evenement = str(charge.get("event", "")).lower().replace("_", ".")
    donnees = charge.get("data") or {}

    if evenement == "connection.update":
        etat = str(donnees.get("state", "")).lower()
        statut = {
            "open": AssistantReglages.StatutWhatsApp.CONNECTE,
            "close": AssistantReglages.StatutWhatsApp.DECONNECTE,
        }.get(etat)
        if statut:
            AssistantReglages.all_tenants.using("admin").filter(pk=reglages.pk).update(
                whatsapp_statut=statut, whatsapp_derniere_activite=timezone.now()
            )
        return f"connexion:{etat}"

    if evenement != "messages.upsert":
        return "ignore:evenement"

    cle = donnees.get("key") or {}
    jid = str(cle.get("remoteJid", ""))
    if cle.get("fromMe") or not jid.endswith("@s.whatsapp.net"):
        return "ignore:origine"

    # Sans horodatage, la fenetre de rejeu ne peut pas s'appliquer : un tel
    # message est ignore plutot que traite sans controle. Baileys l'envoie en
    # nombre, ou en « Long » ({"low": ...}) selon les versions.
    horodatage = donnees.get("messageTimestamp")
    if isinstance(horodatage, dict):
        horodatage = horodatage.get("low")
    try:
        if not horodatage:
            return "ignore:horodatage"
        if time.time() - int(horodatage) > FENETRE_REJEU:
            return "ignore:ancien"
    except (TypeError, ValueError):
        return "ignore:horodatage"

    message = donnees.get("message") or {}
    texte = message.get("conversation") or (message.get("extendedTextMessage") or {}).get("text")
    if not isinstance(texte, str) or not texte.strip():
        return "ignore:non-texte"

    identifiant = str(cle.get("id", ""))
    if not identifiant or not cache.add(f"wa:vu:{instance}:{identifiant}", 1, DUREE_DEDOUBLONNAGE):
        return "ignore:deja-vu"

    from .tasks import repondre_whatsapp

    repondre_whatsapp.delay(str(reglages.tenant_id), jid, texte.strip()[:1000])
    return "reponse:programmee"


def repondre(tenant, jid: str, texte: str) -> str:
    """Genere et envoie la reponse. A appeler dans le contexte du salon."""
    from apps.billing.droits import a_la_fonction

    from . import evolution, ia

    reglages = AssistantReglages.objects.filter(tenant_id=tenant.id).first()
    if (
        reglages is None
        or not reglages.whatsapp_actif
        or not a_la_fonction(tenant.id, "whatsapp_assistant")
    ):
        return "ignore:inactif"

    rythme = f"wa:rythme:{tenant.id}:{jid}"
    cache.add(rythme, 0, 3600)
    if cache.incr(rythme) > REPONSES_PAR_HEURE:
        return "ignore:rythme"

    # Plafond par salon et par jour, comme sur le mini-site : la limite par
    # contact ne suffit pas contre qui ecrit depuis cent numeros, et chaque
    # reponse est un appel d'IA facture. Au-dela, un accuse de reception
    # (sans IA), une fois par jour et par contact.
    jour = f"wa:quota:{tenant.id}:{timezone.localdate()}"
    cache.add(jour, 0, 26 * 3600)
    if cache.incr(jour) > QUOTA_WHATSAPP_JOUR:
        if not cache.add(f"wa:repli:{tenant.id}:{jid}", 1, 24 * 3600):
            return "ignore:quota"
        evolution.envoyer_texte(
            reglages.whatsapp_instance, jid.split("@")[0], _accuse_de_reception(tenant)
        )
        return "reponse:quota"

    fil_cle = f"wa:fil:{tenant.id}:{jid}"
    fil = (cache.get(fil_cle) or [])[-FIL_MAX:]
    fil.append({"role": "user", "content": texte})
    try:
        reponse = ia.SERVICE.repondre(
            ia.SYSTEME_WHATSAPP.format(salon=tenant.name), ia.contexte_public(tenant), fil
        )
    except ia.IAIndisponible:
        # Une seule fois par jour et par contact : l'accuse de reception
        # rassure, le repeter a chaque message agacerait.
        if not cache.add(f"wa:repli:{tenant.id}:{jid}", 1, 24 * 3600):
            return "ignore:ia-indisponible"
        reponse = _accuse_de_reception(tenant)
    evolution.envoyer_texte(reglages.whatsapp_instance, jid.split("@")[0], reponse)
    fil.append({"role": "assistant", "content": reponse})
    cache.set(fil_cle, fil[-FIL_MAX:], 24 * 3600)
    AssistantReglages.objects.filter(pk=reglages.pk).update(
        whatsapp_derniere_activite=timezone.now()
    )
    return "reponse:envoyee"
