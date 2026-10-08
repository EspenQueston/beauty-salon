"""Le client de l'API Evolution (passerelle WhatsApp installee sur le serveur).

---------------------------------------------------------------------------
Ce que ce module suppose, et ce qu'il ne garantit pas
---------------------------------------------------------------------------

Evolution API (v2) relie un numero WhatsApp par le protocole de WhatsApp Web :
chaque salon scanne un QR code avec son telephone. Ce n'est pas l'API
officielle de Meta — un numero peut etre limite ou banni par WhatsApp en cas
d'usage juge abusif. Les routes appelees ici sont celles de la v2 :

  POST   /instance/create                 creer l'instance et son webhook
  GET    /instance/connect/{instance}     QR code a scanner
  GET    /instance/connectionState/{i}    etat de la connexion
  POST   /message/sendText/{instance}     envoyer un message texte
  DELETE /instance/logout/{instance}      deconnecter
  DELETE /instance/delete/{instance}      supprimer

La cle globale (`EVOLUTION_API_KEY`) ne quitte jamais le serveur : elle part
dans l'en-tete `apikey` des appels sortants, et nulle part ailleurs — ni dans
une reponse au navigateur, ni dans un journal.
"""

from __future__ import annotations

import logging

from django.conf import settings

logger = logging.getLogger(__name__)
DELAI = 15


class EvolutionIndisponible(Exception):
    """Non configuree, injoignable, ou reponse inattendue."""


def configuree() -> bool:
    return bool(settings.EVOLUTION_API_URL and settings.EVOLUTION_API_KEY)


def _appel(methode: str, chemin: str, **kwargs) -> dict:
    if not configuree():
        raise EvolutionIndisponible("Evolution API n'est pas configurée.")
    import httpx

    url = settings.EVOLUTION_API_URL.rstrip("/") + chemin
    try:
        reponse = httpx.request(
            methode,
            url,
            headers={"apikey": settings.EVOLUTION_API_KEY},
            timeout=DELAI,
            **kwargs,
        )
    except httpx.HTTPError as erreur:
        logger.warning("Evolution injoignable (%s %s) : %s", methode, chemin, type(erreur).__name__)
        raise EvolutionIndisponible("Passerelle WhatsApp injoignable.") from erreur
    if reponse.status_code >= 400:
        logger.warning("Evolution a refusé %s %s : HTTP %s", methode, chemin, reponse.status_code)
        raise EvolutionIndisponible(f"Passerelle WhatsApp : erreur {reponse.status_code}.")
    try:
        return reponse.json()
    except ValueError:
        return {}


def creer_instance(instance: str, webhook: str) -> dict:
    return _appel(
        "POST",
        "/instance/create",
        json={
            "instanceName": instance,
            "qrcode": True,
            "integration": "WHATSAPP-BAILEYS",
            "webhook": {
                "url": webhook,
                "byEvents": False,
                "base64": False,
                "events": ["MESSAGES_UPSERT", "CONNECTION_UPDATE"],
            },
        },
    )


def qr_code(instance: str) -> str:
    """L'image du QR code (data URI base64), ou chaine vide si deja connecte."""
    donnees = _appel("GET", f"/instance/connect/{instance}")
    return donnees.get("base64") or (donnees.get("qrcode") or {}).get("base64") or ""


def etat(instance: str) -> str:
    """« open » (connecte), « connecting », « close »…"""
    donnees = _appel("GET", f"/instance/connectionState/{instance}")
    return ((donnees.get("instance") or {}).get("state") or donnees.get("state") or "").lower()


def envoyer_texte(instance: str, numero: str, texte: str) -> None:
    _appel("POST", f"/message/sendText/{instance}", json={"number": numero, "text": texte})


def supprimer(instance: str) -> None:
    for methode, chemin in (
        ("DELETE", f"/instance/logout/{instance}"),
        ("DELETE", f"/instance/delete/{instance}"),
    ):
        try:
            _appel(methode, chemin)
        except EvolutionIndisponible:
            # Deja deconnectee ou supprimee : on continue le menage.
            continue
