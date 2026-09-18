"""Le chemin d'un acompte, de la demande a l'acceptation.

---------------------------------------------------------------------------
Les quatre etats, et qui les fait avancer
---------------------------------------------------------------------------

    en attente de paiement  ──(la cliente envoie sa preuve)──▶  demandee
             │                                                     │
             │ (delai depasse)                                     │ (le salon accepte)
             ▼                                                     ▼
          annulee                                              confirmee

Aucune transition n'est automatique sauf l'expiration. C'est voulu : nous ne
voyons pas le paiement - il va directement du telephone de la cliente au
compte du salon - donc personne d'autre qu'un humain du salon ne peut dire
qu'il est arrive.

---------------------------------------------------------------------------
Pourquoi le creneau reste bloque pendant l'attente
---------------------------------------------------------------------------

`pending_payment` fait partie des statuts bloquants. Une cliente qui scanne
un QR code et cherche son mot de passe ne doit pas se faire prendre son
creneau entre-temps.

Mais un creneau bloque indefiniment par quelqu'un qui ne paiera jamais est
aussi couteux : d'ou l'expiration, qui le rend au bout d'un delai court.
"""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from apps.audit.models import AuditLog
from apps.scheduling.models import Booking

from .models import DepositProof, PaymentChannel

# Temps pendant lequel le creneau reste bloque sans versement.
#
# Trente minutes : le temps d'ouvrir son application, de scanner, de payer et
# de faire une capture d'ecran, meme sur un reseau lent. Au-dela, un creneau
# de quatre heures reste gele par quelqu'un qui a ferme l'onglet, et le salon
# perd sa journee sans jamais savoir pourquoi.
#
# Le compte a rebours ne s'applique **qu'avant** le premier envoi de preuve.
# Des qu'une capture arrive, la balle est dans le camp du salon : reprendre
# le creneau a une cliente qui a peut-etre reellement paye serait injuste, et
# c'est pour cela que `release_expired` exige `deposit_proof__isnull=True`.
PAYMENT_WINDOW = timedelta(minutes=30)

# Le motif inscrit sur un rendez-vous que l'echeance a annule.
#
# Une constante et non deux chaines : `expirer` l'ecrit, `payment_state` le
# relit pour distinguer l'echeance d'une annulation decidee par quelqu'un.
# Deux libelles qui divergeraient d'un accent feraient afficher le mauvais
# ecran, et rien ne le signalerait.
MOTIF_EXPIRATION = "Acompte non réglé dans le délai"


# Les etats visibles de la page de reglement. Une seule valeur a lire cote
# navigateur, plutot que quatre booleens qu'il faudrait recombiner - et
# recombiner differemment ici et la, ce qui finit toujours par diverger.
class PaymentState:
    PAYABLE = "payable"
    WAITING = "waiting"
    REFUSED = "refused"
    SETTLED = "settled"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


def payment_deadline(booking):
    """Instant ou le creneau se libere, ou None s'il ne se libere plus.

    Une preuve deja envoyee suspend le compte a rebours : le rendez-vous
    n'attend plus la cliente, il attend le salon.
    """
    if getattr(booking, "deposit_proof", None) is not None:
        return None
    return booking.created_at + PAYMENT_WINDOW


