"""Tout ce qu'affiche la page d'accueil du tableau de bord, en un appel.

---------------------------------------------------------------------------
Pourquoi une seule reponse
---------------------------------------------------------------------------

Cette page montre une douzaine de chiffres qui viennent de six tables. En
six appels, l'ecran s'assemble par morceaux pendant plusieurs secondes sur
un reseau mobile, et chaque morceau arrive avec sa propre latence : on voit
le nombre de clientes, puis les recettes, puis les avis. C'est exactement ce
qu'on ne veut pas d'un tableau de bord, dont l'interet est de tout donner
d'un coup d'oeil.

La synthese financiere suit deja ce principe (`transactions/summary`), pour
la meme raison.

---------------------------------------------------------------------------
Ce que ces chiffres promettent
---------------------------------------------------------------------------

Chacun repond a une question qu'une gerante se pose vraiment le matin :

  - **Aujourd'hui** : combien de rendez-vous, et combien ils representent.
  - **Ce qui attend** : acomptes a verifier, avis a moderer. Ce sont les
    seules lignes qui coutent quelque chose tant qu'on ne les traite pas.
  - **Le mois** : recettes, et la comparaison avec le mois precedent. Un
    chiffre seul ne dit pas s'il est bon.
  - **Les prestations qui marchent** : ce qu'on reconduit, ce qu'on retire.
  - **Ce que les clientes en pensent** : la repartition des notes, pas
    seulement la moyenne - une moyenne de 4 cache aussi bien « tout le monde
    est content » que « la moitie adore, l'autre deteste ».

Tous les calculs sont faits par la base. Additionner en memoire imposerait
de charger chaque ligne d'un salon qui tourne depuis deux ans.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db.models import Avg, Count, Sum
from django.utils import timezone

from apps.customers.models import Customer
from apps.finance.models import Transaction
from apps.reviews.models import Review
from apps.scheduling.models import Booking

# Fenetre des « prestations qui marchent » et du fil d'activite.
RECENT_DAYS = 30

# Nombre de prestations classees affichees. Au-dela, ce n'est plus un
# classement, c'est le catalogue.
TOP_SERVICES = 5

# Longueur du fil d'activite. Il se lit, il ne se depouille pas.
FEED_LENGTH = 8


def _money(value) -> str:
    return str(value or Decimal("0"))


def _day_bounds(tenant, moment=None):
    """Debut et fin du jour courant, dans le fuseau du salon.

    Le serveur vit en UTC ; « aujourd'hui » pour un salon de Brazzaville
    n'est pas la meme tranche que pour un salon de Guangzhou. Prendre la
    date du serveur ferait commencer la journee a la mauvaise heure pour
    l'un des deux, tous les jours.
    """
    from zoneinfo import ZoneInfo

    zone = ZoneInfo(tenant.timezone)
    local = (moment or timezone.now()).astimezone(zone)
    start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


def build(tenant) -> dict:
    """La reponse complete, pour un salon."""
    now = timezone.now()
    day_start, day_end = _day_bounds(tenant, now)
    since = now - timedelta(days=RECENT_DAYS)

    bookings = Booking.objects.all()
    honoured = (Booking.Status.CONFIRMED, Booking.Status.COMPLETED)

    return {
        "currency": tenant.currency,
        "today": _today(bookings, day_start, day_end),
        "attention": attention(),
        "month": _month(now),
        "counters": _counters(bookings, since),
        "top_services": _top_services(bookings, since, honoured),
        "ratings": _ratings(),
        "feed": _feed(bookings, since),
    }


def _today(bookings, day_start, day_end) -> dict:
    """Ce qui se passe aujourd'hui.

    Les rendez-vous annules sont exclus : les compter donnerait une journee
    chargee a un salon qui a vu tout le monde se decommander.
    """
    today = bookings.filter(
        starts_at__gte=day_start,
        starts_at__lt=day_end,
    ).exclude(status=Booking.Status.CANCELLED)

    aggregate = today.aggregate(total=Sum("total_amount"))
    upcoming = (
        today.filter(starts_at__gte=timezone.now())
        .order_by("starts_at")
        .values("starts_at", "service_name", "customer__full_name")
        .first()
    )

    return {
        "count": today.count(),
        "revenue": _money(aggregate["total"]),
        "next": (
            {
                "at": upcoming["starts_at"],
                "service_name": upcoming["service_name"],
                "customer_name": upcoming["customer__full_name"],
            }
            if upcoming
            else None
        ),
    }


def attention() -> dict:
    """Ce qui attend un geste, et coute tant qu'on ne le fait pas.

    Ces trois nombres ne sont pas des statistiques : ce sont des taches.

      - un acompte non verifie, c'est une cliente devant un telephone muet ;
      - une demande non acceptee, c'est un creneau bloque sans engagement ;
      - un creneau passe sans rien de note, c'est une statistique d'absence
        qui ne veut plus rien dire - et une cliente qu'on ne sait pas si
        elle est venue.
    """
    bookings = Booking.objects.all()
    return {
        "deposits": bookings.filter(deposit_proof__status="submitted").count(),
        "requests": bookings.filter(status=Booking.Status.REQUESTED).count(),
        "overdue": bookings.filter(
            ends_at__lt=timezone.now(),
            status__in=(Booking.Status.REQUESTED, Booking.Status.CONFIRMED),
        ).count(),
    }


def _month(now) -> dict:
    """Recettes du mois, et le mois d'avant pour donner l'echelle.

    Un chiffre seul ne dit pas s'il est bon. La variation le dit - et elle
    vaut `None` quand le mois precedent etait vide, parce qu'une croissance
    depuis zero n'est pas un pourcentage.
    """
    start = now.date().replace(day=1)
    previous_end = start - timedelta(days=1)
    previous_start = previous_end.replace(day=1)

    incomes = Transaction.objects.filter(kind=Transaction.Kind.INCOME)
    current = incomes.filter(occurred_on__gte=start).aggregate(
        total=Sum("amount")
    )["total"] or Decimal("0")
    previous = incomes.filter(
        occurred_on__gte=previous_start, occurred_on__lte=previous_end
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")

    growth = None
    if previous > 0:
        growth = round(float((current - previous) / previous) * 100, 1)

    return {
        "income": _money(current),
        "previous_income": _money(previous),
        "growth": growth,
    }


def _counters(bookings, since) -> dict:
    recent = bookings.filter(created_at__gte=since).exclude(
        status=Booking.Status.CANCELLED
    )
    aggregate = recent.aggregate(total=Sum("total_amount"), count=Count("id"))
    count = aggregate["count"] or 0
    total = aggregate["total"] or Decimal("0")

    return {
        "customers": Customer.objects.count(),
        "bookings": count,
        # Le panier moyen sur la periode. Zero rendez-vous ne vaut pas un
        # panier de zero : c'est une absence de reponse.
        "average_basket": _money(total / count) if count else None,
        "reviews": Review.objects.filter(status=Review.Status.PUBLISHED).count(),
        "rating": _average_rating(),
    }


def _average_rating():
    value = Review.objects.filter(status=Review.Status.PUBLISHED).aggregate(
        note=Avg("rating")
    )["note"]
    return round(float(value), 1) if value is not None else None


def _top_services(bookings, since, honoured) -> list[dict]:
    """Les prestations les plus reservees, sur la fenetre recente.

    On compte les rendez-vous **honores ou confirmes**, pas les demandes :
    une prestation qu'on reserve puis annule n'est pas une prestation qui
    marche, et la faire remonter conduirait a mettre en avant exactement ce
    qui decoit.
    """
    rows = (
        bookings.filter(starts_at__gte=since, status__in=honoured)
        .values("service_name")
        .annotate(count=Count("id"), revenue=Sum("total_amount"))
        .order_by("-count", "service_name")[:TOP_SERVICES]
    )
    return [
        {
            "name": row["service_name"] or "Prestation",
            "count": row["count"],
            "revenue": _money(row["revenue"]),
        }
        for row in rows
    ]


def _ratings() -> list[dict]:
    """La repartition des notes, de 5 a 1.

    La repartition et non la moyenne : une moyenne de 4 recouvre aussi bien
    « tout le monde est content » que « la moitie adore et l'autre deteste »,
    et ces deux salons n'ont pas le meme probleme.

    Les notes sans aucun avis figurent quand meme, a zero : une barre absente
    se lit comme une absence de donnee, pas comme une absence de mecontents.
    """
    counts = {
        row["rating"]: row["total"]
        for row in Review.objects.filter(status=Review.Status.PUBLISHED)
        .values("rating")
        .annotate(total=Count("id"))
    }
    return [{"rating": note, "count": counts.get(note, 0)} for note in (5, 4, 3, 2, 1)]


def _feed(bookings, since) -> list[dict]:
    """Le fil d'activite : ce qui s'est passe, du plus recent au plus ancien.

    Construit a partir des rendez-vous et des avis plutot que du journal
    d'audit. Le journal enregistre des actions techniques - « statut
    modifie » - la ou cette liste doit raconter ce qui est arrive au salon.
    """
    entries: list[dict] = []

    recent = (
        bookings.filter(created_at__gte=since)
        .select_related("customer")
        .order_by("-created_at")[:FEED_LENGTH]
    )
    for booking in recent:
        entries.append(
            {
                "kind": "booking",
                "at": booking.created_at,
                "title": f"{booking.customer.full_name} a réservé",
                "detail": booking.service_name,
            }
        )

    for review in (
        Review.objects.filter(created_at__gte=since)
        .order_by("-created_at")[:FEED_LENGTH]
    ):
        entries.append(
            {
                "kind": "review",
                "at": review.created_at,
                "title": f"{review.author_name} a laissé {review.rating}/5",
                "detail": (review.comment or "")[:80],
            }
        )

    paid = (
        bookings.filter(deposit_paid_at__gte=since)
        .select_related("customer")
        .order_by("-deposit_paid_at")[:FEED_LENGTH]
    )
    for booking in paid:
        entries.append(
            {
                "kind": "payment",
                "at": booking.deposit_paid_at,
                "title": f"Acompte reçu de {booking.customer.full_name}",
                "detail": f"{booking.deposit_received} {booking.tenant.currency}",
            }
        )

    entries.sort(key=lambda entry: entry["at"], reverse=True)
    return entries[:FEED_LENGTH]


def occupancy(tenant, days: int = 7) -> float | None:
    """Part des heures d'ouverture reellement occupees, sur la semaine ecoulee.

    Le chiffre qui manquait le plus : un salon peut avoir beaucoup de
    rendez-vous et une journee vide, ou peu de rendez-vous mais longs et
    remplir sa semaine. Le nombre de reservations ne repond pas a « est-ce
    que je travaille assez ».

    Renvoie `None` quand le salon n'a aucune heure d'ouverture declaree :
    diviser par zero donnerait un taux, pas une absence de reponse.
    """
    from apps.scheduling.models import BusinessHours

    minutes_open = 0
    for hours in BusinessHours.objects.filter(staff_member__isnull=True):
        start = hours.starts_at.hour * 60 + hours.starts_at.minute
        end = hours.ends_at.hour * 60 + hours.ends_at.minute
        minutes_open += max(0, end - start)

    if minutes_open <= 0:
        return None

    now = timezone.now()
    booked = Booking.objects.filter(
        starts_at__gte=now - timedelta(days=days),
        starts_at__lt=now,
    ).exclude(status=Booking.Status.CANCELLED)

    minutes_booked = sum(
        (booking.ends_at - booking.starts_at).total_seconds() / 60
        for booking in booked
    )
    # Les heures d'ouverture sont hebdomadaires ; la fenetre peut ne pas
    # faire une semaine entiere.
    window = minutes_open * (days / 7)
    return round(min(100.0, minutes_booked / window * 100), 1)
