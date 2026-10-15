"""SASPAY : regler l'abonnement depuis les pays africains que KKIAPAY ne couvre pas.

---------------------------------------------------------------------------
Qui passe par ici
---------------------------------------------------------------------------

KKIAPAY couvre six pays (Benin, Burkina Faso, Cote d'Ivoire, Togo, Senegal,
Niger), en XOF. SASPAY prend tous les autres pays africains de la
plateforme : Mobile Money dans la devise du pays la ou SASPAY a des reseaux,
carte bancaire en USD partout — c'est ainsi que le Congo-Brazzaville, absent
du catalogue Mobile Money de SASPAY, est couvert. Les deux listes ne se
recoupent jamais (verifie au chargement de ce module).

---------------------------------------------------------------------------
Le parcours
---------------------------------------------------------------------------

1. Le salon choisit son offre : le serveur calcule le montant (remise de
   parrainage comprise), ouvre la demande de paiement et une session de
   paiement hebergee chez SASPAY (`POST /checkout-sessions/`).
2. Le navigateur part sur la page SASPAY, ou le salon choisit son reseau et
   saisit son numero. Rien de ce qui touche a l'argent ne transite par nous.
3. La confirmation ne vient **jamais** du navigateur. Elle vient de l'API
   SASPAY, interrogee par le serveur (`GET /checkout-sessions/{id}/status/`,
   qui revérifie l'etat reel chez l'operateur), a trois occasions :
   au retour du salon sur la page Abonnement, a la reception d'un webhook
   signe, et par la tache d'entretien — le filet que SASPAY recommande pour
   un webhook qui n'arriverait jamais.
4. Le montant et la devise de la session sont compares a la demande ; alors
   seulement l'abonnement est prolonge (`approuver_paiement`).

Le webhook `transaction.success` porte la transaction, pas la session : il
sert de signal pour reverifier les paiements en attente, jamais de preuve.

Documentation : https://docs.saspay.me (verifiee le 9 octobre 2026, voir
output/saspay-research-2026-10-09.html).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
import uuid
from datetime import timedelta
from decimal import Decimal, InvalidOperation

import httpx
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.common.db import bypass_tenant_context, tenant_context

from .kkiapay import PAYS_DOCUMENTES as PAYS_KKIAPAY
from .models import SaspayIntent, SubscriptionPaymentRequest
from .services import PaiementRefuse

logger = logging.getLogger(__name__)

#: Les pays ou SASPAY a des reseaux Mobile Money, et leur devise, hors pays
#: KKIAPAY. Source : le catalogue reel du compte (`GET /networks/`, lu le
#: 16/10/2026), plus complet que la page publique de la documentation — qui
#: ne cite pas le Congo-Brazzaville, ou Airtel et MTN sont pourtant actifs.
MOBILE_MONEY = {
    "CG": "XAF",
    "CD": "CDF",
    "CM": "XAF",
    "GH": "GHS",
    "GN": "GNF",
    "KE": "KES",
    "ML": "XOF",
    "MW": "MWK",
    "NG": "NGN",
    "RW": "RWF",
    "TZ": "TZS",
    "UG": "UGX",
    "ZM": "ZMW",
}
PAYS_COUVERTS = set(MOBILE_MONEY)
#: La carte bancaire passe par un reseau global de SASPAY, en dollars.
DEVISE_CARTE = "USD"
#: Les pays ou l'USD se paie aussi par Mobile Money : en RDC, Airtel, Orange
#: et Vodacom ont des portefeuilles en dollars (`*_cd_usd`).
MOBILE_MONEY_USD = {"CD"}
#: Les devises sans centimes : un Mobile Money ne debite pas 0,50 franc.
SANS_DECIMALES = {"XOF", "XAF", "GNF", "RWF", "UGX"}
#: Ecart toleré entre l'horodatage d'un webhook et notre horloge.
TOLERANCE_WEBHOOK = 300
DELAI_HTTP = 15

assert not PAYS_COUVERTS & PAYS_KKIAPAY, "SASPAY et KKIAPAY ne doivent pas se recouvrir."


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def cle(sandbox=None) -> str:
    sandbox = settings.SASPAY_SANDBOX if sandbox is None else sandbox
    return settings.SASPAY_TEST_SECRET_KEY if sandbox else settings.SASPAY_LIVE_SECRET_KEY


def secret_webhook(sandbox) -> str:
    return settings.SASPAY_TEST_WEBHOOK_SECRET if sandbox else settings.SASPAY_LIVE_WEBHOOK_SECRET


def disponible() -> bool:
    """Ouvert seulement s'il est active et complet.

    Une cle de test n'ouvre jamais de vraie periode en production : en mode
    test, il faut `DEBUG` — comme pour KKIAPAY.
    """
    return bool(
        settings.SASPAY_ENABLED
        and cle()
        and secret_webhook(settings.SASPAY_SANDBOX)
        and (not settings.SASPAY_SANDBOX or settings.DEBUG)
    )


def pays_autorises() -> set[str]:
    return PAYS_COUVERTS & set(settings.SASPAY_ALLOWED_COUNTRIES)


def devises_acceptees(pays: str) -> set[str]:
    """La devise du pays (Mobile Money) et l'USD (carte)."""
    if pays not in pays_autorises():
        return set()
    return {MOBILE_MONEY[pays], DEVISE_CARTE}


