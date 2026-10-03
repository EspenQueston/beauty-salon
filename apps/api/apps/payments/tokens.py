"""Jeton de paiement : le lien qui tient lieu d'authentification.

La cliente n'a pas de compte - elle vient de reserver depuis un lien
WhatsApp. Il faut pourtant qu'elle seule puisse voir le montant de son
acompte et envoyer sa preuve, et qu'un identifiant devine n'ouvre rien.

Le jeton est signe par la cle du serveur : il porte l'identifiant du
rendez-vous en clair, mais toute modification invalide la signature. Le meme
mecanisme sert deja aux invitations a laisser un avis.

---------------------------------------------------------------------------
Trois jetons, trois durees, et pourquoi ils ne se confondent pas
---------------------------------------------------------------------------

  - **paiement** : ouvre la page de reglement. Il authentifie, rien de plus.
    Ce n'est pas lui qui decide si l'on peut encore payer - c'est l'etat du
    rendez-vous, que le serveur relit a chaque appel. Un jeton qui meurt
    avant l'etat produirait « ce lien n'est plus valable » la ou il fallait
    dire « le salon a deja confirme, tout va bien ».
  - **statut** : ouvre la page de suivi, en lecture seule. Il vit aussi
    longtemps que le rendez-vous a un sens, parce que c'est la page qu'on
    rouvre trois semaines plus tard pour verifier l'heure.
  - **arrivee** : le QR que la cliente montre au salon. Il ne donne qu'un
    droit - dire « je suis arrivee » sur *ce* rendez-vous.
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import timedelta

from django.conf import settings
from django.core import signing
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.scheduling.models import Booking

SALT = "beauty-salon.deposit-payment"

# Volontairement plus long que la fenetre de reservation (30 minutes).
#
# Les deux ne mesurent pas la meme chose. La fenetre dit combien de temps le
# creneau reste bloque ; le jeton dit combien de temps le lien identifie sa
# porteuse. Les aligner casserait le cas le plus frequent : un refus de
# versement renvoie la cliente sur la meme page par e-mail, parfois le
# lendemain, et ce lien-la doit fonctionner.
#
# Sept jours : assez pour lire un e-mail et agir, assez court pour qu'un lien
# oublie dans une conversation WhatsApp ne serve pas indefiniment.
TOKEN_MAX_AGE = 60 * 60 * 24 * 7


def payment_token(booking) -> str:
    return signing.dumps({"booking": str(booking.id)}, salt=SALT)


def booking_from_token(token: str) -> Booking | None:
    """Rendez-vous designe par le jeton, ou None.

    Renvoie None pour toute raison - signature invalide, jeton expire,
    rendez-vous disparu. L'appelant repond la meme chose dans les trois cas :
    distinguer « expire » de « falsifie » apprendrait a qui essaie.
    """
    if not token:
        return None

    try:
        data = signing.loads(token, salt=SALT, max_age=TOKEN_MAX_AGE)
    except signing.BadSignature:
        return None

    return (
        Booking.objects.select_related("customer", "deposit_proof")
        .filter(id=data.get("booking"))
        .first()
    )


# ---------------------------------------------------------------------------
# Jeton de statut : la page de suivi du rendez-vous
# ---------------------------------------------------------------------------

STATUS_SALT = "beauty-salon.booking-status"

# Meme duree que le QR d'arrivee : les deux vivent dans l'espace de la
# cliente et servent au meme moment, la page de suivi portant justement le QR.
STATUS_MAX_AGE = 60 * 60 * 24 * 120


def status_token(booking) -> str:
    """Jeton de lecture seule.

    Il est emis des la reservation, bien avant que le salon n'ait accepte :
    c'est precisement pendant l'attente qu'on a besoin de savoir ou l'on en
    est. Il n'autorise aucune ecriture - ni payer, ni annuler, ni arriver.
    """
    return signing.dumps({"booking": str(booking.id)}, salt=STATUS_SALT)


def booking_from_status(token: str) -> Booking | None:
    """Rendez-vous designe par un jeton de suivi, ou None."""
    if not token:
        return None

    try:
        data = signing.loads(token, salt=STATUS_SALT, max_age=STATUS_MAX_AGE)
    except signing.BadSignature:
        return None

    return (
        Booking.objects.select_related(
            "customer", "staff_member", "tenant", "deposit_proof"
        )
        .filter(id=data.get("booking"))
        .first()
    )


# ---------------------------------------------------------------------------
# Jeton d'arrivee : le QR que la cliente montre au salon
# ---------------------------------------------------------------------------

CHECKIN_SALT = "beauty-salon.checkin"

# Un rendez-vous se prend des semaines a l'avance, et le QR vit dans l'espace
# de la cliente pendant tout ce temps. Le jeton dure donc longtemps - mais il
# ne donne qu'un droit : dire « je suis arrivee » sur *ce* rendez-vous, et
# seulement si une personne du salon est connectee pour le scanner.
CHECKIN_MAX_AGE = 60 * 60 * 24 * 120


def checkin_token(booking) -> str:
    return signing.dumps({"booking": str(booking.id)}, salt=CHECKIN_SALT)


def booking_from_checkin(token: str) -> Booking | None:
    """Rendez-vous designe par un QR d'arrivee, ou None.

    Meme discipline que le jeton de paiement : une seule reponse pour toutes
    les raisons d'echec. Distinguer « expire » de « falsifie » apprendrait
    quelque chose a qui essaie.
    """
    if not token:
        return None

    try:
        data = signing.loads(token, salt=CHECKIN_SALT, max_age=CHECKIN_MAX_AGE)
    except signing.BadSignature:
        return None

    return (
        Booking.objects.select_related("customer", "staff_member")
        .filter(id=data.get("booking"))
        .first()
    )


# ---------------------------------------------------------------------------
# Code court : le QR qu'on tape quand on ne peut pas le scanner
# ---------------------------------------------------------------------------
#
# Le jeton d'arrivee fait cent quarante caracteres de base64. Un appareil
# photo les lit sans broncher ; une personne, non. Or l'appareil photo manque
# precisement les jours ou il faudrait qu'il marche : permission refusee,
# objectif casse, poste fixe a l'accueil sans camera, page ouverte en HTTP
# sur le reseau du salon - `getUserMedia` refuse hors contexte securise.
#
# Il faut donc un second chemin, et un chemin qui se dicte au telephone.
#
# ---------------------------------------------------------------------------
# Derive, et non stocke
# ---------------------------------------------------------------------------
#
# Le code se calcule a partir de l'identifiant du rendez-vous et de la cle du
# serveur. Aucune colonne, aucune migration, aucune reprise de donnees : les
# rendez-vous deja pris en ont un des aujourd'hui. Un code stocke aurait
# demande de le generer pour les milliers de lignes existantes, et de gerer
# l'unicite a l'insertion - pour la meme garantie.
#
# ---------------------------------------------------------------------------
# Ce que ce code ne protege pas, et pourquoi ce n'est pas grave
# ---------------------------------------------------------------------------
#
# Six caracteres, c'est 244 millions de combinaisons. C'est beaucoup pour une
# personne qui tape, peu pour une machine qui essaie. Mais le code ne donne
# rien a lui seul : il faut deja une session du salon pour s'en servir, et le
# seul pouvoir qu'il confere est de noter arrivee une cliente de ce meme
# salon. Un salon qui voudrait mentir sur ses propres arrivees n'a pas besoin
# de deviner un code - il a le bouton dans son agenda.
#
# La recherche est en outre bornee a quelques jours autour de maintenant :
# cela ecarte toute collision entre deux rendez-vous, et rend la reponse
# comprehensible quand le code est celui d'un rendez-vous lointain.

# Vingt caracteres, et chaque exclusion a sa raison : B/8, G/6/9, I/1/L,
# O/0/Q, S/5, U/V, Z/2. Ces paires se confondent a la lecture comme a l'oral,
# et le code se dicte au telephone autant qu'il se recopie d'un ecran.
#
# 20^6 = 64 millions de combinaisons. Largement assez pour que deux
# rendez-vous du meme salon ne se croisent jamais dans une fenetre de quatre
# jours, et c'est la seule garantie qu'on lui demande.
CHECKIN_CODE_ALPHABET = "ACDEFHJKMNPRTVWXY347"
CHECKIN_CODE_LENGTH = 6

# Fenetre de recherche autour de maintenant. Deux jours de part et d'autre :
# assez pour une cliente en avance ou un salon qui regularise le lendemain,
# assez etroit pour que deux codes ne puissent pas se croiser.
CHECKIN_CODE_WINDOW = timedelta(days=2)


def checkin_code(booking) -> str:
    """Code d'arrivee a six caracteres, lisible et dictable."""
    digest = hmac.new(
        settings.SECRET_KEY.encode(),
        f"{CHECKIN_SALT}:{booking.id}".encode(),
        hashlib.sha256,
    ).digest()

    number = int.from_bytes(digest[:8], "big")
    letters = []
    for _ in range(CHECKIN_CODE_LENGTH):
        number, index = divmod(number, len(CHECKIN_CODE_ALPHABET))
        letters.append(CHECKIN_CODE_ALPHABET[index])
    return "".join(letters)


