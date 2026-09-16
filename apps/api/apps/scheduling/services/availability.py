"""Moteur de creneaux.

Chaine de calcul, pour un prestataire et une plage de dates :

    horaires recurrents du jour (heure locale du salon)
        - conges et blocages
        + ouvertures exceptionnelles
        - reservations actives, elargies du temps de battement
        = intervalles libres
        -> fenetre glissante de la duree de la prestation, au pas configure

Deux regles non negociables :

- Le navigateur ne decide de rien. Cette fonction est la seule source de
  verite sur les disponibilites, et elle est rejouee au moment de la
  reservation (voir booking.py).
- Tout est calcule en UTC ; le fuseau du salon ne sert qu'a savoir a quel
  moment reel correspond « lundi 9h ». C'est ce qui permet a un salon de
  Guangzhou et un de Kinshasa de coexister dans la meme base.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db.models import Q
from django.utils import timezone

from apps.salons.models import SalonProfile
from apps.scheduling.models import (
    BLOCKING_BOOKING_STATUSES,
    AvailabilityException,
    Booking,
    BusinessHours,
)

from .intervals import Interval, merge, saturated, subtract


@dataclass(frozen=True)
class Slot:
    starts_at: datetime  # UTC
    ends_at: datetime  # UTC
    staff_member_id: str


@dataclass(frozen=True)
class SchedulingRules:
    """Parametres de reservation du salon, avec des valeurs de repli si le
    profil n'a pas encore ete rempli."""

    timezone: ZoneInfo
    granularity: timedelta
    buffer: timedelta
    min_lead_time: timedelta
    max_advance: timedelta

    @classmethod
    def for_tenant(cls, tenant) -> "SchedulingRules":
        profile = SalonProfile.objects.filter(tenant=tenant).first()
        return cls(
            timezone=ZoneInfo(tenant.timezone),
            granularity=timedelta(minutes=profile.slot_granularity_minutes if profile else 15),
            buffer=timedelta(minutes=profile.buffer_minutes if profile else 0),
            min_lead_time=timedelta(minutes=profile.min_lead_time_minutes if profile else 120),
            max_advance=timedelta(days=profile.max_advance_days if profile else 90),
        )


def _local_datetime(day: date, moment: time, tz: ZoneInfo) -> datetime:
    """Combine une date locale et une heure locale en instant absolu.

    Aux changements d'heure, Python retient fold=0 : l'heure « premiere
    occurrence » pour une heure ambigue. Les marches vises (Congo, RDC,
    Chine) ne pratiquent pas l'heure d'ete, mais un salon europeen le ferait,
    d'ou le passage explicite par zoneinfo plutot qu'un decalage fixe.
    """
    return datetime.combine(day, moment, tzinfo=tz)


def _opening_intervals(
    *,
    staff_member_id: str,
    days: list[date],
    rules: SchedulingRules,
    hours_by_staff: dict[str | None, list[BusinessHours]],
) -> list[Interval]:
    """Horaires d'ouverture applicables, convertis en instants UTC.

    Un prestataire qui a ses propres horaires les utilise ; sinon il herite
    de ceux du salon. Sans ce repli, chaque equipe devrait ressaisir la meme
    grille pour chaque personne.
    """
    rows = hours_by_staff.get(staff_member_id) or hours_by_staff.get(None) or []
    if not rows:
        return []

    intervals: list[Interval] = []
    for day in days:
        for row in rows:
            if row.weekday != day.weekday():
                continue
            start = _local_datetime(day, row.starts_at, rules.timezone)
            end = _local_datetime(day, row.ends_at, rules.timezone)
            if end > start:
                intervals.append(Interval(start, end))

    return merge(intervals)


