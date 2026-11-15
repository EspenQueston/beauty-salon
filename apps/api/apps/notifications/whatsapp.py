"""Les notifications WhatsApp, en plus des e-mails.

---------------------------------------------------------------------------
Les regles, decidees avec le produit (15/11/2026)
---------------------------------------------------------------------------

  - **Un seul numero expediteur**, celui de Beauty Salon, relie a Evolution
    par l'instance `WHATSAPP_INSTANCE`. Pas le numero de chaque salon.
  - **Toutes les offres**, Standard comme Pro.
  - **Des messages de service seulement** : confirmations, rappels,
    acomptes, abonnement. Jamais de promotion par ce canal.
  - La cliente garde la case « messages WhatsApp » cochee par defaut ; elle
    peut la decocher, ou repondre STOP a tout moment.

---------------------------------------------------------------------------
Comment un message part
---------------------------------------------------------------------------

  1. Un evenement (reservation, rappel, paiement valide) appelle une des
     fonctions `ecrire_*` ci-dessous. Elles ne levent jamais : l'e-mail est
     le canal de reference, WhatsApp ne doit pas le faire echouer.
  2. Une ligne `MessageWhatsApp` est ecrite, avec une cle unique : un
     second appel pour le meme moment ne cree rien.
  3. Apres la transaction, la tache `envoyer_message_whatsapp` l'envoie,
     lentement (WhatsApp sanctionne un numero qui ecrit trop vite) et
     retente si la passerelle est indisponible.

Evolution n'est pas l'API officielle de Meta : le numero peut etre limite ou
banni. Tout l'envoi passe par `_envoyer`, seul endroit a changer le jour ou
l'on bascule vers l'API WhatsApp Cloud.
"""

from __future__ import annotations

import logging
import re

from django.conf import settings
from django.db import IntegrityError, transaction

logger = logging.getLogger(__name__)

PIED = {
    "fr": "Répondez STOP pour ne plus recevoir ces messages.",
    "en": "Reply STOP to stop receiving these messages.",
}

# Les messages aux clientes : courts, une information, un lien.
CLIENTE = {
    "fr": {
        "demande": (
            "Bonjour {prenom}, votre demande de rendez-vous chez {salon} est bien reçue : "
            "{service}, le {date} à {heure}. Le salon vous confirme très vite."
        ),
        "attente_acompte": (
            "Bonjour {prenom}, votre créneau chez {salon} est réservé : {service}, le {date} "
            "à {heure}. Réglez l'acompte pour le garder."
        ),
        "confirme": (
            "Bonjour {prenom}, votre rendez-vous chez {salon} est confirmé : {service}, "
            "le {date} à {heure}."
        ),
        "accepte": (
            "Bonjour {prenom}, {salon} a confirmé votre rendez-vous : {service}, le {date} "
            "à {heure}."
        ),
        "accepte_acompte": (
            "Bonjour {prenom}, {salon} a bien reçu votre acompte. Votre rendez-vous est "
            "confirmé : {service}, le {date} à {heure}."
        ),
        "rappel": (
            "Rappel : votre rendez-vous chez {salon} est demain, le {date} à {heure} "
            "({service})."
        ),
        "annule": (
            "Bonjour {prenom}, {salon} a annulé votre rendez-vous du {date} ({service}). "
            "Vous pouvez reprendre rendez-vous en ligne."
        ),
        "deplace": (
            "Bonjour {prenom}, votre rendez-vous chez {salon} est déplacé : {service}, "
            "le {date} à {heure}."
        ),
        "acompte_refuse": (
            "Bonjour {prenom}, {salon} n'a pas retrouvé votre acompte. Renvoyez votre "
            "preuve de paiement pour garder votre créneau du {date}."
        ),
    },
    "en": {
        "demande": (
            "Hello {prenom}, your booking request at {salon} has been received: {service}, "
            "on {date} at {heure}. The salon will confirm shortly."
        ),
        "attente_acompte": (
            "Hello {prenom}, your slot at {salon} is reserved: {service}, on {date} at "
            "{heure}. Pay the deposit to keep it."
        ),
        "confirme": (
            "Hello {prenom}, your appointment at {salon} is confirmed: {service}, on {date} "
            "at {heure}."
        ),
        "accepte": (
            "Hello {prenom}, {salon} has confirmed your appointment: {service}, on {date} "
            "at {heure}."
        ),
        "accepte_acompte": (
            "Hello {prenom}, {salon} has received your deposit. Your appointment is "
            "confirmed: {service}, on {date} at {heure}."
        ),
        "rappel": (
            "Reminder: your appointment at {salon} is tomorrow, {date} at {heure} "
            "({service})."
        ),
        "annule": (
            "Hello {prenom}, {salon} has cancelled your appointment on {date} ({service}). "
            "You can book again online."
        ),
        "deplace": (
            "Hello {prenom}, your appointment at {salon} has been moved: {service}, on "
            "{date} at {heure}."
        ),
        "acompte_refuse": (
            "Hello {prenom}, {salon} could not find your deposit. Send your proof of "
            "payment again to keep your {date} slot."
        ),
    },
}

