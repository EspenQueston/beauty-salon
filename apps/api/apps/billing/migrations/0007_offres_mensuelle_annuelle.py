"""Deux offres payantes, leurs prix en yuans, et la reprise de l'existant.

---------------------------------------------------------------------------
Les offres
---------------------------------------------------------------------------

`monthly` (1 mois) et `yearly` (12 mois) remplacent Solo, Salon et Pro, qui
restent en base, desactivees : des abonnements anciens les referencent. Seuls
les prix en yuans de reference sont poses — 99 et 999 CNY. Les autres devises
n'ont de prix que celui qu'un administrateur saisira.

---------------------------------------------------------------------------
Les salons deja inscrits
---------------------------------------------------------------------------

Jusqu'ici, un essai termine basculait l'abonnement en « actif » a prix nul :
aucun salon n'a jamais paye. Appliquer d'un coup la nouvelle regle — pas de
periode payee, pas d'acces — fermerait les reservations de tous les salons le
jour de la mise a jour, sans preavis.

Chaque abonnement sans facture reglee recoit donc un essai de 14 jours a
compter d'aujourd'hui (ou garde le sien s'il dure plus longtemps) : le temps
de choisir une offre et de payer. Un salon sans abonnement du tout en recoit
un. Tout est trace dans l'historique.
"""

from datetime import timedelta
from decimal import Decimal

from django.db import migrations
from django.utils import timezone

JOURS_ESSAI = 14
TENANT_GUC = "app.tenant_id"

OFFRES = [
    {
        "code": "monthly",
        "name": "Mensuel",
        "description": "Toute la plateforme, réglée chaque mois.",
        "billing_months": 1,
        "position": 10,
        "prix_cny": Decimal("99"),
    },
    {
        "code": "yearly",
        "name": "Annuel",
        "description": "Toute la plateforme, réglée pour douze mois.",
        "billing_months": 12,
        "position": 11,
        "prix_cny": Decimal("999"),
    },
]

ANCIENNES = ("solo", "salon", "pro")


def en_avant(apps, schema_editor):
    Plan = apps.get_model("billing", "Plan")
    PlanPrice = apps.get_model("billing", "PlanPrice")
    Subscription = apps.get_model("billing", "Subscription")
    SubscriptionEvent = apps.get_model("billing", "SubscriptionEvent")
    Invoice = apps.get_model("billing", "Invoice")
    Tenant = apps.get_model("tenants", "Tenant")
    connexion = schema_editor.connection
    alias = connexion.alias

    for offre in OFFRES:
        prix = offre["prix_cny"]
        champs = {k: v for k, v in offre.items() if k not in ("code", "prix_cny")}
        plan, _ = Plan.objects.using(alias).update_or_create(
            code=offre["code"], defaults={**champs, "active": True}
        )
        PlanPrice.objects.using(alias).get_or_create(
            plan=plan, currency="CNY", defaults={"amount": prix, "active": True}
        )

    Plan.objects.using(alias).filter(code__in=ANCIENNES).update(active=False)

    essai, _ = Plan.objects.using(alias).get_or_create(
        code="trial",
        defaults={
            "name": "Essai",
            "description": "Deux semaines pour essayer, sans engagement.",
            "billing_months": 0,
            "position": 0,
            "active": True,
        },
    )

    maintenant = timezone.now()
    fin_essai = maintenant + timedelta(days=JOURS_ESSAI)

    # Salon par salon, contexte pose : abonnements, historique et factures
    # sont sous RLS. Lus hors contexte ils seraient vides, ecrits hors
    # contexte ils sont refuses. Toutes les requetes passent par `alias`, la
    # connexion ou vit le `set_config` — voir catalog/0011.
    for tenant in Tenant.objects.using(alias).all():
        with connexion.cursor() as curseur:
            curseur.execute("SELECT set_config(%s, %s, true)", [TENANT_GUC, str(tenant.id)])

        abonnement = Subscription.objects.using(alias).filter(tenant_id=tenant.id).first()

        # Sans abonnement du tout : un essai neuf.
        if abonnement is None:
            abonnement = Subscription.objects.using(alias).create(
                tenant=tenant,
                plan=essai,
                status="trialing",
                price_amount=Decimal("0"),
                currency=tenant.currency,
                trial_ends_at=fin_essai,
                current_period_start=maintenant,
                current_period_end=fin_essai,
            )
            SubscriptionEvent.objects.using(alias).create(
                tenant=tenant,
                subscription=abonnement,
                kind="migrated",
                status_after="trialing",
                period_end_after=fin_essai,
                note="Essai de 14 jours ouvert à la mise en place des abonnements payants.",
            )
            continue

        # Jamais paye : un essai prolonge jusqu'a J+14.
        if abonnement.status not in ("trialing", "active", "past_due"):
            continue
        if (
            Invoice.objects.using(alias)
            .filter(subscription_id=abonnement.id, status="paid")
            .exists()
        ):
            continue

        avant_statut = abonnement.status
        avant_fin = abonnement.current_period_end
        fin = max(fin_essai, abonnement.trial_ends_at or fin_essai)
        abonnement.status = "trialing"
        abonnement.trial_ends_at = fin
        abonnement.current_period_end = fin
        abonnement.plan = essai
        abonnement.save(
            using=alias,
            update_fields=["status", "trial_ends_at", "current_period_end", "plan"],
        )
        SubscriptionEvent.objects.using(alias).create(
            tenant_id=abonnement.tenant_id,
            subscription=abonnement,
            kind="migrated",
            status_before=avant_statut,
            status_after="trialing",
            period_end_before=avant_fin,
            period_end_after=fin,
            note=(
                "Aucun paiement enregistré : essai prolongé de 14 jours à la mise "
                "en place des abonnements payants."
            ),
        )

    with connexion.cursor() as curseur:
        curseur.execute("SELECT set_config(%s, '', true)", [TENANT_GUC])


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0006_rls_paiements"),
        ("tenants", "0003_alter_tenant_country_alter_tenant_currency_and_more"),
    ]

    # Pas de retour arriere automatique : on ne defait pas un essai accorde.
    operations = [migrations.RunPython(en_avant, migrations.RunPython.noop)]