def _aligned_start(
    moment: datetime, rules: SchedulingRules, anchor: datetime | None = None
) -> datetime:
    """Arrondit vers le haut sur la grille de la plage d'ouverture.

    -----------------------------------------------------------------------
    Pourquoi l'ancre est le debut de la plage, et non minuit
    -----------------------------------------------------------------------

    La grille etait calee sur l'horloge depuis minuit : :00, :30, :15 selon
    le pas. Un salon qui ouvre a 9 h 30 avec un pas d'une heure ne se voyait
    donc jamais proposer 9 h 30 - le premier creneau tombait a 10 h. Trente
    minutes invendables par jour, alors que l'heure etait affichee comme
    ouverte sur son propre mini-site.

    En ancrant la grille au debut de la plage, l'ouverture est toujours le
    premier creneau : 9 h 30, 10 h 30, 11 h 30.

    -----------------------------------------------------------------------
    Ce que cela ne casse pas
    -----------------------------------------------------------------------

    La raison d'etre de l'alignement reste entiere. Un rendez-vous qui finit
    a 14 h 07 ouvre un intervalle libre a 14 h 07 ; l'ancre est celle de la
    *plage* (14 h), donc le creneau suivant tombe a 15 h, jamais a 14 h 07.
    On ne propose toujours pas d'heures batardes - on propose simplement
    l'heure d'ouverture, qui n'en est pas une.

    Sans ancre - appel hors d'une plage connue - on retombe sur minuit,
    c'est-a-dire le comportement d'avant.
    """
    local = moment.astimezone(rules.timezone)

    if anchor is None:
        origin = datetime.combine(local.date(), time(0, 0), tzinfo=rules.timezone)
    else:
        origin = anchor.astimezone(rules.timezone)

    step = int(rules.granularity.total_seconds())
    elapsed = int((local - origin).total_seconds())

    # Un instant anterieur a l'ancre n'a rien a arrondir : la plage commence
    # la, et c'est deja un point de grille.
    if elapsed <= 0:
        return origin.astimezone(moment.tzinfo or origin.tzinfo)

    remainder = elapsed % step
    if remainder:
        local = local + timedelta(seconds=step - remainder)
    return local.astimezone(moment.tzinfo or local.tzinfo)


def _slots_in(
    interval: Interval,
    duration: timedelta,
    rules: SchedulingRules,
    anchor: datetime | None = None,
) -> list[datetime]:
    starts: list[datetime] = []
    cursor = _aligned_start(interval.start, rules, anchor)
    while cursor + duration <= interval.end:
        starts.append(cursor)
        cursor = cursor + rules.granularity
    return starts


def _anchor_for(moment: datetime, openings: list[Interval]) -> datetime | None:
    """Debut de la plage d'ouverture qui contient cet instant.

    Les intervalles libres naissent d'une soustraction : ils ont perdu la
    trace de la plage dont ils viennent. On la retrouve ici, puisque c'est
    elle qui porte la grille.
    """
    for opening in openings:
        if opening.start <= moment < opening.end:
            return opening.start
    return None