# Les messages a la direction du salon (reservations) et aux proprietaires
# (abonnement).
PRO = {
    "fr": {
        "reservation": (
            "Nouvelle réservation chez {salon} : {cliente}, {service}, le {date} à {heure}."
        ),
        "acompte": (
            "Acompte à vérifier chez {salon} : {cliente} a envoyé sa preuve de paiement pour le "
            "{date}."
        ),
        "abo_valide": (
            "Paiement validé : votre abonnement Beauty Salon ({offre}) est actif jusqu'au {fin}. "
            "Merci !"
        ),
        "abo_refuse": (
            "Votre paiement d'abonnement Beauty Salon n'a pas pu être validé. Le détail est dans "
            "votre espace."
        ),
        "trial": (
            "Votre essai gratuit Beauty Salon se termine {echeance}, le {fin}. Choisissez votre "
            "offre pour continuer à recevoir des réservations."
        ),
        "renewal": (
            "Votre abonnement Beauty Salon se termine {echeance}, le {fin}. Renouvelez-le pour "
            "continuer à recevoir des réservations."
        ),
        "grace": (
            "Votre abonnement Beauty Salon est arrivé à échéance. Réglez-le avant le {fin} pour "
            "garder vos réservations en ligne."
        ),
        "closed": (
            "Les réservations en ligne de {salon} sont fermées : l'abonnement n'est pas réglé. "
            "Vos données sont intactes, tout rouvre dès votre paiement."
        ),
    },
    "en": {
        "reservation": "New booking at {salon}: {cliente}, {service}, on {date} at {heure}.",
        "acompte": "Deposit to check at {salon}: {cliente} sent a proof of payment for {date}.",
        "abo_valide": (
            "Payment validated: your Beauty Salon subscription ({offre}) is active until {fin}. "
            "Thank you!"
        ),
        "abo_refuse": (
            "Your Beauty Salon subscription payment could not be validated. Details are in your "
            "account."
        ),
        "trial": (
            "Your Beauty Salon free trial ends {echeance}, on {fin}. Choose your plan to keep "
            "receiving bookings."
        ),
        "renewal": (
            "Your Beauty Salon subscription ends {echeance}, on {fin}. Renew it to keep receiving"
            " bookings."
        ),
        "grace": (
            "Your Beauty Salon subscription has expired. Pay before {fin} to keep online bookings"
            " open."
        ),
        "closed": (
            "Online bookings at {salon} are closed: the subscription is unpaid. Your data is "
            "safe; everything reopens once you pay."
        ),
    },
}


# ---------------------------------------------------------------------------
# Numeros
# ---------------------------------------------------------------------------


def numero(valeur: str | None) -> str | None:
    """Le numero au format attendu par WhatsApp (indicatif + numero, chiffres
    seuls), ou None.

    Sans indicatif international, on ne devine pas : « 0612345678 » peut
    etre francais, congolais ou ivoirien, et un message au mauvais pays part
    chez un inconnu. Seuls « +… » et « 00… » sont acceptes.
    """
    brut = re.sub(r"[\s().-]", "", valeur or "")
    if brut.startswith("+"):
        chiffres = brut[1:]
    elif brut.startswith("00"):
        chiffres = brut[2:]
    else:
        return None
    if not chiffres.isdigit() or not 8 <= len(chiffres) <= 15 or chiffres.startswith("0"):
        return None
    return chiffres


def configure() -> bool:
    from apps.assistants import evolution

    return bool(settings.WHATSAPP_INSTANCE) and evolution.configuree()


def desinscrit(chiffres: str) -> bool:
    from .models import DesinscriptionWhatsApp

    return DesinscriptionWhatsApp.objects.filter(numero=chiffres).exists()


# ---------------------------------------------------------------------------
# Programmer
# ---------------------------------------------------------------------------