def normalize_checkin_code(raw: str) -> str:
    """Ce que la personne a tape, ramene a ce que le code est.

    Les espaces, les tirets et la casse sont du bruit de saisie : « a4-kn m3 »
    et « A4KNM3 » designent le meme rendez-vous, et refuser le premier
    n'apprend rien a personne.

    En revanche rien n'est *devine*. On pourrait etre tente de rattraper les
    confusions classiques - lire le « O » tape comme le « Q » du code. Ce
    serait une faute : la correction transformerait parfois une frappe erronee
    en un code valide, celui d'une autre cliente, et le salon noterait arrivee
    la mauvaise personne sans qu'aucun message ne l'avertisse. C'est
    exactement ce que le code existe pour eviter.

    Un caractere hors alphabet rend donc la saisie invalide, et la vue le dit
    en clair au lieu de repondre « code inconnu ».
    """
    return "".join(char for char in raw.upper() if char.isalnum())


def checkin_code_is_wellformed(code: str) -> bool:
    """Le code a-t-il la bonne longueur et le bon alphabet ?"""
    return len(code) == CHECKIN_CODE_LENGTH and all(
        char in CHECKIN_CODE_ALPHABET for char in code
    )


def booking_from_code(code: str, tenant_id) -> tuple[Booking | None, bool]:
    """Rendez-vous portant ce code dans le salon donne.

    Renvoie `(rendez-vous, ambigu)`. L'ambiguite - deux rendez-vous du meme
    salon partageant un code dans la meme fenetre - est astronomiquement
    improbable, mais elle se signale plutot qu'elle ne se tranche au hasard :
    noter arrivee la mauvaise cliente est exactement ce que le code existe
    pour eviter.
    """
    wanted = normalize_checkin_code(code)
    if not checkin_code_is_wellformed(wanted):
        return None, False

    now = timezone.now()
    candidates = Booking.objects.select_related("customer", "staff_member").filter(
        tenant_id=tenant_id,
        starts_at__gte=now - CHECKIN_CODE_WINDOW,
        starts_at__lte=now + CHECKIN_CODE_WINDOW,
    )

    # Le statut n'est volontairement pas filtre ici : c'est la vue qui doit
    # pouvoir repondre « ce rendez-vous est annule » plutot que « code
    # inconnu », qui enverrait chercher une faute de frappe inexistante.
    found = [
        booking
        for booking in candidates
        if hmac.compare_digest(checkin_code(booking), wanted)
    ]

    if len(found) > 1:
        return None, True
    return (found[0] if found else None), False