def canal(pays: str, devise: str) -> str:
    """Comment se paie `devise` dans `pays` : ce que la page annonce au salon.

    « mobile_money » (la devise du pays), « carte » (l'USD), ou
    « mobile_money_carte » (l'USD en RDC, que les portefeuilles en dollars
    acceptent aussi).
    """
    if devise != DEVISE_CARTE:
        return "mobile_money"
    return "mobile_money_carte" if pays in MOBILE_MONEY_USD else "carte"


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


def _appel(methode: str, chemin: str, sandbox: bool, *, json=None, echec: PaiementRefuse):
    """Un appel a l'API ; `echec` est le refus a lever si SASPAY ne repond pas."""
    secret = cle(sandbox)
    if not secret:
        raise PaiementRefuse("SASPAY n'est pas configuré.", "saspay_indisponible")
    try:
        reponse = httpx.request(
            methode,
            settings.SASPAY_API_URL.rstrip("/") + chemin,
            json=json,
            timeout=DELAI_HTTP,
            headers={"Accept": "application/json", "Authorization": f"Bearer {secret}"},
        )
        reponse.raise_for_status()
        donnees = reponse.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("SASPAY %s %s : %s", methode, chemin, exc)
        raise echec from exc
    if not isinstance(donnees, dict):
        raise PaiementRefuse("Réponse SASPAY invalide.", "verification_invalide")
    # L'API enveloppe chaque réponse : {"success": true, "data": {…}, "code": 200}.
    # Constaté en direct le 16/10/2026 — la documentation montre l'objet nu.
    # Sans ce déballage, chaque paiement réel finissait en « réponse invalide ».
    if "success" in donnees and "data" in donnees:
        if donnees["success"] is not True or not isinstance(donnees["data"], dict):
            logger.warning("SASPAY %s %s : refus %s", methode, chemin, donnees.get("code"))
            raise echec
        return donnees["data"]
    return donnees


def _verifier(chemin: str, sandbox: bool) -> dict:
    return _appel(
        "GET",
        chemin,
        sandbox,
        echec=PaiementRefuse(
            "La vérification SASPAY est indisponible. Réessayez.", "verification_indisponible"
        ),
    )


def _montant(valeur) -> Decimal:
    try:
        montant = Decimal(str(valeur))
    except (InvalidOperation, ValueError) as exc:
        raise PaiementRefuse("Montant SASPAY invalide.", "montant_invalide") from exc
    if not montant.is_finite():
        raise PaiementRefuse("Montant SASPAY invalide.", "montant_invalide")
    return montant


# ---------------------------------------------------------------------------
# Ouvrir un paiement
# ---------------------------------------------------------------------------