def programmer(*, telephone: str, genre: str, texte: str, cle: str, langue: str = "fr",
               tenant_id=None, pied: bool = True) -> bool:
    """Ecrit le message dans la file et l'envoie apres la transaction.

    Rend True si un message a ete programme. Ne leve jamais.
    """
    try:
        chiffres = numero(telephone)
        if chiffres is None or desinscrit(chiffres):
            return False
        langue = langue if langue in PIED else "fr"
        if pied:
            texte = f"{texte}\n\n{PIED[langue]}"

        from .models import MessageWhatsApp

        try:
            # Un point de sauvegarde : un doublon (meme cle) ne doit pas
            # annuler la transaction de l'evenement qui l'a declenche.
            with transaction.atomic():
                message = MessageWhatsApp.objects.create(
                    tenant_id=tenant_id,
                    cle=cle[:160],
                    genre=genre[:40],
                    numero=chiffres,
                    langue=langue,
                    texte=texte[:1500],
                )
        except IntegrityError:
            return False

        identifiant = str(message.pk)

        def deposer():
            from .tasks import envoyer_message_whatsapp

            try:
                envoyer_message_whatsapp.delay(identifiant)
            except Exception:  # noqa: BLE001 - courtier arrete : la ligne reste en attente
                logger.warning("WhatsApp %s non depose dans la file Celery.", identifiant)

        transaction.on_commit(deposer)
        return True
    except Exception:  # noqa: BLE001 - l'e-mail est le canal de reference
        logger.exception("Message WhatsApp non programme (%s).", genre)
        return False


def ecrire_a_la_cliente(booking, genre: str, *, date: str, heure: str, lien: str = "") -> bool:
    """Le message `genre` a la cliente du rendez-vous, dans sa langue."""
    try:
        cliente = booking.customer
        if not getattr(cliente, "notifications_whatsapp", True):
            return False
        langue = booking.language if booking.language in CLIENTE else "fr"
        prenom = (cliente.full_name or "").split()[0] if cliente.full_name else ""
        texte = CLIENTE[langue][genre].format(
            prenom=prenom,
            salon=booking.tenant.name,
            service=booking.service_name,
            date=date,
            heure=heure,
        )
        if prenom == "":
            texte = texte.replace("Bonjour , ", "Bonjour, ").replace("Hello , ", "Hello, ")
        if lien:
            texte = f"{texte}\n{lien}"
        # Un deplacement change le creneau : la cle porte la date, pour qu'un
        # second deplacement soit annonce lui aussi.
        return programmer(
            telephone=cliente.phone,
            genre=f"cliente_{genre}",
            texte=texte,
            cle=f"resa:{booking.pk}:{genre}:{date}:{heure}",
            langue=langue,
            tenant_id=booking.tenant_id,
        )
    except Exception:  # noqa: BLE001
        logger.exception("WhatsApp cliente non programme (%s).", genre)
        return False


def _direction(tenant_id, roles) -> list[tuple[str, str]]:
    """(telephone, langue) des comptes actifs du salon ayant ces roles."""
    from apps.accounts.models import Membership

    return list(
        Membership.objects
        .filter(tenant_id=tenant_id, status=Membership.Status.ACTIVE, role__in=roles,
                user__is_active=True)
        .exclude(user__phone="")
        .values_list("user__phone", "user__locale")
    )


def ecrire_a_la_direction(tenant, genre: str, cle: str, *, proprietaires_seulement=False,
                          selon_langue=None, **valeurs) -> int:
    """Le message `genre` aux proprietaires (et gerantes) du salon, chacun dans
    sa langue. Rend le nombre de messages programmes. Ne leve jamais.

    Sans telephone sur aucun compte, le numero WhatsApp du profil du salon
    sert de repli : c'est celui que la proprietaire a donne pour etre jointe.

    `selon_langue(langue)` rend les valeurs qui dependent de la langue (une
    date longue, le nom d'une offre) ; les autres passent en `**valeurs`.
    """
    try:
        from apps.accounts.models import Membership

        roles = (Membership.Role.OWNER,) if proprietaires_seulement else (
            Membership.Role.OWNER, Membership.Role.MANAGER,
        )
        destinataires = _direction(tenant.pk, roles)
        if not destinataires:
            from apps.common.db import tenant_context
            from apps.salons.models import SalonProfile

            with tenant_context(tenant.pk):
                repli = (
                    SalonProfile.objects.filter(tenant_id=tenant.pk)
                    .values_list("whatsapp_number", flat=True)
                    .first()
                )
            if repli:
                destinataires = [(repli, "fr")]

        programmes = 0
        for telephone, locale in destinataires:
            langue = (locale or "fr")[:2]
            langue = langue if langue in PRO else "fr"
            extra = selon_langue(langue) if selon_langue else {}
            texte = PRO[langue][genre].format(salon=tenant.name, **valeurs, **extra)
            chiffres = numero(telephone) or telephone
            programmes += programmer(
                telephone=telephone,
                genre=f"pro_{genre}",
                texte=texte,
                cle=f"{cle}:{chiffres}",
                langue=langue,
                tenant_id=tenant.pk,
                pied=False,
            )
        return programmes
    except Exception:  # noqa: BLE001
        logger.exception("WhatsApp direction non programme (%s).", genre)
        return 0