def available_slots(
    *,
    tenant,
    service,
    staff_members,
    date_from: date,
    date_to: date,
    extra_minutes: int = 0,
    now: datetime | None = None,
) -> list[Slot]:
    """Creneaux reservables pour une prestation, sur une plage de dates.

    `staff_members` est la liste des prestataires eligibles : le filtrage par
    competence (StaffService) est fait par l'appelant, qui sait aussi si la
    cliente a choisi une personne precise ou « peu importe ».

    `extra_minutes` est le temps ajoute par les options retenues. Il entre
    ici, dans la duree qui sert a decouper les intervalles libres, et non
    seulement dans l'affichage : une pose XL qui demande quarante-cinq
    minutes de plus ne doit pas se voir proposer un creneau de quatre heures
    qui ne la contient pas. C'est tout l'interet de faire passer les options
    par le moteur plutot que par la facture.
    """
    if not staff_members:
        return []

    now = now or timezone.now()
    rules = SchedulingRules.for_tenant(tenant)
    duration = timedelta(minutes=service.duration_minutes + max(0, extra_minutes))

    earliest = now + rules.min_lead_time
    latest = now + rules.max_advance

    days = _date_range(date_from, date_to)
    if not days:
        return []

    # Une marge d'un jour de chaque cote : un rendez-vous commence le 3 a 23h
    # et deborde sur le 4, et l'ouverture locale du 3 peut tomber le 2 en UTC.
    window = Interval(
        _local_datetime(days[0], time(0, 0), rules.timezone) - timedelta(days=1),
        _local_datetime(days[-1], time(0, 0), rules.timezone) + timedelta(days=2),
    )

    # Ressources comptees : un fauteuil libre ne suffit pas s'il n'y a plus
    # de bac. Le blocage vaut pour tout le salon, pas par prestataire, donc
    # il est calcule une seule fois.
    resource_blocks = _saturated_resources(tenant, service, window, rules)

    staff_ids = [str(member.id) for member in staff_members]
    hours_by_staff = _load_business_hours(tenant, staff_ids)
    exceptions_by_staff = _load_exceptions(tenant, staff_ids, window)
    busy_by_staff = _load_busy(tenant, staff_ids, window, rules)

    slots: list[Slot] = []
    for member in staff_members:
        member_id = str(member.id)

        closed, extra = exceptions_by_staff.get(member_id, ([], []))

        # Les ouvertures exceptionnelles sont ajoutees avant de decider qu'il
        # n'y a rien : leur raison d'etre est justement d'ouvrir un jour
        # ferme, ou aucun horaire recurrent n'existe.
        open_intervals = merge(
            _opening_intervals(
                staff_member_id=member_id,
                days=days,
                rules=rules,
                hours_by_staff=hours_by_staff,
            )
            + extra
        )
        if not open_intervals:
            continue

        open_intervals = subtract(open_intervals, closed)
        free = subtract(open_intervals, busy_by_staff.get(member_id, []))
        if resource_blocks:
            free = subtract(free, resource_blocks)

        for interval in free:
            anchor = _anchor_for(interval.start, open_intervals)
            for start in _slots_in(interval, duration, rules, anchor):
                if start < earliest or start > latest:
                    continue
                slots.append(
                    Slot(
                        starts_at=start.astimezone(ZoneInfo("UTC")),
                        ends_at=(start + duration).astimezone(ZoneInfo("UTC")),
                        staff_member_id=member_id,
                    )
                )

    slots.sort(key=lambda s: (s.starts_at, s.staff_member_id))
    return slots


def is_slot_available(
    *,
    tenant,
    service,
    staff_member,
    starts_at: datetime,
    extra_minutes: int = 0,
    now: datetime | None = None,
) -> bool:
    """Revalidation ponctuelle, appelee au moment de reserver.

    Le calcul complet est refait pour la seule journee concernee : c'est peu
    couteux et cela evite de faire confiance a ce que le navigateur renvoie.

    `extra_minutes` doit valoir ce qu'il valait a l'affichage des creneaux :
    revalider une pose XL avec la duree de base laisserait passer un
    rendez-vous qui deborde sur le suivant - le controle serait plus laxiste
    que la proposition, ce qui n'a aucun sens.
    """
    local_day = starts_at.astimezone(ZoneInfo(tenant.timezone)).date()
    slots = available_slots(
        tenant=tenant,
        service=service,
        staff_members=[staff_member],
        date_from=local_day,
        date_to=local_day,
        extra_minutes=extra_minutes,
        now=now,
    )
    return any(slot.starts_at == starts_at for slot in slots)


# ---------------------------------------------------------------------------
# Chargements
# ---------------------------------------------------------------------------


