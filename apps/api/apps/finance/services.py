"""Synthese financiere et recettes automatiques.

Tous les calculs sont faits par la base plutot que par Python : additionner
en memoire imposerait de charger chaque ligne, et un salon qui tourne depuis
deux ans en a des milliers pour un ecran qui n'affiche que douze chiffres.
"""

from __future__ import annotations

from collections import OrderedDict
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db.models import Q, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from .models import Transaction


def jour_du_salon(moment: datetime, tenant) -> date:
    """La date telle que le salon la vit.

    ---------------------------------------------------------------------
    Pourquoi ce n'est pas `moment.date()`
    ---------------------------------------------------------------------

    Parce que Django stocke et rend les instants en UTC, et qu'aucun salon
    ne vit a UTC. Un rendez-vous de 7 h du matin a Shanghai est enregistre
    a 23 h UTC **la veille** : `moment.date()` porte alors la recette au
    mauvais jour, et le salon cherche dans ses comptes du mardi l'argent
    qu'il a gagne le mercredi.

    Le decalage est d'une heure a Brazzaville et Kinshasa, de huit a
    Shanghai. Dans les trois cas il suffit a faire basculer les prestations
    du debut de matinee et celles de fin de soiree.

    Un poste de developpement regle sur UTC ne voit jamais ce bogue.
    """
    zone = ZoneInfo(getattr(tenant, "timezone", "") or "UTC")
    return timezone.localtime(moment, zone).date()


def aujourdhui_du_salon(tenant) -> date:
    """« Aujourd'hui » du point de vue du salon, pas du serveur."""
    return jour_du_salon(timezone.now(), tenant)


# Nombre de parts distinctes montrees dans un graphique en anneau.
#
# Ce n'est pas un choix esthetique : au-dela de trois teintes, deux parts
# deviennent indistinguables pour une partie des lecteurs, y compris a
# vision normale. Le reste est regroupe sous « Autres », qui reste exact.
DONUT_SLICES = 3


def totals(queryset) -> dict:
    """Recettes, depenses, resultat et marge sur un ensemble de lignes."""
    aggregate = queryset.aggregate(
        income=Sum("amount", filter=Q(kind=Transaction.Kind.INCOME)),
        expense=Sum("amount", filter=Q(kind=Transaction.Kind.EXPENSE)),
    )
    income = aggregate["income"] or Decimal("0")
    expense = aggregate["expense"] or Decimal("0")
    net = income - expense

    return {
        "income": str(income),
        "expense": str(expense),
        "net": str(net),
        # La marge n'a de sens que s'il y a eu des recettes. Zero divise par
        # zero vaut « pas de reponse », pas « 0 % ».
        "margin": (
            round(float(net / income) * 100, 1) if income > 0 else None
        ),
        "count": queryset.count(),
    }


def monthly(queryset, tenant=None, months: int = 12) -> list[dict]:
    """Recettes et depenses mois par mois, sans trou.

    Les mois vides sont ajoutes explicitement : une courbe qui saute de mars
    a juin laisse croire a une activite continue entre les deux.

    Le dernier seau est le mois courant **du salon**. Le premier jour du
    mois, un serveur en UTC et un salon a Shanghai ne sont pas dans le meme
    mois pendant huit heures : la colonne du mois qui vient de commencer
    manquerait, avec les recettes qu'elle porte.
    """
    rows = (
        queryset.annotate(month=TruncMonth("occurred_on"))
        .values("month", "kind")
        .annotate(total=Sum("amount"))
        .order_by("month")
    )

    buckets: OrderedDict[str, dict] = OrderedDict()

    reference = aujourdhui_du_salon(tenant) if tenant is not None else date.today()
    today = reference.replace(day=1)
    for offset in range(months - 1, -1, -1):
        moment = _shift_months(today, -offset)
        buckets[moment.isoformat()] = {
            "month": moment.isoformat(),
            "income": Decimal("0"),
            "expense": Decimal("0"),
        }

    for row in rows:
        key = row["month"].isoformat()
        bucket = buckets.get(key)
        if bucket is None:
            # Ligne anterieure a la fenetre demandee : ignoree ici, elle
            # reste comptee dans les totaux.
            continue
        bucket["income" if row["kind"] == Transaction.Kind.INCOME else "expense"] = (
            row["total"]
        )

    result = []
    running = Decimal("0")
    for bucket in buckets.values():
        net = bucket["income"] - bucket["expense"]
        running += net
        result.append(
            {
                "month": bucket["month"],
                "income": str(bucket["income"]),
                "expense": str(bucket["expense"]),
                "net": str(net),
                # Le cumul repond a « est-ce que je remonte la pente ? »,
                # que le resultat mensuel seul ne dit pas.
                "cumulative": str(running),
            }
        )
    return result