def payment_state(booking, now=None) -> str:
    """Ou en est le reglement de ce rendez-vous.

    L'ordre des tests n'est pas indifferent. « Le salon a confirme » passe
    avant tout le reste : c'est le seul etat qui rend la page de reglement
    non seulement inutile mais trompeuse, puisqu'elle inviterait a payer une
    seconde fois ce qui est deja regle.
    """
    now = now or timezone.now()

    if booking.status == Booking.Status.CANCELLED:
        # « Annule » et « delai depasse » sont deux histoires differentes.
        #
        # Depuis que l'echeance annule pour de bon, un rendez-vous expire est
        # aussi un rendez-vous annule - et la page allait donc afficher le
        # message generique. C'eut ete une perte : « faute de reglement dans
        # les trente minutes, le creneau a ete remis a disposition, rien ne
        # vous a ete debite » dit ce qui s'est passe et ce qu'on peut faire
        # ensuite, la ou « ce rendez-vous a ete annule » laisse chercher.
        #
        # On compare au motif ecrit par `expirer`, des deux cotes la meme
        # constante : c'est la seule facon de distinguer l'echeance d'une
        # annulation decidee par le salon ou par la cliente.
        if booking.cancellation_reason == MOTIF_EXPIRATION:
            return PaymentState.EXPIRED
        return PaymentState.CANCELLED

    if booking.deposit_paid or booking.status in (
        Booking.Status.CONFIRMED,
        Booking.Status.COMPLETED,
        Booking.Status.NO_SHOW,
    ):
        return PaymentState.SETTLED

    proof = getattr(booking, "deposit_proof", None)
    if proof is not None:
        if proof.status == DepositProof.Status.SUBMITTED:
            return PaymentState.WAITING
        if proof.status == DepositProof.Status.REJECTED:
            return PaymentState.REFUSED

    deadline = payment_deadline(booking)
    if deadline is not None and now >= deadline:
        return PaymentState.EXPIRED

    return PaymentState.PAYABLE


class PaymentRefused(Exception):
    """Message destine a l'utilisatrice, en francais."""


def channels_for(tenant_id) -> list[PaymentChannel]:
    """Moyens d'encaissement reellement affichables pour ce salon."""
    return [
        channel
        for channel in PaymentChannel.objects.filter(active=True).select_related(
            "qr_image"
        )
        if channel.usable
    ]


def needs_payment(booking, channels) -> bool:
    """Ce rendez-vous doit-il passer par la page de paiement ?

    Deux conditions, et les deux sont necessaires : un acompte est demande,
    **et** le salon a declare au moins un moyen d'encaisser. Un salon sans QR
    code ne doit pas envoyer sa cliente sur une page qui ne montre rien - il
    encaissera sur place, comme avant.
    """
    return bool(booking.deposit_amount and booking.deposit_amount > 0 and channels)


def submit_proof(
    *, booking, image=None, channel: str = "", reference: str = "", note: str = ""
) -> DepositProof:
    """Enregistre la preuve envoyee par la cliente et reveille le salon.

    Le rendez-vous passe de « en attente de paiement » a « demandee » : la
    balle est desormais dans le camp du salon. Rien n'est confirme - la
    cliente dit avoir paye, c'est tout ce que nous savons.
    """
    if booking.status not in (
        Booking.Status.PENDING_PAYMENT,
        Booking.Status.REQUESTED,
    ):
        raise PaymentRefused(
            "Ce rendez-vous n'attend plus de versement."
            if booking.status != Booking.Status.CANCELLED
            else "Ce rendez-vous a été annulé. Reprenez une réservation."
        )

    proof, _created = DepositProof.objects.update_or_create(
        booking=booking,
        defaults={
            "tenant_id": booking.tenant_id,
            "image": image,
            "channel": channel,
            "reference": reference.strip(),
            "note": note.strip(),
            "status": DepositProof.Status.SUBMITTED,
            # Un nouvel envoi efface le refus precedent : la cliente a
            # corrige, le salon doit regarder a neuf.
            "reviewed_at": None,
            "reviewed_by": None,
            "rejection_reason": "",
        },
    )

    if booking.status == Booking.Status.PENDING_PAYMENT:
        booking.status = Booking.Status.REQUESTED
        booking.save(update_fields=["status", "updated_at"])

    AuditLog.objects.create(
        tenant_id=booking.tenant_id,
        action=AuditLog.Action.BOOKING_STATUS_CHANGED,
        resource_type="booking",
        resource_id=str(booking.id),
        metadata={"deposit_proof": "submitted", "channel": channel},
    )

    # Le salon est prevenu tout de suite : un acompte verse sans que personne
    # ne regarde, c'est une cliente qui attend devant un telephone muet.
    from apps.notifications.tasks import send_deposit_proof_alert

    send_deposit_proof_alert.delay(str(booking.id), str(booking.tenant_id))

    return proof


