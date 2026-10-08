"""Adaptateur du protocole du SDK Python KKIAPAY 0.0.6, avec délais bornés.

Source : kkiapay/base.py du SDK référencé par la documentation officielle.
Le SDK impose pytest 7.2.1, incompatible avec ce projet ; httpx reproduit
uniquement sa requête de vérification. Aucun remboursement ou reversement inventé.
"""

import hmac
import uuid
from datetime import timedelta
from decimal import Decimal, InvalidOperation

import httpx
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.common.db import bypass_tenant_context, tenant_context

from .models import KkiapayIntent, SubscriptionPaymentRequest
from .services import PaiementRefuse

PAYS_DOCUMENTES = {"BJ", "BF", "CI", "TG", "SN", "NE"}


def credentials(sandbox=None):
    sandbox = settings.KKIAPAY_SANDBOX if sandbox is None else sandbox
    prefix = "KKIAPAY_TEST_" if sandbox else "KKIAPAY_LIVE_"
    return {
        nom: getattr(settings, prefix + nom, "")
        for nom in ("PUBLIC_KEY", "PRIVATE_KEY", "SECRET_KEY", "WEBHOOK_SECRET")
    }


def disponible():
    return bool(
        settings.KKIAPAY_ENABLED
        and all(credentials().values())
        and (not settings.KKIAPAY_SANDBOX or settings.DEBUG)
    )


def verifier_transaction(transaction_id, sandbox):
    c = credentials(sandbox)
    if not all(c.values()):
        raise PaiementRefuse("KKIAPAY n’est pas configuré.", "kkiapay_indisponible")
    base = "https://api-sandbox.kkiapay.me" if sandbox else "https://api.kkiapay.me"
    try:
        response = httpx.post(
            base + "/api/v1/transactions/status",
            json={"transactionId": transaction_id},
            timeout=15,
            headers={
                "Accept": "application/json",
                "X-SECRET-KEY": c["SECRET_KEY"],
                "X-API-KEY": c["PUBLIC_KEY"],
                "X-PRIVATE-KEY": c["PRIVATE_KEY"],
            },
        )
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise PaiementRefuse(
            "La vérification KKIAPAY est indisponible. Réessayez.", "verification_indisponible"
        ) from exc
    if not isinstance(data, dict):
        raise PaiementRefuse("Réponse KKIAPAY invalide.", "verification_invalide")
    return data


@transaction.atomic
def preparer(tenant_id, user, donnees):
    from apps.parrainage.cycles import politique
    from apps.tenants.models import Tenant

    from . import services

    tenant = Tenant.objects.get(pk=tenant_id)
    autorises = PAYS_DOCUMENTES.intersection(settings.KKIAPAY_ALLOWED_COUNTRIES)
    if not disponible() or tenant.country not in autorises or donnees["country"] != tenant.country:
        raise PaiementRefuse(
            "KKIAPAY n’est pas disponible dans le pays de ce salon.", "pays_non_pris_en_charge"
        )
    if donnees["currency"] != "XOF":
        raise PaiementRefuse("KKIAPAY accepte uniquement XOF, pas XAF.", "devise_incompatible")
    existing = KkiapayIntent.objects.filter(tenant_id=tenant_id, statut="en_attente").first()
    if existing:
        if existing.expire_le <= timezone.now():
            expirer(existing.pk)
        else:
            with tenant_context(tenant_id):
                d = SubscriptionPaymentRequest.objects.get(pk=existing.demande_id)
            if d.plan.code != donnees["plan"] or str(d.payment_method_id) != str(donnees["method"]):
                raise PaiementRefuse("Un paiement KKIAPAY est déjà en cours.", "demande_en_attente")
            return presentation(existing, d)
    identifiant = uuid.uuid4()
    d = services.soumettre_paiement(
        tenant_id=tenant_id,
        utilisateur=user,
        code_offre=donnees["plan"],
        pays=tenant.country,
        devise="XOF",
        moyen_id=donnees["method"],
        reference=f"KKIAPAY-{identifiant}",
        montant_attendu=donnees.get("montant_attendu"),
        integration=True,
    )
    if d.method_kind != "kkiapay" or d.amount != d.amount.to_integral_value():
        raise PaiementRefuse("Configurez un tarif KKIAPAY en XOF entiers.", "tarif_incompatible")
    p = politique()
    # Durée explicite plateforme ; pas d'intention non bornée si configuration absente.
    if not p:
        raise PaiementRefuse(
            "Configurez le délai d’abandon des paiements dans l’administration.",
            "politique_incomplete",
        )
    i = KkiapayIntent.objects.create(
        id=identifiant,
        tenant_id=tenant_id,
        demande=d,
        sandbox=settings.KKIAPAY_SANDBOX,
        expire_le=timezone.now() + timedelta(hours=p.reservation_heures),
    )
    return presentation(i, d)