def by_category(queryset, kind: str) -> list[dict]:
    """Repartition par poste, du plus gros au plus petit."""
    rows = (
        queryset.filter(kind=kind)
        .values("category")
        .annotate(total=Sum("amount"))
        .order_by("-total")
    )

    choices = (
        Transaction.IncomeCategory
        if kind == Transaction.Kind.INCOME
        else Transaction.ExpenseCategory
    )
    labels = dict(choices.choices)

    return [
        {
            "category": row["category"],
            "label": labels.get(row["category"], row["category"]),
            "total": str(row["total"]),
        }
        for row in rows
    ]


def top_slices(rows: list[dict], limit: int = DONUT_SLICES) -> list[dict]:
    """Les `limit` premiers postes, le reste regroupe sous « Autres ».

    Sert au graphique en anneau, qui ne peut pas porter plus de trois
    teintes distinctes sans devenir illisible pour une partie des lecteurs.
    Le total reste juste : rien n'est perdu, tout est regroupe.
    """
    if len(rows) <= limit:
        return rows

    head = rows[:limit]
    tail_total = sum(Decimal(row["total"]) for row in rows[limit:])
    return [
        *head,
        {
            "category": "__other__",
            "label": f"Autres ({len(rows) - limit} postes)",
            "total": str(tail_total),
        },
    ]


def _shift_months(moment: date, delta: int) -> date:
    month = moment.month - 1 + delta
    year = moment.year + month // 12
    return date(year, month % 12 + 1, 1)


# ---------------------------------------------------------------------------
# Ce qui s'enregistre tout seul
# ---------------------------------------------------------------------------
#
# Trois evenements produisent une ligne sans que personne ne la saisisse :
# un acompte encaisse, une prestation honoree, une facture d'abonnement
# reglee. C'est ce qui rend le cahier de comptes utilisable des le premier
# jour - un registre qu'il faut tenir a la main en double du reste n'est
# jamais tenu.
#
# ---------------------------------------------------------------------------
# Le piege : ne jamais compter le meme argent deux fois
# ---------------------------------------------------------------------------
#
# Une cliente verse 150 d'acompte sur une prestation a 450. Si l'acompte
# donne une recette de 150 et que la prestation terminee en donne une de 450,
# le salon voit 600 la ou 450 sont entres - et se croit plus riche qu'il ne
# l'est.
#
# La regle est donc : **le solde, pas le total**. Chaque ligne automatique ne
# constate que ce qui ne l'a pas deja ete pour ce rendez-vous.


def _already_recorded(booking) -> Decimal:
    """Somme deja enregistree en recette pour ce rendez-vous."""
    total = Transaction.objects.filter(
        booking=booking, kind=Transaction.Kind.INCOME
    ).aggregate(total=Sum("amount"))["total"]
    return total or Decimal("0")