def accept(*, booking, actor, amount=None, method: str = "") -> Booking:
    """Le salon confirme avoir recu l'argent **et** pouvoir assurer la prestation.

    Les deux en un seul geste, volontairement. Les separer aurait permis
    d'encaisser un acompte pour un creneau qu'on ne peut pas tenir, ce qui
    est la pire issue possible pour la cliente : elle a paye et elle n'aura
    rien.
    """
    if booking.status not in (
        Booking.Status.REQUESTED,
        Booking.Status.PENDING_PAYMENT,
    ):
        raise PaymentRefused("Ce rendez-vous n'est plus en attente d'acceptation.")

    proof = getattr(booking, "deposit_proof", None)
    if proof is not None:
        proof.status = DepositProof.Status.ACCEPTED
        proof.reviewed_at = timezone.now()
        proof.reviewed_by = actor if getattr(actor, "is_authenticated", False) else None
        proof.save(update_fields=["status", "reviewed_at", "reviewed_by"])

    received = amount if amount is not None else booking.deposit_amount
    if received and received > 0:
        booking.deposit_paid = True
        booking.deposit_paid_at = timezone.now()
        booking.deposit_received = received
        booking.deposit_method = method or (proof.channel if proof else "") or "other"

    booking.status = Booking.Status.CONFIRMED
    booking.save(
        update_fields=[
            "status",
            "deposit_paid",
            "deposit_paid_at",
            "deposit_received",
            "deposit_method",
            "updated_at",
        ]
    )

    # L'acompte entre en caisse le jour ou il est constate.
    if booking.deposit_paid:
        from apps.finance.services import record_deposit_income

        record_deposit_income(booking)

    AuditLog.objects.create(
        tenant_id=booking.tenant_id,
        actor_user=actor if getattr(actor, "is_authenticated", False) else None,
        action=AuditLog.Action.BOOKING_STATUS_CHANGED,
        resource_type="booking",
        resource_id=str(booking.id),
        metadata={"accepted": True, "deposit_received": str(booking.deposit_received)},
    )

    from apps.notifications.tasks import send_booking_accepted

    send_booking_accepted.delay(str(booking.id), str(booking.tenant_id))

    return booking


def reject_proof(*, booking, actor, reason: str = "") -> DepositProof:
    """Le salon ne retrouve pas le versement.

    Le rendez-vous **ne s'annule pas** : il retourne en attente de paiement.
    Une capture floue, un mauvais compte, un decalage de quelques minutes -
    tout cela se corrige, et annuler seche ferait perdre une cliente qui a
    peut-etre reellement paye.
    """
    proof = getattr(booking, "deposit_proof", None)
    if proof is None:
        raise PaymentRefused("Aucune preuve n'a été envoyée pour ce rendez-vous.")

    proof.status = DepositProof.Status.REJECTED
    proof.reviewed_at = timezone.now()
    proof.reviewed_by = actor if getattr(actor, "is_authenticated", False) else None
    proof.rejection_reason = reason.strip()
    proof.save(
        update_fields=["status", "reviewed_at", "reviewed_by", "rejection_reason"]
    )

    booking.status = Booking.Status.PENDING_PAYMENT
    booking.save(update_fields=["status", "updated_at"])

    AuditLog.objects.create(
        tenant_id=booking.tenant_id,
        actor_user=actor if getattr(actor, "is_authenticated", False) else None,
        action=AuditLog.Action.BOOKING_STATUS_CHANGED,
        resource_type="booking",
        resource_id=str(booking.id),
        metadata={"deposit_proof": "rejected", "reason": reason},
    )

    from apps.notifications.tasks import send_deposit_rejected

    send_deposit_rejected.delay(str(booking.id), str(booking.tenant_id))

    return proof




