"""Creation et cycle de vie des reservations.

Trois protections se superposent contre la double reservation, de la plus
faible a la plus forte :

1. Le frontend n'affiche que des creneaux calcules par l'API.
2. Ce service revalide la disponibilite *dans* la transaction.
3. PostgreSQL refuse l'insertion via la contrainte d'exclusion.

Seule la troisieme resiste a deux clientes qui valident a la meme seconde.
Les deux premieres existent pour que le cas normal donne un message clair
plutot qu'une erreur de base.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from django.core.cache import cache
from django.db import IntegrityError, OperationalError, transaction
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.common.exceptions import SlotUnavailable
from apps.customers.models import Customer
from apps.salons.models import ServiceMode
from apps.scheduling.models import Booking
from apps.staff.models import StaffService

from .availability import available_slots, is_slot_available

logger = logging.getLogger(__name__)

IDEMPOTENCY_TTL = 60 * 60 * 24


class BookingRefused(Exception):
    """Demande invalide, sans rapport avec la concurrence."""


@dataclass
class CustomerDetails:
    full_name: str
    phone: str
    email: str = ""
    contact_preference: str = Customer.ContactPreference.WHATSAPP
    marketing_consent: bool = False


# Les deux façons dont PostgreSQL refuse un créneau déjà pris.
CRENEAU_PRIS = (IntegrityError, OperationalError)

# 40P01 : « deadlock detected ». Le code SQLSTATE plutôt que le message, qui
# est traduit selon la locale du serveur.
DEADLOCK = "40P01"


def est_un_conflit_de_creneau(exc: Exception) -> bool:
    """Cette erreur dit-elle « quelqu'un a pris ce créneau avant vous » ?

    -----------------------------------------------------------------------
    Pourquoi un interblocage compte comme un conflit
    -----------------------------------------------------------------------

    Deux insertions simultanées sur un créneau qui se chevauche ne se soldent
    pas toujours par une violation de contrainte. La vérification de la
    contrainte d'exclusion prend des verrous, et quand les deux transactions
    les prennent en sens inverse, PostgreSQL tranche en tuant l'une des deux :
    elle reçoit `deadlock detected`, pas `IntegrityError`.

    Du point de vue du produit, c'est **le même événement** - une cliente a
    perdu la course. Ne pas le reconnaître laissait l'exception remonter
    jusqu'à une erreur 500, là où l'autre cas affichait proprement « ce
    créneau vient d'être pris, en voici d'autres ». Le cas est rare, mais
    c'est précisément le chemin que la contrainte d'exclusion existe pour
    protéger.

    Toute autre `OperationalError` - connexion coupée, base arrêtée - n'a
    rien à voir avec un créneau et doit continuer de remonter telle quelle.
    """
    if isinstance(exc, IntegrityError):
        return True
    return getattr(exc.__cause__, "sqlstate", None) == DEADLOCK


def create_booking(
    *,
    tenant,
    service,
    staff_member,
    starts_at: datetime,
    customer: CustomerDetails,
    source: str = Booking.Source.WEB,
    customer_note: str = "",
    options=(),
    items=(),
    travel_zone=None,
    address: str = "",
    idempotency_key: str | None = None,
    actor=None,
    # La langue de lecture du mini-site au moment de la reservation. Elle ne
    # sert qu aux e-mails, mais elle se perd si on ne la retient pas ici.
    language: str = "fr",
) -> Booking:
    if idempotency_key:
        existing = replay_booking(tenant, idempotency_key)
        if existing is not None:
            return existing

    if not service.active:
        raise BookingRefused("Cette prestation n'est plus proposée.")
    if not staff_member.active:
        raise BookingRefused("Ce prestataire n'accepte plus de rendez-vous.")

    can_perform = StaffService.objects.filter(
        tenant=tenant, staff_member=staff_member, service=service
    ).exists()
    if not can_perform:
        raise BookingRefused("Ce prestataire ne réalise pas cette prestation.")

    # Revalidation : ce que le navigateur a envoye peut dater de plusieurs
    # minutes, ou avoir ete fabrique a la main.
    # Les options allongent la prestation : la revalidation doit porter sur la
    # duree reellement demandee, sinon le controle serait plus permissif que
    # ce qui a ete propose a la cliente.
    extra_minutes = sum(option.duration_delta_minutes for option in options)
    options_amount = sum(
        (option.price_delta for option in options), start=Decimal("0")
    )

    if not is_slot_available(
        tenant=tenant,
        service=service,
        staff_member=staff_member,
        starts_at=starts_at,
        extra_minutes=extra_minutes,
    ):
        raise SlotUnavailable(
            extra={"alternatives": _alternatives(tenant, service, staff_member, starts_at)}
        )

    ends_at = starts_at + timedelta(minutes=service.duration_minutes + extra_minutes)


    customer_row = _upsert_customer(tenant, customer)

    # Les frais de deplacement entrent dans le total annonce, pas a cote.
    #
    # Deux montants separes obligeraient la cliente a faire l'addition, et
    # c'est exactement la ou naissent les contestations a l'arrivee. Le detail
    # reste garde a part pour le salon, qui a besoin de savoir ce qui relevait
    # de la prestation et ce qui relevait du trajet.
    from apps.store.services import items_total, snapshot, take_stock

    items_amount = items_total(items)

    travel_fee = travel_zone.fee_amount if travel_zone else Decimal("0")
    total = service.price_amount + options_amount + items_amount + travel_fee

    # L'acompte suit le panier, au lieu de rester fige sur la prestation.
    # Le detail de la regle vit dans `deposit.py` : le temps a un taux, la
    # marchandise en entier, le trajet pas du tout.
    from apps.payments.services import channels_for
    from apps.salons.models import SalonProfile

    from .deposit import compute_deposit

    profile = SalonProfile.objects.filter(tenant=tenant).first()
    deposit_due = compute_deposit(
        service_amount=service.price_amount,
        options_amount=options_amount,
        items_amount=items_amount,
        travel_amount=travel_fee,
        requires_deposit=bool(service.requires_deposit),
        rate=getattr(profile, "deposit_rate", 0) or 0,
        minimum=getattr(profile, "deposit_minimum", None) or Decimal("0"),
        covers_items=getattr(profile, "deposit_covers_items", True),
        currency=tenant.currency,
    )

    try:
        # Bloc imbrique : en cas de violation de contrainte, seul ce
        # savepoint est annule et la transaction de la requete survit.
        with transaction.atomic():
            booking = Booking.objects.create(
                tenant=tenant,
                customer=customer_row,
                staff_member=staff_member,
                service=service,
                starts_at=starts_at,
                ends_at=ends_at,
                # « En attente de paiement » quand un acompte est du et que
                # le salon a un moyen de l'encaisser. Le creneau reste bloque
                # pendant ce temps : une cliente qui cherche son mot de passe
                # WeChat ne doit pas se le faire prendre.
                status=(
                    Booking.Status.PENDING_PAYMENT
                    if deposit_due > 0 and channels_for(tenant.id)
                    else Booking.Status.REQUESTED
                ),
                source=source,
                language=language,
                service_name=service.name,
                total_amount=total,
                # Instantane : renommer ou retarifer une option demain ne
                # doit pas reecrire ce qui a ete vendu aujourd'hui.
                options_snapshot=[
                    {
                        "name": option.name,
                        "price": str(option.price_delta),
                        "minutes": option.duration_delta_minutes,
                    }
                    for option in options
                ],
                options_amount=options_amount,
                items_snapshot=snapshot(items),
                items_amount=items_amount,
                deposit_amount=deposit_due,
                # Une zone choisie veut dire « chez moi », meme pour une
                # prestation proposee dans les deux lieux.
                location_mode=(
                    ServiceMode.HOME if travel_zone else service.location_mode
                ),
                address=address,
                travel_zone_name=travel_zone.name if travel_zone else "",
                travel_fee_amount=travel_fee,
                customer_note=customer_note,
            )
    except CRENEAU_PRIS as exc:
        if not est_un_conflit_de_creneau(exc):
            raise
        # Une autre reservation a gagne la course entre la revalidation et
        # l'insertion. C'est le cas que la contrainte d'exclusion existe pour
        # attraper.
        logger.info(
            "Conflit de creneau : tenant=%s staff=%s debut=%s",
            tenant.id,
            staff_member.id,
            starts_at,
        )
        raise SlotUnavailable(
            extra={"alternatives": _alternatives(tenant, service, staff_member, starts_at)}
        ) from None

    # Le stock part maintenant, la reservation etant acquise : entre elle et
    # la prestation il peut s'ecouler trois semaines, et la derniere perruque
    # serait sinon vendue deux fois. Apres l'insertion et non avant - une
    # course perdue ne doit pas decompter un article jamais vendu.
    take_stock(items)

    AuditLog.objects.create(
        tenant=tenant,
        actor_user=actor if actor and actor.is_authenticated else None,
        action=AuditLog.Action.BOOKING_CREATED,
        resource_type="booking",
        resource_id=str(booking.id),
        metadata={"starts_at": starts_at.isoformat(), "source": source},
    )

    if idempotency_key:
        cache.set(_idempotency_cache_key(tenant, idempotency_key), str(booking.id),
                  IDEMPOTENCY_TTL)

    return booking


def cancel_booking(
    *, booking: Booking, reason: str = "", actor=None, by_salon: bool = True
) -> Booking:
    if booking.status in (Booking.Status.CANCELLED, Booking.Status.COMPLETED):
        raise BookingRefused("Cette réservation ne peut plus être annulée.")

    booking.status = Booking.Status.CANCELLED
    booking.cancelled_at = timezone.now()
    booking.cancellation_reason = reason
    booking.save(update_fields=["status", "cancelled_at", "cancellation_reason", "updated_at"])

    # La marchandise reservee retourne en rayon. Un rendez-vous honore, lui,
    # ne la rend pas : elle est partie avec la cliente.
    from apps.store.services import give_back_stock

    give_back_stock(booking)

    # Personne n'etait prevenu jusqu'ici. Une cliente qui se deplace pour un
    # rendez-vous annule la veille est le pire resultat possible du produit,
    # et c'etait silencieux.
    from apps.notifications import evenements
    from apps.notifications.tasks import send_booking_cancelled

    send_booking_cancelled.delay(
        str(booking.id), str(booking.tenant_id), by_salon=by_salon
    )
    evenements.rendez_vous_annule(booking, par_le_salon=by_salon)

    AuditLog.objects.create(
        tenant_id=booking.tenant_id,
        actor_user=actor if actor and actor.is_authenticated else None,
        action=AuditLog.Action.BOOKING_CANCELLED,
        resource_type="booking",
        resource_id=str(booking.id),
        metadata={"reason": reason},
    )
    return booking


def reschedule_booking(*, booking: Booking, starts_at: datetime, actor=None) -> Booking:
    """Deplace un rendez-vous en revalidant le nouveau creneau."""
    tenant = booking.tenant
    previous = booking.starts_at

    # -----------------------------------------------------------------------
    # Un rendez-vous clos ne se deplace pas
    # -----------------------------------------------------------------------
    #
    # Rien ne l'interdisait. On pouvait donner une nouvelle date a une
    # prestation deja terminee - la recette etait deja comptabilisee, l'avis
    # deja demande - ou ressusciter une annulation en la posant ailleurs,
    # sans que la cliente, prevenue de l'annulation, n'en sache rien.
    #
    # `CHECKED_IN` est exclu aussi : la cliente est dans le fauteuil, il est
    # trop tard pour changer l'heure de son rendez-vous.
    if booking.status not in (
        Booking.Status.PENDING_PAYMENT,
        Booking.Status.REQUESTED,
        Booking.Status.CONFIRMED,
    ):
        raise BookingRefused("Ce rendez-vous ne peut plus être déplacé.")

    if not is_slot_available(
        tenant=tenant,
        service=booking.service,
        staff_member=booking.staff_member,
        starts_at=starts_at,
    ):
        raise SlotUnavailable(
            extra={
                "alternatives": _alternatives(
                    tenant, booking.service, booking.staff_member, starts_at
                )
            }
        )

    booking.starts_at = starts_at
    booking.ends_at = starts_at + timedelta(minutes=booking.service.duration_minutes)
    # Le rappel J-1 se rearme.
    #
    # `reminder_sent_at` est ce qui garantit un envoi unique. Laisse tel
    # quel apres un deplacement, il produisait le pire des deux cas : la
    # cliente avait recu un rappel pour l'ancienne date, et n'en recevrait
    # aucun pour la nouvelle.
    booking.reminder_sent_at = None

    try:
        with transaction.atomic():
            booking.save(
                update_fields=["starts_at", "ends_at", "reminder_sent_at", "updated_at"]
            )
    except CRENEAU_PRIS as exc:
        if not est_un_conflit_de_creneau(exc):
            raise
        raise SlotUnavailable() from None

    # La cliente doit l'apprendre, et pas en arrivant.
    #
    # Le deplacement etait silencieux : le salon changeait l'heure, la
    # cliente se presentait a l'ancienne. C'est exactement le defaut qu'on
    # avait corrige pour l'annulation, laisse ouvert a cote.
    from apps.notifications.tasks import send_booking_rescheduled

    send_booking_rescheduled.delay(
        str(booking.id), str(booking.tenant_id), previous.isoformat()
    )

    AuditLog.objects.create(
        tenant_id=booking.tenant_id,
        actor_user=actor if actor and actor.is_authenticated else None,
        action=AuditLog.Action.BOOKING_RESCHEDULED,
        resource_type="booking",
        resource_id=str(booking.id),
        metadata={"from": previous.isoformat(), "to": starts_at.isoformat()},
    )
    return booking


# ---------------------------------------------------------------------------
# Interne
# ---------------------------------------------------------------------------


def _upsert_customer(tenant, details: CustomerDetails) -> Customer:
    """Retrouve la cliente par telephone, ou la cree.

    Le telephone fait office d'identite : une meme personne qui reserve deux
    fois doit retrouver son historique, pas creer une seconde fiche.
    """
    customer, created = Customer.objects.get_or_create(
        tenant=tenant,
        phone=details.phone.strip(),
        defaults={
            "full_name": details.full_name.strip(),
            "email": details.email.strip(),
            "contact_preference": details.contact_preference,
            "marketing_consent": details.marketing_consent,
            "marketing_consent_at": timezone.now() if details.marketing_consent else None,
        },
    )

    if not created:
        changed = []
        if details.full_name and customer.full_name != details.full_name.strip():
            customer.full_name = details.full_name.strip()
            changed.append("full_name")
        if details.email and not customer.email:
            customer.email = details.email.strip()
            changed.append("email")
        # Le consentement s'ajoute mais ne se retire jamais implicitement :
        # le retirer demande une action explicite de la cliente.
        if details.marketing_consent and not customer.marketing_consent:
            customer.marketing_consent = True
            customer.marketing_consent_at = timezone.now()
            changed += ["marketing_consent", "marketing_consent_at"]
        if changed:
            customer.save(update_fields=[*changed, "updated_at"])

    return customer


def _alternatives(tenant, service, staff_member, around: datetime, limit: int = 4) -> list[str]:
    """Quelques creneaux proches, pour que le refus soit utile."""
    local_day = around.astimezone(timezone.get_current_timezone()).date()
    slots = available_slots(
        tenant=tenant,
        service=service,
        staff_members=[staff_member],
        date_from=local_day,
        date_to=local_day + timedelta(days=2),
    )
    slots.sort(key=lambda slot: abs(slot.starts_at - around))
    return [slot.starts_at.isoformat() for slot in slots[:limit]]


def _idempotency_cache_key(tenant, key: str) -> str:
    return f"booking:idem:{tenant.id}:{key}"


def replay_booking(tenant, key: str) -> Booking | None:
    """Reservation deja creee pour cette cle, si elle existe.

    Expose publiquement : la vue doit pouvoir repondre a un rejeu *avant*
    de tester la disponibilite, sinon un renvoi de requete apres succes
    recevrait un 409 « creneau pris » - par sa propre reservation.
    """
    booking_id = cache.get(_idempotency_cache_key(tenant, key))
    if not booking_id:
        return None
    return Booking.objects.filter(id=booking_id).first()