def record_deposit_income(booking) -> Transaction | None:
    """Constate l'acompte le jour ou il rentre.

    Un acompte est de l'argent reellement recu : il appartient au mois du
    versement, pas a celui de la prestation. Un salon qui encaisse en mars
    pour une pose en mai doit voir la recette en mars, sinon sa tresorerie du
    mois est fausse.

    C'est `deposit_received` qui fait foi, jamais `deposit_amount` : une
    cliente laisse parfois ce qu'elle a sur elle.
    """
    received = booking.deposit_received or Decimal("0")
    if received <= 0:
        return None

    existing = Transaction.objects.filter(
        booking=booking, source=Transaction.Source.BOOKING_DEPOSIT
    ).first()
    if existing is not None:
        # Le montant a pu etre corrige entre-temps.
        if existing.amount != received:
            existing.amount = received
            existing.method = booking.deposit_method or existing.method
            existing.save(update_fields=["amount", "method", "updated_at"])
        return existing

    return Transaction.objects.create(
        tenant_id=booking.tenant_id,
        kind=Transaction.Kind.INCOME,
        category=Transaction.IncomeCategory.SERVICE,
        source=Transaction.Source.BOOKING_DEPOSIT,
        label=f"Acompte — {booking.service_name or 'prestation'}",
        amount=received,
        occurred_on=jour_du_salon(
            booking.deposit_paid_at or timezone.now(), booking.tenant
        ),
        method=booking.deposit_method or Transaction.Method.CASH,
        counterparty=getattr(booking.customer, "full_name", "") or "",
        booking=booking,
    )


def remove_deposit_income(booking) -> int:
    """Retire la recette d'un acompte annule.

    `deposit/cancel` existe pour corriger un clic malencontreux. Si la
    recette restait, la correction serait cosmetique : la caisse resterait
    fausse, et personne ne saurait pourquoi.
    """
    deleted, _ = Transaction.objects.filter(
        booking=booking, source=Transaction.Source.BOOKING_DEPOSIT
    ).delete()
    return deleted


def record_items_income(booking) -> Transaction | None:
    """Constate separement ce qui a ete vendu au comptoir.

    Une ligne a part, et non fondue dans la prestation : le graphique
    « d'ou vient l'argent » n'a d'interet que s'il distingue ce qu'on gagne
    en coiffant de ce qu'on gagne en revendant des meches. Ce sont deux
    metiers, deux marges, et deux decisions differentes.
    """
    amount = booking.items_amount or Decimal("0")
    if amount <= 0:
        return None

    existing = Transaction.objects.filter(
        booking=booking, source=Transaction.Source.BOOKING_ITEMS
    ).first()
    if existing is not None:
        return existing

    names = ", ".join(
        row.get("name", "") for row in (booking.items_snapshot or [])
    )[:160]

    return Transaction.objects.create(
        tenant_id=booking.tenant_id,
        kind=Transaction.Kind.INCOME,
        category=Transaction.IncomeCategory.PRODUCT,
        source=Transaction.Source.BOOKING_ITEMS,
        label=names or "Vente au comptoir",
        amount=amount,
        occurred_on=jour_du_salon(booking.starts_at, booking.tenant),
        method=booking.deposit_method or Transaction.Method.CASH,
        counterparty=getattr(booking.customer, "full_name", "") or "",
        booking=booking,
    )


def record_travel_income(booking) -> Transaction | None:
    """Constate separement le forfait de deplacement.

    Meme raison que pour la vente au comptoir : une ligne a part, sinon le
    graphique « d'ou vient l'argent » ne dit plus rien. Se deplacer n'est pas
    coiffer - c'est du carburant, du temps de trajet et un risque de retard -
    et la depense correspondante existe deja de l'autre cote du livre, sous
    « Transport et deplacements ».

    Fondu dans la prestation, le forfait gonflait le chiffre d'affaires du
    geste technique pendant que le trajet ne paraissait qu'en depense : un
    salon regardant ses deux colonnes concluait que le domicile lui coutait
    de l'argent. Les deux lignes se font maintenant face, et la question
    « le forfait de cette zone couvre-t-il le trajet ? » devient lisible.
    """
    amount = booking.travel_fee_amount or Decimal("0")
    if amount <= 0:
        # Une zone desservie gratuitement est un choix commercial, pas une
        # recette de zero : rien a ecrire.
        return None

    existing = Transaction.objects.filter(
        booking=booking, source=Transaction.Source.BOOKING_TRAVEL
    ).first()
    if existing is not None:
        return existing

    zone = booking.travel_zone_name or "zone non precisee"

    return Transaction.objects.create(
        tenant_id=booking.tenant_id,
        kind=Transaction.Kind.INCOME,
        category=Transaction.IncomeCategory.TRAVEL,
        source=Transaction.Source.BOOKING_TRAVEL,
        label=f"Déplacement — {zone}"[:160],
        amount=amount,
        occurred_on=jour_du_salon(booking.starts_at, booking.tenant),
        method=booking.deposit_method or Transaction.Method.CASH,
        counterparty=getattr(booking.customer, "full_name", "") or "",
        booking=booking,
    )