def _saturated_resources(tenant, service, window: Interval, rules) -> list[Interval]:
    """Moments ou une ressource exigee par `service` est deja toute prise.

    Ne charge rien si la prestation n'exige aucune ressource - c'est le cas
    de la plupart, et cela evite deux requetes sur chaque recherche de
    creneau.
    """
    from apps.catalog.models import ServiceResource

    required = list(
        ServiceResource.objects.filter(service=service, resource__active=True)
        .select_related("resource")
        .values_list("resource_id", "resource__capacity")
    )
    if not required:
        return []

    resource_ids = [resource_id for resource_id, _ in required]

    # Tous les rendez-vous actifs qui mobilisent l'une de ces ressources,
    # quel que soit le prestataire : c'est le salon entier qui partage le
    # bac, pas une personne.
    competing = Booking.objects.filter(
        status__in=BLOCKING_BOOKING_STATUSES,
        starts_at__lt=window.end,
        ends_at__gt=window.start,
        service__resource_links__resource_id__in=resource_ids,
    ).values_list("service__resource_links__resource_id", "starts_at", "ends_at")

    used: dict = {}
    for resource_id, starts_at, ends_at in competing:
        # Le battement compte aussi pour une ressource : un bac doit etre
        # rince entre deux clientes.
        used.setdefault(resource_id, []).append(
            Interval(starts_at, ends_at).expanded(rules.buffer, rules.buffer)
        )

    blocks: list[Interval] = []
    for resource_id, capacity in required:
        blocks.extend(saturated(used.get(resource_id, []), capacity))

    return merge(blocks)


def _date_range(date_from: date, date_to: date) -> list[date]:
    if date_to < date_from:
        return []
    span = (date_to - date_from).days
    return [date_from + timedelta(days=offset) for offset in range(span + 1)]


def _load_business_hours(tenant, staff_ids: list[str]) -> dict[str | None, list[BusinessHours]]:
    rows = BusinessHours.objects.filter(tenant=tenant).filter(
        _staff_or_salon_q(staff_ids)
    )
    grouped: dict[str | None, list[BusinessHours]] = {}
    for row in rows:
        key = str(row.staff_member_id) if row.staff_member_id else None
        grouped.setdefault(key, []).append(row)
    return grouped


def _staff_or_salon_q(staff_ids: list[str]):
    """Horaires propres au prestataire, sinon ceux du salon."""
    return Q(staff_member_id__in=staff_ids) | Q(staff_member__isnull=True)


def _load_exceptions(
    tenant, staff_ids: list[str], window: Interval
) -> dict[str, tuple[list[Interval], list[Interval]]]:
    """Renvoie, par prestataire, (intervalles fermes, ouvertures en plus)."""
    rows = (
        AvailabilityException.objects.filter(tenant=tenant)
        .filter(_staff_or_salon_q(staff_ids))
        .filter(starts_at__lt=window.end, ends_at__gt=window.start)
    )

    result: dict[str, tuple[list[Interval], list[Interval]]] = {
        staff_id: ([], []) for staff_id in staff_ids
    }

    for row in rows:
        interval = Interval(row.starts_at, row.ends_at)
        # Une exception sans prestataire vise tout le salon.
        targets = [str(row.staff_member_id)] if row.staff_member_id else staff_ids
        for target in targets:
            if target not in result:
                continue
            closed, extra = result[target]
            if row.kind == AvailabilityException.Kind.EXTRA_OPENING:
                extra.append(interval)
            else:
                closed.append(interval)

    return result


def _load_busy(
    tenant, staff_ids: list[str], window: Interval, rules: SchedulingRules
) -> dict[str, list[Interval]]:
    rows = Booking.objects.filter(
        tenant=tenant,
        staff_member_id__in=staff_ids,
        status__in=BLOCKING_BOOKING_STATUSES,
        starts_at__lt=window.end,
        ends_at__gt=window.start,
    ).values_list("staff_member_id", "starts_at", "ends_at")

    grouped: dict[str, list[Interval]] = {staff_id: [] for staff_id in staff_ids}
    for staff_member_id, starts_at, ends_at in rows:
        # Le temps de battement est ajoute des deux cotes : il doit exister
        # aussi bien avant qu'apres un rendez-vous existant.
        grouped[str(staff_member_id)].append(
            Interval(starts_at, ends_at).expanded(rules.buffer, rules.buffer)
        )
    return grouped
