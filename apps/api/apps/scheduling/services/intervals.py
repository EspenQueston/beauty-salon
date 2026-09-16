"""Arithmetique d'intervalles temporels.

Fonctions pures, sans acces base : c'est la partie du moteur de creneaux qui
se teste sans monter un salon complet, et celle ou se cachent la plupart des
bugs de disponibilite.

Convention : tous les intervalles sont semi-ouverts [start, end). Deux
rendez-vous qui se touchent (14h-15h puis 15h-16h) ne se chevauchent donc
pas, ce qui correspond a la contrainte tstzrange '[)' cote base.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True, order=True)
class Interval:
    start: datetime
    end: datetime

    def __post_init__(self):
        if self.end <= self.start:
            raise ValueError("Un intervalle doit finir apres son debut.")

    @property
    def duration(self) -> timedelta:
        return self.end - self.start

    def overlaps(self, other: "Interval") -> bool:
        return self.start < other.end and other.start < self.end

    def expanded(self, before: timedelta, after: timedelta) -> "Interval":
        return Interval(self.start - before, self.end + after)


def merge(intervals: list[Interval]) -> list[Interval]:
    """Fusionne les intervalles qui se chevauchent ou se touchent."""
    if not intervals:
        return []

    ordered = sorted(intervals, key=lambda i: (i.start, i.end))
    merged = [ordered[0]]

    for current in ordered[1:]:
        last = merged[-1]
        if current.start <= last.end:
            if current.end > last.end:
                merged[-1] = Interval(last.start, current.end)
        else:
            merged.append(current)

    return merged


def subtract(base: list[Interval], holes: list[Interval]) -> list[Interval]:
    """Retire `holes` de `base` et renvoie ce qui reste."""
    remaining = merge(base)
    if not remaining:
        return []

    for hole in merge(holes):
        result: list[Interval] = []
        for piece in remaining:
            if not piece.overlaps(hole):
                result.append(piece)
                continue
            # Le trou peut couper le morceau en deux, le raboter d'un cote,
            # ou le faire disparaitre entierement.
            if piece.start < hole.start:
                result.append(Interval(piece.start, hole.start))
            if hole.end < piece.end:
                result.append(Interval(hole.end, piece.end))
        remaining = result
        if not remaining:
            break

    return remaining


def saturated(intervals: list[Interval], capacity: int) -> list[Interval]:
    """Moments ou au moins `capacity` intervalles se superposent.

    Sert aux ressources comptees : avec deux bacs a shampooing, un creneau
    n'est bloque que lorsque *deux* lavages se chevauchent deja. Un seul
    lavage en cours ne bloque rien.

    Balayage par evenements plutot que comparaison deux a deux : le cout est
    en n log n, et surtout le resultat est exact quand trois rendez-vous se
    recouvrent partiellement - cas ou une comparaison par paires se trompe.

    Renvoie des intervalles fusionnes, tries.
    """
    if capacity <= 0:
        # Une ressource sans exemplaire disponible bloque tout ce qui la
        # demande : c'est le seul sens raisonnable a donner a zero.
        return merge(intervals)
    if len(intervals) < capacity:
        return []

    # +1 a chaque debut, -1 a chaque fin. Les fins sont traitees avant les
    # debuts a instant egal : deux rendez-vous qui se touchent (14h-15h puis
    # 15h-16h) ne se chevauchent pas.
    events: list[tuple[datetime, int]] = []
    for interval in intervals:
        events.append((interval.start, 1))
        events.append((interval.end, -1))
    events.sort(key=lambda event: (event[0], event[1]))

    blocked: list[Interval] = []
    depth = 0
    opened_at: datetime | None = None

    for moment, delta in events:
        was_full = depth >= capacity
        depth += delta
        is_full = depth >= capacity

        if is_full and not was_full:
            opened_at = moment
        elif was_full and not is_full and opened_at is not None:
            if moment > opened_at:
                blocked.append(Interval(opened_at, moment))
            opened_at = None

    return merge(blocked)