@transaction.atomic
def preparer(tenant_id, user, donnees) -> dict:
    """La demande de paiement et sa session SASPAY ; rend l'adresse de la page.

    Tout dans une transaction : si SASPAY ne repond pas, la demande n'existe
    pas non plus, et le salon peut simplement reessayer.
    """
    from apps.parrainage.models import PolitiquePlateforme
    from apps.tenants.models import Tenant
    from apps.translations.langue import adresse_app, du_compte

    from . import services

    tenant = Tenant.objects.get(pk=tenant_id)
    devise = donnees["currency"]
    if (
        not disponible()
        or tenant.country not in pays_autorises()
        or donnees["country"] != tenant.country
    ):
        raise PaiementRefuse(
            "SASPAY n'est pas disponible dans le pays de ce salon.", "pays_non_pris_en_charge"
        )
    if devise not in devises_acceptees(tenant.country):
        raise PaiementRefuse(
            "SASPAY accepte la devise du pays ou le dollar américain (carte).",
            "devise_incompatible",
        )

    existante = SaspayIntent.objects.filter(tenant_id=tenant_id, statut="en_attente").first()
    if existante:
        if existante.expire_le <= timezone.now():
            expirer(existante.pk)
        else:
            with tenant_context(tenant_id):
                d = SubscriptionPaymentRequest.objects.get(pk=existante.demande_id)
            if d.plan.code != donnees["plan"] or str(d.payment_method_id) != str(donnees["method"]):
                raise PaiementRefuse("Un paiement SASPAY est déjà en cours.", "demande_en_attente")
            return presentation(existante, d)

    identifiant = uuid.uuid4()
    d = services.soumettre_paiement(
        tenant_id=tenant_id,
        utilisateur=user,
        code_offre=donnees["plan"],
        pays=tenant.country,
        devise=devise,
        moyen_id=donnees["method"],
        reference=f"SASPAY-{identifiant}",
        montant_attendu=donnees.get("montant_attendu"),
        integration=True,
    )
    if d.method_kind != "saspay":
        raise PaiementRefuse(
            "Ce moyen de paiement n'est pas disponible pour ce pays et cette devise.",
            "moyen_indisponible",
        )
    if d.currency in SANS_DECIMALES and d.amount != d.amount.to_integral_value():
        raise PaiementRefuse(
            "Configurez un tarif sans centimes pour cette devise.", "tarif_incompatible"
        )
    politique = PolitiquePlateforme.objects.filter(pk=1).first()
    if not politique or not politique.reservation_heures:
        raise PaiementRefuse(
            "Configurez le délai d'abandon des paiements dans l'administration.",
            "politique_incomplete",
        )
    intention = SaspayIntent.objects.create(
        id=identifiant,
        tenant_id=tenant_id,
        demande=d,
        sandbox=settings.SASPAY_SANDBOX,
        expire_le=timezone.now() + timedelta(hours=politique.reservation_heures),
    )

    corps = {
        "amount": f"{d.amount:.2f}",
        "currency": d.currency,
        "description": f"Beauty Salon — {d.plan.name} — {tenant.name}"[:200],
        "customer_email": user.email,
        "customer_name": (getattr(user, "display_name", "") or tenant.name)[:120],
        # Le salon revient sur sa page Abonnement, qui demande au serveur
        # de verifier : le retour lui-meme ne prouve rien.
        "return_url": adresse_app(f"/abonnement?saspay={intention.pk}", du_compte(user)),
        "metadata": {"intention": str(intention.pk), "salon": str(tenant_id)},
        "expires_at": intention.expire_le.isoformat(),
    }
    if canal(tenant.country, d.currency) != "carte":
        # Preselectionne les reseaux du pays (et, en RDC, ses portefeuilles
        # en dollars) ; en USD par carte, aucun pays.
        corps["country"] = tenant.country
    session = _appel(
        "POST",
        "/checkout-sessions/",
        intention.sandbox,
        json=corps,
        echec=PaiementRefuse(
            "SASPAY est momentanément indisponible. Réessayez dans un instant.",
            "saspay_indisponible",
        ),
    )
    session_id, adresse = str(session.get("id") or ""), str(session.get("checkout_url") or "")
    if not session_id or not adresse.startswith("https://"):
        raise PaiementRefuse("Réponse SASPAY invalide.", "verification_invalide")
    intention.session_id = session_id
    intention.checkout_url = adresse
    intention.save(update_fields=["session_id", "checkout_url", "updated_at"])
    return presentation(intention, d)


def presentation(intention, demande) -> dict:
    return {
        "id": str(intention.pk),
        "checkout_url": intention.checkout_url,
        "amount": str(demande.amount),
        "currency": demande.currency,
        "sandbox": intention.sandbox,
        "expire_le": intention.expire_le,
        "statut": intention.statut,
    }


