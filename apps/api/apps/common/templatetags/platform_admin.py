"""Panneau de supervision de la page d'accueil de l'administration.

L'index par defaut liste des modeles ; il ne dit pas ce qu'il y a a faire
maintenant. Ces chiffres-la sont exactement le travail quotidien de l'equipe
plateforme : valider les salons qui viennent de s'inscrire, relancer les
factures en retard, verifier que les comptes d'administration sont proteges.

Toutes les lectures passent par l'alias `admin` et par `all_tenants` : c'est
le seul endroit du produit ou voir tous les salons est intentionnel.
"""

import os
from datetime import timedelta

from django import template
from django.db.models import Sum
from django.urls import reverse
from django.utils import timezone
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.models import User
from apps.billing.models import Invoice
from apps.common.admin import ADMIN_DB
from apps.scheduling.models import BLOCKING_BOOKING_STATUSES, Booking
from apps.tenants.models import Tenant

register = template.Library()

PENDING_PREVIEW = 8


@register.inclusion_tag("admin/supervision.html", takes_context=True)
def supervision_panel(context):
    request = context.get("request")
    if request is None or not request.user.is_authenticated:
        return {"visible": False}

    now = timezone.now()

    pending = (
        Tenant.objects.using(ADMIN_DB)
        .filter(status=Tenant.Status.PENDING)
        .order_by("-created_at")
    )
    pending_count = pending.count()

    invoices = Invoice.all_tenants.using(ADMIN_DB)
    overdue = invoices.filter(status=Invoice.Status.ISSUED, due_at__lt=now)
    overdue_total = overdue.aggregate(total=Sum("amount"))["total"] or 0

    bookings = Booking.all_tenants.using(ADMIN_DB).filter(
        starts_at__gte=now,
        starts_at__lt=now + timedelta(days=7),
        status__in=BLOCKING_BOOKING_STATUSES,
    )

    # Un compte d'administration ouvre l'alias qui contourne les politiques
    # RLS : sans double authentification, un mot de passe volé donne acces
    # aux donnees de tous les salons.
    protected = set(
        TOTPDevice.objects.using(ADMIN_DB)
        .filter(confirmed=True)
        .values_list("user_id", flat=True)
    )
    admins = User.objects.using(ADMIN_DB).filter(is_platform_admin=True, is_active=True)
    unprotected = [account for account in admins if account.id not in protected]

    return {
        "visible": True,
        "pending_count": pending_count,
        "pending_rows": list(pending[:PENDING_PREVIEW]),
        "pending_more": max(pending_count - PENDING_PREVIEW, 0),
        "pending_url": (
            f"{reverse('admin:tenants_tenant_changelist')}?status__exact=pending"
        ),
        "active_count": Tenant.objects.using(ADMIN_DB)
        .filter(status=Tenant.Status.ACTIVE)
        .count(),
        "tenant_url": reverse("admin:tenants_tenant_changelist"),
        "overdue_count": overdue.count(),
        "overdue_total": overdue_total,
        "invoice_url": (
            f"{reverse('admin:billing_invoice_changelist')}?status__exact=issued"
        ),
        "booking_count": bookings.count(),
        "unprotected": unprotected,
        "user_url": reverse("admin:accounts_user_changelist"),
        "now": now,
    }


@register.simple_tag
def versioned_static(path: str) -> str:
    """URL d'un fichier statique, suffixée par sa date de modification.

    En developpement, Django sert les fichiers statiques avec des en-tetes
    que le navigateur met volontiers en cache : une modification de la
    feuille de style n'apparait qu'apres un rechargement force, et on croit
    debugger un probleme de cascade CSS alors qu'on regarde l'ancien
    fichier. L'empreinte rend l'URL differente des que le contenu change.

    En production, `ManifestStaticFilesStorage` fait deja ce travail et
    renvoie un nom de fichier hache ; le suffixe est alors redondant mais
    inoffensif.
    """
    from django.contrib.staticfiles import finders
    from django.templatetags.static import static

    url = static(path)
    absolute = finders.find(path)
    if absolute:
        try:
            return f"{url}?v={int(os.path.getmtime(absolute))}"
        except OSError:
            pass
    return url