def expirer(booking, now=None) -> bool:
    """Annule ce rendez-vous si son delai de reglement est passe.

    Renvoie True quand la transition a eu lieu. Idempotente : rappelee sur
    un rendez-vous deja annule, deja paye, ou dont la preuve est arrivee,
    elle ne fait rien.

    -----------------------------------------------------------------------
    Pourquoi cette regle doit pouvoir s'appliquer a la lecture
    -----------------------------------------------------------------------

    Elle ne vivait que dans le balayage Celery, toutes les cinq minutes. Le
    reste du produit se contentait de *calculer* l'etat a l'affichage - la
    page de reglement disait « delai depasse » a la seconde pres, sans rien
    changer en base.

    Tant que le balayage tourne, l'ecart se compte en minutes et personne ne
    le voit. Des qu'il ne tourne pas - poste de developpement sans worker,
    file bloquee, redemarrage rate -, l'ecart n'a plus de fin : le
    rendez-vous reste « en attente de paiement » pour toujours. L'espace
    cliente continue d'afficher « Un acompte reste a regler » et son bouton
    mene a « le delai est depasse ». On invite quelqu'un a payer, et on lui
    ferme la porte au nez.

    Trois rendez-vous etaient dans cet etat sur cette base, dont un depuis
    vingt-deux heures.

    La transition est donc declenchee aussi la ou l'etat est lu. Ecrire
    pendant une lecture ne se fait pas a la legere : c'est acceptable ici
    parce que l'ecriture est idempotente, bornee aux rendez-vous deja
    echus, et qu'elle applique exactement la meme regle que le balayage -
    celui-ci reste la voie normale, et la seule qui libere un creneau quand
    plus personne ne regarde la page.
    """
    now = now or timezone.now()

    if booking.status != Booking.Status.PENDING_PAYMENT:
        return False
    # Une preuve deja envoyee suspend le compte a rebours : le rendez-vous
    # n'attend plus la cliente, il attend le salon.
    if getattr(booking, "deposit_proof", None) is not None:
        return False

    deadline = booking.created_at + PAYMENT_WINDOW
    if now < deadline:
        return False

    # -----------------------------------------------------------------
    # La bascule se joue dans la base, pas en memoire
    # -----------------------------------------------------------------
    #
    # `give_back_stock` ajoute `stock + quantite` : ce n'est pas idempotent.
    # Deux appels rendent la marchandise deux fois, et le salon croit avoir
    # des meches qu'il n'a pas.
    #
    # Le test ci-dessus lit un objet deja charge. Deux lectures simultanees
    # - deux onglets, la page de suivi et l'espace cliente, ou une lecture
    # qui croise le balayage Celery - le franchissent donc toutes les deux
    # avant que l'une ait ecrit. Tant que l'expiration ne vivait que dans le
    # balayage, la fenetre etait etroite ; depuis qu'un simple affichage la
    # declenche, elle s'ouvre a chaque chargement de page.
    #
    # L'`UPDATE` conditionnel tranche : la base ne laisse passer qu'un seul
    # ecrivain, et seul celui qui a gagne rend les articles.
    gagne = Booking.objects.filter(
        pk=booking.pk, status=Booking.Status.PENDING_PAYMENT
    ).update(
        status=Booking.Status.CANCELLED,
        cancelled_at=now,
        cancellation_reason=MOTIF_EXPIRATION,
        # `update()` court-circuite `auto_now` : sans cette ligne, la fiche
        # garderait la date de sa derniere modification par un humain.
        updated_at=now,
    )
    if not gagne:
        return False

    # L'objet en memoire suit, pour que l'appelant lise l'etat reel.
    booking.status = Booking.Status.CANCELLED
    booking.cancelled_at = now
    booking.cancellation_reason = MOTIF_EXPIRATION

    # Les articles reserves retournent en rayon.
    from apps.store.services import give_back_stock

    give_back_stock(booking)
    return True


def release_expired(now=None) -> int:
    """Rend les creneaux que personne n'a payes.

    Sans cela, fermer l'onglet de la page de paiement gelerait un creneau de
    quatre heures pour toujours. Seuls les rendez-vous restes **sans aucune
    preuve** expirent : une cliente qui a envoye sa capture attend le salon,
    pas l'inverse, et lui reprendre son creneau serait injuste.

    La transition elle-meme vit dans `expirer` : c'est la meme, qu'elle soit
    declenchee par ce balayage ou par la lecture d'une page. Deux copies de
    cette regle finiraient par diverger, et la divergence porterait sur
    « ce rendez-vous existe-t-il encore ».
    """
    now = now or timezone.now()
    deadline = now - PAYMENT_WINDOW

    stale = Booking.objects.filter(
        status=Booking.Status.PENDING_PAYMENT,
        created_at__lt=deadline,
        deposit_proof__isnull=True,
    )

    return sum(1 for booking in stale if expirer(booking, now))