def record_booking_income(booking) -> Transaction | None:
    """Constate le **solde** d'un rendez-vous honore.

    Le solde, et non le total : l'acompte a deja produit sa propre ligne le
    jour ou il est rentre.

    Renvoie None quand il n'y a rien a constater - prestation entierement
    reglee d'avance, ou montant nul.
    """
    if booking.total_amount is None or booking.total_amount <= 0:
        return None

    existing = Transaction.objects.filter(
        booking=booking, source=Transaction.Source.BOOKING_BALANCE
    ).first()
    if existing is not None:
        return existing

    # La vente au comptoir et le deplacement sont constates d'abord : le
    # solde se calcule sur ce qui reste, donc ils s'en deduisent tout seuls.
    # Inverser l'ordre les compterait deux fois - une fois dans le solde,
    # une fois dans leur propre ligne.
    record_items_income(booking)
    record_travel_income(booking)

    balance = booking.total_amount - _already_recorded(booking)
    if balance <= 0:
        # Tout etait deja verse. Une ligne a zero n'apprendrait rien et
        # encombrerait la liste des mouvements.
        return None

    return Transaction.objects.create(
        tenant_id=booking.tenant_id,
        kind=Transaction.Kind.INCOME,
        category=Transaction.IncomeCategory.SERVICE,
        source=Transaction.Source.BOOKING_BALANCE,
        label=booking.service_name or "Prestation",
        amount=balance,
        occurred_on=jour_du_salon(booking.starts_at, booking.tenant),
        # Le moyen de paiement de l'acompte est le seul indice dont on
        # dispose. A defaut, especes : c'est le cas majoritaire sur les
        # marches vises, et le salon corrige en un clic.
        method=booking.deposit_method or Transaction.Method.CASH,
        counterparty=getattr(booking.customer, "full_name", "") or "",
        booking=booking,
    )


def record_subscription_expense(invoice) -> Transaction | None:
    """Porte l'abonnement a la plateforme en charge du salon.

    C'est une depense comme le loyer : le salon la subit, il ne la saisit
    pas. L'inscrire automatiquement evite la situation absurde ou le seul
    poste que la plateforme connait parfaitement serait le seul que le salon
    devrait recopier a la main.
    """
    if invoice.amount is None or invoice.amount <= 0:
        return None

    existing = Transaction.objects.filter(invoice=invoice).first()
    if existing is not None:
        return existing

    period = f" — {invoice.period_start:%m/%Y}" if invoice.period_start else ""

    return Transaction.objects.create(
        tenant_id=invoice.tenant_id,
        kind=Transaction.Kind.EXPENSE,
        category=Transaction.ExpenseCategory.OTHER_EXPENSE,
        source=Transaction.Source.SUBSCRIPTION,
        label=f"Abonnement Beauty Salon{period}",
        amount=invoice.amount,
        occurred_on=jour_du_salon(
            invoice.paid_at or timezone.now(), invoice.tenant
        ),
        method=invoice.payment_method or Transaction.Method.TRANSFER,
        counterparty="Beauty Salon",
        note=f"Facture {invoice.number}",
        invoice=invoice,
    )