@register.inclusion_tag("admin/platform_finances.html", takes_context=True)
def platform_finances(context):
    """Les comptes de la plateforme, sur sa page d'accueil.

    Meme discipline que les graphiques cote salon, appliquee ici :

      - **Une seule echelle.** Recettes et depenses sont dans la meme unite,
        donc sur le meme axe. Deux echelles superposees laisseraient croire a
        des croisements qui n'existent pas.
      - **Deux teintes, pas plus**, verifiees pour rester distinctes en
        deuteranopie comme en protanopie - et doublees d'une legende, parce
        que la couleur ne doit jamais porter l'information seule.
      - **Les mois vides sont dessines**, sinon la courbe sauterait de mars a
        juin en laissant croire a une activite continue entre les deux.

    Toutes les lectures passent par l'alias `admin` : c'est le seul endroit
    du produit ou voir tous les salons est intentionnel.
    """
    from decimal import Decimal

    from django.db.models import Q
    from django.db.models.functions import TruncMonth

    from apps.platformledger.models import PlatformEntry

    request = context.get("request")
    if request is None or not request.user.is_authenticated:
        return {"visible": False}

    today = timezone.localdate()
    first = today.replace(day=1)
    window_start = first
    for _ in range(11):
        window_start = (window_start - timedelta(days=1)).replace(day=1)

    rows = (
        PlatformEntry.objects.using(ADMIN_DB)
        .filter(occurred_on__gte=window_start)
        .annotate(month=TruncMonth("occurred_on"))
        .values("month", "kind")
        .annotate(total=Sum("amount"))
    )

    buckets = {}
    cursor = window_start
    while cursor <= first:
        buckets[cursor] = {"month": cursor, "income": Decimal("0"), "expense": Decimal("0")}
        cursor = (cursor + timedelta(days=32)).replace(day=1)

    for row in rows:
        bucket = buckets.get(row["month"])
        if bucket is not None:
            key = "income" if row["kind"] == PlatformEntry.Kind.INCOME else "expense"
            bucket[key] = row["total"]

    series = list(buckets.values())
    biggest = max(
        (max(bucket["income"], bucket["expense"]) for bucket in series),
        default=Decimal("0"),
    ) or Decimal("1")

    # Les hauteurs sont calculees ici plutot que dans le gabarit : un
    # pourcentage se calcule en Python, pas en langage de template.
    for bucket in series:
        bucket["income_height"] = round(float(bucket["income"] / biggest) * 100)
        bucket["expense_height"] = round(float(bucket["expense"] / biggest) * 100)
        bucket["label"] = bucket["month"].strftime("%b")

    month_totals = (
        PlatformEntry.objects.using(ADMIN_DB)
        .filter(occurred_on__gte=first)
        .aggregate(
            income=Sum("amount", filter=Q(kind=PlatformEntry.Kind.INCOME)),
            expense=Sum("amount", filter=Q(kind=PlatformEntry.Kind.EXPENSE)),
        )
    )
    income = month_totals["income"] or Decimal("0")
    expense = month_totals["expense"] or Decimal("0")

    return {
        "visible": True,
        "series": series,
        "income": income,
        "expense": expense,
        "net": income - expense,
        "positive": income >= expense,
        "ledger_url": reverse("admin:platformledger_platformentry_changelist"),
        "paying_salons": (
            PlatformEntry.objects.using(ADMIN_DB)
            .filter(
                kind=PlatformEntry.Kind.INCOME,
                source=PlatformEntry.Source.SUBSCRIPTION,
                occurred_on__gte=first,
            )
            .values("tenant_id")
            .distinct()
            .count()
        ),
    }