def code_du_rendez_vous(code: str, booking_id, tenant_id) -> tuple[Booking | None, bool]:
    """Verifie un code contre **un** rendez-vous connu, sans fenetre de dates.

    Quand le panneau d'arrivee a ete ouvert depuis une ligne de l'agenda, on
    sait deja de quel rendez-vous on parle : il n'y a rien a chercher. La
    fenetre de +/- deux jours n'existe que pour empecher deux codes a six
    caracteres de se croiser, et cette precaution n'a aucun objet quand il
    n'y a qu'un seul candidat.

    Elle avait en revanche un cout bien reel : une cliente attendue dans
    deux jours et demi, affichee a l'ecran et nommee dans le panneau, se
    voyait repondre « aucun rendez-vous ne porte ce code ».

    Si le code ne correspond pas au rendez-vous ouvert, on retombe sur la
    recherche par fenetre : c'est elle qui permet de dire « ce code est
    celui d'une autre cliente » plutot qu'un simple refus.
    """
    wanted = normalize_checkin_code(code)
    if not checkin_code_is_wellformed(wanted):
        return None, False

    try:
        booking = (
            Booking.objects.select_related("customer", "staff_member")
            .filter(pk=booking_id, tenant_id=tenant_id)
            .first()
        )
    except (ValidationError, ValueError):
        booking = None

    if booking is not None and hmac.compare_digest(checkin_code(booking), wanted):
        return booking, False

    return booking_from_code(wanted, tenant_id)


# ---------------------------------------------------------------------------
# Annulation par la cliente
# ---------------------------------------------------------------------------
#
# Un sel distinct, et c'est tout l'interet : le jeton de suivi promet, dans sa
# propre documentation, de n'autoriser aucune ecriture. Le reutiliser pour
# annuler romprait cette promesse sans que rien ne le signale — un jeton
# copie d'un signet vieux de quatre mois deviendrait un droit de suppression.
#
# Celui-ci n'est emis que lorsque l'annulation est reellement ouverte, et il
# ne vit que le temps d'une visite sur la page. Au-dela, la cliente rouvre sa
# page : le jeton se reemet si la fenetre du salon le permet encore, et ne se
# reemet pas sinon.
CANCEL_SALT = "beauty-salon.booking-cancel"

CANCEL_MAX_AGE = 60 * 60 * 6


def cancel_token(booking) -> str:
    """Droit d'annuler ce rendez-vous, et rien d'autre."""
    return signing.dumps({"booking": str(booking.id)}, salt=CANCEL_SALT)


def booking_from_cancel(token: str) -> Booking | None:
    """Rendez-vous designe par un jeton d'annulation, ou None."""
    if not token:
        return None

    try:
        data = signing.loads(token, salt=CANCEL_SALT, max_age=CANCEL_MAX_AGE)
    except signing.BadSignature:
        return None

    return (
        Booking.objects.select_related("customer", "staff_member", "tenant", "service")
        .filter(id=data.get("booking"))
        .first()
    )