# ---------------------------------------------------------------------------
# Confirmer
# ---------------------------------------------------------------------------


def confirmer(intent_id) -> dict:
    """Demande a SASPAY ou en est la session ; prolonge l'abonnement si payee.

    Rend `{"confirme": bool, "statut": ...}`. Une session pas encore payee
    n'est pas une erreur : le salon peut etre en train de valider sur son
    telephone. Tout ce qui ne concorde pas (montant, devise, session) est
    refuse, et rien n'est active.
    """
    from . import services

    i = SaspayIntent.objects.get(pk=intent_id)
    if not i.tenant_id or not i.demande_id:
        raise PaiementRefuse("Ce paiement a été archivé.", "paiement_archive")
    if i.statut == "confirme":
        return {"confirme": True, "statut": "confirme", "paiement": str(i.demande_id)}
    if not i.session_id:
        raise PaiementRefuse("Paiement introuvable.", "paiement_introuvable")
    if not disponible() or i.sandbox != settings.SASPAY_SANDBOX:
        raise PaiementRefuse("Cet environnement SASPAY n'est pas actif.", "environnement_inactif")

    etat = _verifier(f"/checkout-sessions/{i.session_id}/status/", i.sandbox)
    if str(etat.get("id")) != i.session_id:
        raise PaiementRefuse("Transaction non associée à ce paiement.", "association_invalide")
    if etat.get("status") != "PAID" or etat.get("transaction_status") != "SUCCESS":
        return {"confirme": False, "statut": str(etat.get("status") or "PENDING").lower()}
    transaction_id = str(etat.get("transaction_id") or "")
    if not transaction_id or len(transaction_id) > 100:
        raise PaiementRefuse("Référence SASPAY invalide.", "reference_invalide")

    # Le montant et la devise viennent de la session elle-meme, chez SASPAY.
    session = _verifier(f"/checkout-sessions/{i.session_id}/", i.sandbox)
    montant = _montant(session.get("amount"))
    metadonnees = session.get("metadata") or {}
    if str(session.get("id")) != i.session_id or (
        isinstance(metadonnees, dict)
        and metadonnees.get("intention")
        and metadonnees["intention"] != str(i.pk)
    ):
        raise PaiementRefuse("Transaction non associée à ce paiement.", "association_invalide")

    with transaction.atomic(), bypass_tenant_context(), tenant_context(i.tenant_id):
        i = SaspayIntent.objects.select_for_update().get(pk=i.pk)
        d = SubscriptionPaymentRequest.objects.select_for_update().get(pk=i.demande_id)
        if (
            montant != d.amount
            or session.get("currency") != d.currency
            or d.method_kind != "saspay"
        ):
            raise PaiementRefuse(
                "Le montant vérifié ne correspond pas à l'abonnement.", "montant_invalide"
            )
        if i.statut == "confirme":
            if i.transaction_id != transaction_id:
                raise PaiementRefuse(
                    "Ce paiement est déjà associé à une autre transaction.", "association_invalide"
                )
            return {"confirme": True, "statut": "confirme", "paiement": str(d.pk)}
        if i.statut != "en_attente":
            raise PaiementRefuse(
                "Cette intention de paiement a expiré. Contactez le support.", "intention_expiree"
            )
        i.transaction_id = transaction_id
        i.statut = "confirme"
        i.save(update_fields=["transaction_id", "statut", "updated_at"])
        reference = str(etat.get("transaction_reference") or transaction_id)[:100]
        d.reference = reference
        d.reference_normalisee = services.normaliser_reference(reference)
        d.save(update_fields=["reference", "reference_normalisee"])
        services.approuver_paiement(
            d.pk, administrateur=None, note="Vérifié par l'API SASPAY", integration=True
        )
        return {"confirme": True, "statut": "confirme", "paiement": str(d.pk)}