# ---------------------------------------------------------------------------
# Envoyer
# ---------------------------------------------------------------------------


def _envoyer(chiffres: str, texte: str) -> str:
    """Envoie par Evolution ; rend l'identifiant du message. Seul point a
    changer pour passer a l'API officielle."""
    from apps.assistants import evolution

    reponse = evolution.envoyer_texte(settings.WHATSAPP_INSTANCE, chiffres, texte) or {}
    return str((reponse.get("key") or {}).get("id", ""))[:100]


def envoyer(message_id: str) -> str:
    """Envoie une ligne en attente. Rend le statut final, ou « retenter »."""
    from django.utils import timezone

    from apps.assistants.evolution import EvolutionIndisponible

    from .models import MessageWhatsApp

    message = MessageWhatsApp.objects.filter(pk=message_id).first()
    if message is None or message.statut != MessageWhatsApp.Statut.EN_ATTENTE:
        return "deja-traite"

    def conclure(statut, **champs):
        MessageWhatsApp.objects.filter(pk=message.pk).update(
            statut=statut, updated_at=timezone.now(), **champs
        )
        return statut

    if not configure():
        return conclure(MessageWhatsApp.Statut.IGNORE, erreur="WhatsApp non configuré.")
    if desinscrit(message.numero):
        return conclure(MessageWhatsApp.Statut.IGNORE, erreur="Numéro désinscrit (STOP).")

    tentatives = message.tentatives + 1
    try:
        identifiant = _envoyer(message.numero, message.texte)
    except EvolutionIndisponible as erreur:
        MessageWhatsApp.objects.filter(pk=message.pk).update(
            tentatives=tentatives, erreur=str(erreur)[:200], updated_at=timezone.now()
        )
        return "retenter"
    return conclure(
        MessageWhatsApp.Statut.ENVOYE,
        tentatives=tentatives,
        envoye_le=timezone.now(),
        identifiant=identifiant,
        erreur="",
    )


def abandonner(message_id: str) -> None:
    """Apres la derniere tentative : la ligne passe en echec."""
    from django.utils import timezone

    from .models import MessageWhatsApp

    MessageWhatsApp.objects.filter(
        pk=message_id, statut=MessageWhatsApp.Statut.EN_ATTENTE
    ).update(statut=MessageWhatsApp.Statut.ECHEC, updated_at=timezone.now())


# ---------------------------------------------------------------------------
# Reponses : STOP
# ---------------------------------------------------------------------------

MOTS_STOP = {"stop", "arret", "arrêt", "arreter", "arrêter", "unsubscribe", "stopper"}


def traiter_reponse(charge: dict) -> str:
    """Un evenement Evolution de l'instance plateforme. Seul « STOP » compte :
    personne ne lit les autres reponses sur ce numero."""
    from .models import DesinscriptionWhatsApp

    evenement = str(charge.get("event", "")).lower().replace("_", ".")
    if evenement != "messages.upsert":
        return "ignore:evenement"
    donnees = charge.get("data") or {}
    cle = donnees.get("key") or {}
    jid = str(cle.get("remoteJid", ""))
    if cle.get("fromMe") or not jid.endswith("@s.whatsapp.net"):
        return "ignore:origine"
    message = donnees.get("message") or {}
    texte = message.get("conversation") or (message.get("extendedTextMessage") or {}).get("text")
    if not isinstance(texte, str):
        return "ignore:non-texte"
    if texte.strip().strip(".!").lower() not in MOTS_STOP:
        return "ignore:reponse"
    chiffres = jid.split("@")[0]
    if not chiffres.isdigit():
        return "ignore:numero"
    DesinscriptionWhatsApp.objects.get_or_create(numero=chiffres)
    return "stop"
