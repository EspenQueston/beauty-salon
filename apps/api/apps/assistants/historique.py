"""L'historique des conversations de l'assistant, et le webhook n8n.

---------------------------------------------------------------------------
Deux sources, un seul historique
---------------------------------------------------------------------------

  - **WhatsApp par la plateforme** (Evolution) : chaque message recu et
    chaque reponse de l'assistant sont consignes au passage (voir
    `whatsapp.repondre`).
  - **n8n** : le salon qui a sa propre automatisation WhatsApp nous envoie
    chaque message sur son webhook. Format attendu (un message, ou
    `{"messages": [...]}` pour un lot) :

        {
          "contact": "+242061234567",      # obligatoire : numero ou identifiant
          "nom": "Awa",                     # facultatif
          "direction": "entrant",           # entrant | sortant (ou in/out, user/assistant)
          "message": "Bonjour, vous etes ouverts ?",
          "horodatage": "2026-10-03T09:14:00Z",  # facultatif (ISO ou secondes)
          "id": "wamid.HBgM..."             # facultatif : evite les doublons
        }

---------------------------------------------------------------------------
Securite du webhook
---------------------------------------------------------------------------

L'adresse porte une cle publique (qui designe le salon) et un jeton de 32
octets, garde seulement en empreinte et compare en temps constant. Une
adresse devinee sans son jeton recoit le meme 404 qu'une adresse inexistante.
Le salon doit avoir l'offre Pro ; le debit est borne.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import UTC, datetime

from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import AssistantReglages, ConversationAssistant, MessageAssistant

TEXTE_MAX = 4000
LOT_MAX = 50

ENTRANTS = {"entrant", "in", "incoming", "user", "client", "cliente"}
SORTANTS = {"sortant", "out", "outgoing", "assistant", "bot", "ia"}


class Refus(Exception):
    """Webhook refuse : adresse inconnue, jeton faux ou salon sans Pro."""


class MessageInvalide(ValueError):
    pass


def empreinte(jeton: str) -> str:
    return hashlib.sha256(jeton.encode()).hexdigest()


def contact_normalise(valeur: str) -> str:
    """« 242061234567@s.whatsapp.net » -> « +242061234567 » ; le reste, tel quel."""
    brut = str(valeur or "").strip().split("@")[0]
    chiffres = re.sub(r"[^0-9]", "", brut)
    if chiffres and re.fullmatch(r"\+?[0-9 ().-]+", brut):
        return f"+{chiffres}"[:64]
    return brut[:64]


def consigner(
    tenant_id,
    *,
    canal: str,
    contact: str,
    direction: str,
    texte: str,
    nom: str = "",
    quand: datetime | None = None,
    reference: str = "",
) -> bool:
    """Ajoute un message au fil. A appeler dans le contexte du salon.

    Renvoie False pour un doublon (meme `reference`) : rien n'est ecrit.
    """
    contact = contact_normalise(contact)
    texte = (texte or "").strip()[:TEXTE_MAX]
    if not contact or not texte:
        raise MessageInvalide("Contact et message sont obligatoires.")
    quand = quand or timezone.now()
    reference = (reference or "")[:120]

    try:
        with transaction.atomic():
            conversation, _ = ConversationAssistant.objects.get_or_create(
                tenant_id=tenant_id,
                canal=canal,
                contact=contact,
                defaults={"nom": nom[:120], "dernier_message_le": quand},
            )
            MessageAssistant.objects.create(
                tenant_id=tenant_id,
                conversation=conversation,
                direction=direction,
                texte=texte,
                envoye_le=quand,
                reference=reference,
            )
    except IntegrityError:
        # Le meme message, deja recu (n8n rejoue un envoi en cas d'echec).
        return False

    champs = {"nombre_messages": F("nombre_messages") + 1}
    if quand >= conversation.dernier_message_le or conversation.nombre_messages == 0:
        champs.update(dernier_message_le=quand, dernier_apercu=texte[:200])
    if nom and not conversation.nom:
        champs["nom"] = nom[:120]
    ConversationAssistant.objects.filter(pk=conversation.pk).update(**champs)
    return True


# ---------------------------------------------------------------------------
# Le webhook n8n
# ---------------------------------------------------------------------------


def nouvelle_adresse(reglages: AssistantReglages) -> tuple[str, str]:
    """Cree (ou remplace) la cle et le jeton. Le jeton n'est rendu qu'ici, une fois."""
    cle = reglages.n8n_cle or secrets.token_urlsafe(12)
    jeton = secrets.token_urlsafe(32)
    reglages.n8n_cle = cle
    reglages.n8n_empreinte = empreinte(jeton)
    reglages.save(update_fields=["n8n_cle", "n8n_empreinte", "updated_at"])
    return cle, jeton


def reglages_du_webhook(cle: str, jeton: str) -> AssistantReglages:
    from apps.billing.droits import a_la_fonction
    from apps.common.db import tenant_context

    reglages = (
        AssistantReglages.all_tenants.using("admin").filter(n8n_cle=cle).first() if cle else None
    )
    attendu = reglages.n8n_empreinte if reglages and reglages.n8n_empreinte else "0" * 64
    if not hmac.compare_digest(empreinte(jeton or ""), attendu) or reglages is None:
        raise Refus("Adresse inconnue.")
    # Dans le contexte du salon : l'abonnement se lit sous RLS, et la requete
    # du webhook n'en a aucun (pas de session, pas d'hote de salon).
    with tenant_context(reglages.tenant_id):
        pro = a_la_fonction(reglages.tenant_id, "whatsapp_assistant")
    if not pro:
        raise Refus("Offre Pro requise.")
    return reglages


def _direction(valeur) -> str:
    texte = str(valeur or "").strip().lower()
    if texte in SORTANTS:
        return MessageAssistant.Direction.SORTANT
    if texte in ENTRANTS or not texte:
        return MessageAssistant.Direction.ENTRANT
    raise MessageInvalide(f"Direction inconnue : {valeur!r}.")


def _horodatage(valeur) -> datetime | None:
    if valeur in (None, ""):
        return None
    if isinstance(valeur, (int, float)) or (isinstance(valeur, str) and valeur.isdigit()):
        secondes = float(valeur)
        if secondes > 1e12:  # millisecondes
            secondes /= 1000
        return datetime.fromtimestamp(secondes, tz=UTC)
    lu = parse_datetime(str(valeur))
    if lu is None:
        raise MessageInvalide("Horodatage illisible.")
    return lu if timezone.is_aware(lu) else timezone.make_aware(lu, UTC)


def recevoir(reglages: AssistantReglages, charge) -> dict:
    """Ecrit les messages recus de n8n. Dans le contexte du salon."""
    lot = charge.get("messages") if isinstance(charge, dict) and "messages" in charge else [charge]
    if not isinstance(lot, list) or not lot:
        raise MessageInvalide("Aucun message.")
    if len(lot) > LOT_MAX:
        raise MessageInvalide(f"{LOT_MAX} messages au plus par envoi.")

    recus = doublons = 0
    for element in lot:
        if not isinstance(element, dict):
            raise MessageInvalide("Chaque message doit être un objet JSON.")
        ecrit = consigner(
            reglages.tenant_id,
            canal=ConversationAssistant.Canal.N8N,
            contact=str(
                element.get("contact") or element.get("telephone") or element.get("from") or ""
            ),
            nom=str(element.get("nom") or element.get("name") or ""),
            direction=_direction(element.get("direction") or element.get("role")),
            texte=str(element.get("message") or element.get("texte") or element.get("text") or ""),
            quand=_horodatage(element.get("horodatage") or element.get("timestamp")),
            reference=str(element.get("id") or ""),
        )
        recus += int(ecrit)
        doublons += int(not ecrit)

    AssistantReglages.objects.filter(pk=reglages.pk).update(n8n_derniere_reception=timezone.now())
    return {"recus": recus, "doublons": doublons}