def presentation(i, d):
    return {
        "id": str(i.pk),
        "amount": int(d.amount),
        "currency": "XOF",
        "api_key": credentials(i.sandbox)["PUBLIC_KEY"],
        "sandbox": i.sandbox,
        "partnerId": str(i.pk),
        "expire_le": i.expire_le,
        "statut": i.statut,
    }


def confirmer(intent_id, transaction_id, *, charge_signee=None):
    from . import services

    if not transaction_id or len(transaction_id) > 100:
        raise PaiementRefuse("Référence KKIAPAY invalide.", "reference_invalide")
    i = KkiapayIntent.objects.get(pk=intent_id)
    if not i.tenant_id or not i.demande_id:
        raise PaiementRefuse("Ce paiement a été archivé.", "paiement_archive")
    if not disponible() or i.sandbox != settings.KKIAPAY_SANDBOX:
        raise PaiementRefuse("Cet environnement KKIAPAY n’est pas actif.", "environnement_inactif")
    resultat = verifier_transaction(transaction_id, i.sandbox)
    # Le montant et le statut viennent toujours de l'API privée. L'association
    # doit venir de cette réponse OU d'un webhook authentifié, jamais du navigateur.
    liaison = resultat.get("partnerId") or (charge_signee or {}).get("partnerId")
    try:
        montant = Decimal(str(resultat.get("amount")))
    except InvalidOperation as exc:
        raise PaiementRefuse("Montant KKIAPAY invalide.", "montant_invalide") from exc
    if resultat.get("transactionId") != transaction_id or liaison != str(i.pk):
        raise PaiementRefuse("Transaction non associée à ce paiement.", "association_invalide")
    if resultat.get("status") != "SUCCESS":
        raise PaiementRefuse("Le paiement n’est pas confirmé par KKIAPAY.", "paiement_non_confirme")
    # XOF est l'unique devise documentée ; une autre devise explicite est refusée.
    if resultat.get("currency", "XOF") != "XOF" or not montant.is_finite():
        raise PaiementRefuse("Devise KKIAPAY incompatible.", "devise_incompatible")
    with transaction.atomic(), bypass_tenant_context(), tenant_context(i.tenant_id):
        i = KkiapayIntent.objects.select_for_update().get(pk=i.pk)
        d = SubscriptionPaymentRequest.objects.select_for_update().get(pk=i.demande_id)
        if montant != d.amount or d.currency != "XOF" or d.method_kind != "kkiapay":
            raise PaiementRefuse(
                "Le montant vérifié ne correspond pas à l’abonnement.", "montant_invalide"
            )
        if i.statut == "confirme":
            if i.transaction_id != transaction_id:
                raise PaiementRefuse(
                    "Ce paiement est déjà associé à une autre transaction.", "association_invalide"
                )
            return {"confirme": True, "paiement": str(d.pk)}
        if i.statut != "en_attente" or i.expire_le <= timezone.now():
            raise PaiementRefuse(
                "Cette intention de paiement a expiré. Contactez le support.", "intention_expiree"
            )
        i.transaction_id = transaction_id
        i.statut = "confirme"
        i.save(update_fields=["transaction_id", "statut", "updated_at"])
        d.reference = transaction_id
        d.reference_normalisee = services.normaliser_reference(transaction_id)
        d.save(update_fields=["reference", "reference_normalisee"])
        services.approuver_paiement(
            d.pk, administrateur=None, note="Vérifié par API privée KKIAPAY", integration=True
        )
        return {"confirme": True, "paiement": str(d.pk)}


def secret_valide(secret, sandbox):
    attendu = credentials(sandbox)["WEBHOOK_SECRET"]
    return bool(
        attendu and secret and hmac.compare_digest(secret.encode("utf-8"), attendu.encode("utf-8"))
    )


@transaction.atomic
def expirer(intent_id):
    from . import services

    i = KkiapayIntent.objects.select_for_update().get(pk=intent_id)
    if i.statut != "en_attente" or i.expire_le > timezone.now():
        return
    if not i.tenant_id or not i.demande_id:
        i.statut = "expire"
        i.save(update_fields=["statut", "updated_at"])
        return
    with bypass_tenant_context(), tenant_context(i.tenant_id):
        d = SubscriptionPaymentRequest.objects.get(pk=i.demande_id)
        if d.status == "pending":
            services.refuser_paiement(
                d.pk, administrateur=None, motif="Paiement KKIAPAY abandonné ou expiré"
            )
    i.statut = "expire"
    i.save(update_fields=["statut"])