def confirmer_en_attente(sandbox: bool, transaction_id: str = "") -> bool:
    """Reverifie les paiements en attente de cet environnement.

    Appele par le webhook (avec la transaction annoncee) et par l'entretien.
    Rend True si la transaction annoncee est confirmee chez nous. Une panne
    de verification remonte : le webhook repond alors 503, et SASPAY
    retentera.
    """
    if transaction_id and SaspayIntent.objects.filter(
        sandbox=sandbox, transaction_id=transaction_id, statut="confirme"
    ).exists():
        return True
    trouve = False
    attente = SaspayIntent.objects.filter(
        sandbox=sandbox, statut="en_attente"
    ).exclude(session_id="").order_by("created_at")[:100]
    for intention in attente:
        try:
            resultat = confirmer(intention.pk)
        except PaiementRefuse as exc:
            if exc.code == "verification_indisponible":
                raise
            logger.warning("Paiement SASPAY %s refusé : %s", intention.pk, exc.code)
            continue
        if resultat["confirme"]:
            intention.refresh_from_db(fields=["transaction_id"])
            trouve = trouve or intention.transaction_id == transaction_id
    return trouve


# ---------------------------------------------------------------------------
# Webhook
# ---------------------------------------------------------------------------


def signature_valide(corps: bytes, signature: str, horodatage: str, sandbox: bool) -> bool:
    """HMAC-SHA256 de « horodatage.corps_brut », en hexadecimal minuscule.

    Sur les octets recus, jamais sur un JSON reconstruit ; horodatage a moins
    de cinq minutes ; comparaison a temps constant.
    """
    secret = secret_webhook(sandbox)
    if not secret or not signature or not horodatage:
        return False
    try:
        if abs(time.time() - int(horodatage)) > TOLERANCE_WEBHOOK:
            return False
    except ValueError:
        return False
    attendue = hmac.new(
        secret.encode("utf-8"), horodatage.encode("ascii") + b"." + corps, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(attendue, signature.strip().lower())


# ---------------------------------------------------------------------------
# Expiration
# ---------------------------------------------------------------------------


def expirer(intent_id) -> None:
    """Clot un paiement abandonne — apres une derniere verification.

    Un salon qui a paye a la derniere minute ne doit pas voir sa demande
    refusee : on demande d'abord a SASPAY. Si SASPAY ne repond pas, on
    n'expire pas : l'entretien suivant recommencera.
    """
    from . import services

    i = SaspayIntent.objects.get(pk=intent_id)
    if i.statut != "en_attente" or i.expire_le > timezone.now():
        return
    if i.tenant_id and i.demande_id and i.session_id and disponible():
        try:
            if confirmer(i.pk)["confirme"]:
                return
        except PaiementRefuse as exc:
            if exc.code == "verification_indisponible":
                return
    with transaction.atomic():
        i = SaspayIntent.objects.select_for_update().get(pk=intent_id)
        if i.statut != "en_attente":
            return
        if i.tenant_id and i.demande_id:
            with bypass_tenant_context(), tenant_context(i.tenant_id):
                d = SubscriptionPaymentRequest.objects.get(pk=i.demande_id)
                if d.status == "pending":
                    services.refuser_paiement(
                        d.pk, administrateur=None, motif="Paiement SASPAY abandonné ou expiré"
                    )
        i.statut = "expire"
        i.save(update_fields=["statut", "updated_at"])
    if i.session_id and cle(i.sandbox):
        # La page de paiement ne doit plus rien encaisser.
        try:
            _appel(
                "POST",
                f"/checkout-sessions/{i.session_id}/cancel/",
                i.sandbox,
                echec=PaiementRefuse(
                    "SASPAY est momentanément indisponible. Réessayez dans un instant.",
                    "saspay_indisponible",
                ),
            )
        except PaiementRefuse:
            logger.warning("Session SASPAY %s non annulée.", i.session_id)


def entretenir() -> None:
    """Le filet : paiements en attente reverifies, abandons clos.

    Appele par l'entretien du parrainage, toutes les dix minutes : une panne
    ici ne doit jamais l'interrompre, d'ou le filet large.
    """
    try:
        if disponible():
            try:
                confirmer_en_attente(settings.SASPAY_SANDBOX)
            except PaiementRefuse:
                logger.warning("Vérification SASPAY indisponible ; nouvel essai plus tard.")
        for iid in list(
            SaspayIntent.objects.filter(
                statut="en_attente", expire_le__lte=timezone.now()
            ).values_list("pk", flat=True)
        ):
            expirer(iid)
    except Exception:  # noqa: BLE001 - l'entretien du parrainage doit continuer
        logger.exception("Entretien SASPAY interrompu.")
