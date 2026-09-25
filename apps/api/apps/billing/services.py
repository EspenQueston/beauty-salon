"""Cycle de vie des abonnements : essai, paiement, verification, acces.

---------------------------------------------------------------------------
Le modele
---------------------------------------------------------------------------

Un salon s'inscrit : il a 14 jours d'essai. Pour continuer, il choisit une
offre — mensuelle ou annuelle —, paie hors ligne (WeChat Pay, Alipay, Mobile
Money) et declare son paiement avec la reference de la transaction. Un
administrateur verifie sur le compte crediteur, puis approuve ou refuse.
Seule l'approbation ouvre une periode payee. Aucune passerelle n'est branchee,
et aucun paiement n'est jamais tenu pour verifie tant qu'un humain autorise
ne l'a pas dit.

---------------------------------------------------------------------------
Les regles, decidees avec le produit
---------------------------------------------------------------------------

  - essai : 14 jours ;
  - un mois approuve accorde un mois calendaire, une annee douze ;
  - payer pendant une periode en cours (essai compris) : la nouvelle periode
    commence a la fin de la periode en cours — personne ne perd de jours ;
  - sinon, elle commence a l'approbation ;
  - a la fin d'une periode, 3 jours de grace ; ensuite, plus de nouvelles
    reservations et un tableau de bord en lecture seule, page Abonnement
    exceptee. Rien n'est efface ; tout reprend a l'approbation.

---------------------------------------------------------------------------
Deux garanties
---------------------------------------------------------------------------

L'approbation est **atomique** et **idempotente** : la demande et
l'abonnement sont verrouilles le temps de la decision, et une demande deja
traitee ne l'est pas deux fois. Deux clics, deux onglets, deux
administrateurs en meme temps : une seule periode accordee.

Rien n'est ecrase : chaque demande, chaque decision et chaque changement de
periode reste en base (`SubscriptionPaymentRequest`, `SubscriptionEvent`,
`Invoice`, `AuditLog`).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from dateutil.relativedelta import relativedelta
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from apps.common.db import bypass_tenant_context, tenant_context
from apps.tenants.models import Tenant

from .models import (
    DEVISES_ABONNEMENT,
    Invoice,
    Plan,
    PlanPrice,
    PlatformPaymentMethod,
    Subscription,
    SubscriptionEvent,
    SubscriptionPaymentRequest,
)

logger = logging.getLogger(__name__)

TRIAL_DAYS = 14
GRACE = timedelta(days=3)
PAYMENT_TERMS_DAYS = 15

# Duree d'un cycle de l'ancien mode « a terme echu », garde pour l'action
# d'administration qui emet une facture sur un abonnement a prix negocie.
PERIOD_DAYS = 30

OFFRES_PAYANTES = (Plan.Code.MONTHLY, Plan.Code.YEARLY)
DEVISES = {code for code, _ in DEVISES_ABONNEMENT}

# Ce qu'un moyen de la plateforme devient sur la facture et en comptabilite.
METHODE_FACTURE = {
    PlatformPaymentMethod.Kind.WECHAT: Invoice.Method.WECHAT,
    PlatformPaymentMethod.Kind.ALIPAY: Invoice.Method.ALIPAY,
    PlatformPaymentMethod.Kind.MOBILE_MONEY: Invoice.Method.MOBILE_MONEY,
}


class BillingError(Exception):
    """Operation de facturation refusee."""


class PaiementRefuse(BillingError):
    """Une demande de paiement qui ne peut pas etre enregistree ou traitee.

    Porte un `code` stable, lu par le frontend, et un message deja redige
    pour la personne qui l'a declenchee.
    """

    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------------------
# L'acces
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Acces:
    """Ce qu'un salon peut faire, maintenant.

    `ouvert` decide de tout : reservations publiques et ecritures du tableau
    de bord. Le reste sert a l'expliquer — dans une banniere, un message
    d'erreur, la page Abonnement.
    """

    ouvert: bool
    raison: (
        str  # "essai" | "periode" | "grace" | "expire" | "suspendu" | "resilie" | "sans_abonnement"
    )
    fin_periode: datetime | None = None
    jusqu_au: datetime | None = None

    @property
    def en_grace(self) -> bool:
        return self.raison == "grace"


def acces_de(abonnement: Subscription | None, now: datetime | None = None) -> Acces:
    """L'acces que donne un abonnement, calcule sur les dates.

    Sur les dates et non sur le statut seul : si la tache quotidienne n'est
    pas encore passee, une periode echue ferme tout de meme l'acces a
    l'heure dite.

    Un salon sans abonnement du tout reste ouvert. Ce cas ne se produit plus
    — l'inscription, l'administration et la tache quotidienne en creent un —
    mais s'il revenait, par un chemin oublie, fermer les reservations d'un
    salon en production serait pire que de lui laisser quelques jours
    gratuits. La tache quotidienne le repare le lendemain.
    """
    now = now or timezone.now()
    if abonnement is None:
        return Acces(ouvert=True, raison="sans_abonnement")

    if abonnement.status == Subscription.Status.SUSPENDED:
        return Acces(ouvert=False, raison="suspendu", fin_periode=abonnement.current_period_end)
    if abonnement.status == Subscription.Status.CANCELLED:
        return Acces(ouvert=False, raison="resilie", fin_periode=abonnement.current_period_end)

    fin = abonnement.current_period_end
    limite = fin + GRACE
    if now < fin:
        raison = "essai" if abonnement.status == Subscription.Status.TRIALING else "periode"
        return Acces(ouvert=True, raison=raison, fin_periode=fin, jusqu_au=limite)
    if now < limite:
        return Acces(ouvert=True, raison="grace", fin_periode=fin, jusqu_au=limite)
    return Acces(ouvert=False, raison="expire", fin_periode=fin, jusqu_au=limite)


def acces_du_salon(tenant_id, now: datetime | None = None) -> Acces:
    """L'acces du salon courant. A appeler dans son contexte."""
    abonnement = Subscription.objects.filter(tenant_id=tenant_id).first()
    return acces_de(abonnement, now)


# ---------------------------------------------------------------------------
# Les periodes
# ---------------------------------------------------------------------------


def ajouter_mois(ancre: datetime, mois: int, fuseau: str) -> datetime:
    """`ancre` plus `mois` mois calendaires, dans le fuseau du salon.

    Deux regles, testees :

      - un jour qui n'existe pas dans le mois d'arrivee donne le dernier jour
        de ce mois : 31 janvier + 1 mois = 28 fevrier (29 en annee
        bissextile), 29 fevrier + 12 mois = 28 fevrier ;
      - le calcul part toujours de l'ancre de la suite de periodes, jamais de
        la fin precedente : 31 janvier + 2 mois = 31 mars, et non le 28 mars
        qu'on obtiendrait en ajoutant un mois au 28 fevrier.

    Dans le fuseau du salon, parce que « le 31 » est une date locale : a
    Guangzhou, 23 h UTC le 30 est deja le 31.
    """
    local = ancre.astimezone(ZoneInfo(fuseau))
    return (local + relativedelta(months=mois)).astimezone(ZoneInfo("UTC"))


def _fuseau(abonnement: Subscription) -> str:
    tenant = abonnement.tenant
    return getattr(tenant, "timezone", "") or "UTC"


def _evenement(
    abonnement, kind, *, avant_statut="", avant_fin=None, acteur=None, demande=None, note=""
):
    return SubscriptionEvent.objects.create(
        tenant_id=abonnement.tenant_id,
        subscription=abonnement,
        kind=kind,
        status_before=avant_statut,
        status_after=abonnement.status,
        period_end_before=avant_fin,
        period_end_after=abonnement.current_period_end,
        actor=acteur,
        payment_request=demande,
        note=note,
    )


def start_trial(tenant: Tenant, *, plan: Plan | None = None) -> Subscription:
    """Ouvre la periode d'essai d'un salon qui vient de s'inscrire."""
    plan = plan or Plan.objects.filter(code=Plan.Code.TRIAL, active=True).first()
    if plan is None:
        raise BillingError("Aucune offre d'essai n'est configurée.")

    now = timezone.now()
    ends = now + timedelta(days=TRIAL_DAYS)

    # Appelee depuis l'inscription comme depuis l'administration, ou le
    # contexte de la requete peut etre celui d'un autre salon.
    with bypass_tenant_context(), tenant_context(tenant.id):
        existing = Subscription.objects.filter(tenant=tenant).first()
        if existing is not None:
            return existing

        abonnement = Subscription.objects.create(
            tenant=tenant,
            plan=plan,
            status=Subscription.Status.TRIALING,
            price_amount=Decimal("0"),
            currency=tenant.currency,
            trial_ends_at=ends,
            current_period_start=now,
            current_period_end=ends,
        )
        _evenement(abonnement, SubscriptionEvent.Kind.TRIAL_STARTED)
        return abonnement


# ---------------------------------------------------------------------------
# Tarifs et moyens de reglement
# ---------------------------------------------------------------------------


def offres_payantes() -> list[Plan]:
    return list(Plan.objects.filter(code__in=OFFRES_PAYANTES, active=True).order_by("position"))


def tarif(plan: Plan, devise: str) -> PlanPrice | None:
    """Le prix configure d'une offre dans une devise, ou None."""
    return PlanPrice.objects.filter(plan=plan, currency=devise, active=True).first()


def economie_annuelle(mensuel: Decimal | None, annuel: Decimal | None) -> dict | None:
    """Ce que l'annee fait gagner face a douze mois payes un par un.

    None quand on ne peut pas comparer — un des deux prix manque — ou qu'il
    n'y a rien a gagner : on n'affiche jamais une « economie » nulle.
    """
    if not mensuel or not annuel:
        return None
    douze = mensuel * 12
    gain = douze - annuel
    if gain <= 0:
        return None
    pourcentage = (gain / douze * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return {"montant": gain, "pourcentage": int(pourcentage), "douze_mois": douze}


def montee_en_gamme(abonnement: Subscription | None) -> dict | None:
    """Ce que gagnerait un salon au mensuel a passer a l'annuel, ou None.

    Dans la devise de son abonnement, et seulement si les deux prix y sont
    configures : on ne vante pas une economie qu'on ne sait pas chiffrer. Le
    passage n'a rien d'un avoir au prorata — l'annee payee commence a la
    suite de la periode en cours, comme tout paiement anticipe.
    """
    if abonnement is None or abonnement.plan.code != Plan.Code.MONTHLY:
        return None
    offres = {offre.code: offre for offre in offres_payantes()}
    if Plan.Code.MONTHLY not in offres or Plan.Code.YEARLY not in offres:
        return None
    mensuel = tarif(offres[Plan.Code.MONTHLY], abonnement.currency)
    annuel = tarif(offres[Plan.Code.YEARLY], abonnement.currency)
    economie = economie_annuelle(
        mensuel.amount if mensuel else None, annuel.amount if annuel else None
    )
    if not economie:
        return None
    return {
        "vers": Plan.Code.YEARLY,
        "devise": abonnement.currency,
        "montant_annuel": str(annuel.amount),
        "economie": {
            "montant": str(economie["montant"]),
            "pourcentage": economie["pourcentage"],
        },
    }


def moyens_eligibles(pays: str, devise: str) -> list[PlatformPaymentMethod]:
    """Les moyens proposes pour ce pays et cette devise : actifs et complets."""
    candidats = PlatformPaymentMethod.objects.filter(active=True, country=pays, currency=devise)
    return [moyen for moyen in candidats if not moyen.problemes()]


def catalogue_de_paiement() -> list[dict]:
    """Tout ce qu'un salon peut choisir, pays par pays et devise par devise.

    Une devise n'apparait que si elle a au moins un prix **et** au moins un
    moyen de reglement utilisable : proposer un tarif qu'on ne peut payer par
    aucun moyen, ou un moyen sans tarif, laisserait le salon au milieu du
    parcours.
    """
    offres = offres_payantes()
    prix = {
        (p.plan_id, p.currency): p.amount
        for p in PlanPrice.objects.filter(plan__in=offres, active=True)
    }
    moyens: dict[tuple[str, str], list[PlatformPaymentMethod]] = {}
    for moyen in PlatformPaymentMethod.objects.filter(active=True):
        if not moyen.problemes():
            moyens.setdefault((moyen.country, moyen.currency), []).append(moyen)

    pays = []
    for code_pays, nom_pays in Tenant.Country.choices:
        devises = []
        for code_devise, nom_devise in DEVISES_ABONNEMENT:
            disponibles = moyens.get((code_pays, code_devise), [])
            plans = [
                {"plan": offre, "montant": prix[(offre.id, code_devise)]}
                for offre in offres
                if (offre.id, code_devise) in prix
            ]
            if not disponibles or not plans:
                continue
            montants = {p["plan"].code: p["montant"] for p in plans}
            devises.append(
                {
                    "code": code_devise,
                    "nom": str(nom_devise),
                    "plans": plans,
                    "economie": economie_annuelle(
                        montants.get(Plan.Code.MONTHLY), montants.get(Plan.Code.YEARLY)
                    ),
                    "moyens": disponibles,
                }
            )
        if devises:
            pays.append({"code": code_pays, "nom": str(nom_pays), "devises": devises})
    return pays


# ---------------------------------------------------------------------------
# Declarer un paiement
# ---------------------------------------------------------------------------


def normaliser_reference(reference: str) -> str:
    return re.sub(r"\s+", "", reference or "").upper()


def soumettre_paiement(
    *,
    tenant_id,
    utilisateur,
    code_offre: str,
    pays: str,
    devise: str,
    moyen_id,
    reference: str,
    preuve=None,
) -> SubscriptionPaymentRequest:
    """Enregistre la declaration d'un paiement. N'active rien.

    Le montant n'est jamais lu dans la requete : il est calcule ici, a partir
    du tarif configure, et fige sur la demande. A appeler dans le contexte du
    salon ; `preuve` est un fichier deja valide (type et taille).
    """
    plan = Plan.objects.filter(code=code_offre, active=True).first()
    if plan is None or plan.code not in OFFRES_PAYANTES:
        raise PaiementRefuse("Cette offre n'existe pas.", "offre_inconnue")
    if pays not in Tenant.Country.values:
        raise PaiementRefuse("Ce pays n'est pas proposé.", "pays_inconnu")
    if devise not in DEVISES:
        raise PaiementRefuse("Cette devise n'est pas proposée.", "devise_inconnue")

    prix = tarif(plan, devise)
    if prix is None:
        raise PaiementRefuse(
            f"L'offre {plan.name} n'a pas encore de tarif en {devise}. "
            "Choisissez une autre devise.",
            "tarif_absent",
        )

    moyen = PlatformPaymentMethod.objects.filter(pk=moyen_id).first()
    if (
        moyen is None
        or not moyen.est_utilisable
        or moyen.country != pays
        or moyen.currency != devise
    ):
        raise PaiementRefuse(
            "Ce moyen de paiement n'est pas disponible pour ce pays et cette devise.",
            "moyen_indisponible",
        )

    reference = (reference or "").strip()
    normalisee = normaliser_reference(reference)
    # Une reference se recopie d'un recu : des caracteres imprimables, rien
    # d'autre. Un caractere de controle ne vient d'aucune application de
    # paiement, et finirait dans l'administration et dans les e-mails.
    if not reference.isprintable():
        raise PaiementRefuse(
            "La référence contient des caractères non valides. Recopiez-la depuis "
            "votre reçu.",
            "reference_invalide",
        )
    if len(normalisee) < 4:
        raise PaiementRefuse(
            "Indiquez la référence de la transaction, telle qu'elle apparaît "
            "dans votre application de paiement.",
            "reference_requise",
        )

    try:
        with transaction.atomic():
            # Le verrou sur l'abonnement range les declarations du salon en
            # file : deux envois simultanes ne passent pas l'un a cote de
            # l'autre avant que la contrainte ne tranche.
            abonnement = (
                Subscription.objects.select_for_update()
                .select_related("tenant")
                .filter(tenant_id=tenant_id)
                .first()
            )
            if abonnement is None:
                raise PaiementRefuse(
                    "Ce salon n'a pas d'abonnement. Contactez le support.",
                    "abonnement_absent",
                )
            if SubscriptionPaymentRequest.objects.filter(
                tenant_id=tenant_id, status=SubscriptionPaymentRequest.Status.PENDING
            ).exists():
                raise PaiementRefuse(
                    "Un paiement est déjà en cours de vérification. Vous serez "
                    "prévenu(e) dès qu'il aura été examiné.",
                    "demande_en_attente",
                )

            asset = None
            if preuve is not None:
                from apps.media.models import MediaAsset

                # Privee et de genre « preuve » : hors de la vitrine, hors de
                # la mediatheque, lisible seulement par le salon et
                # l'administration.
                asset = MediaAsset.objects.create(
                    tenant_id=tenant_id,
                    file=preuve,
                    content_type=getattr(preuve, "content_type", "") or "image/jpeg",
                    byte_size=getattr(preuve, "size", 0) or 0,
                    kind=MediaAsset.Kind.PROOF,
                    visibility=MediaAsset.Visibility.PRIVATE,
                    alt_text="Preuve de paiement d'abonnement",
                )

            demande = SubscriptionPaymentRequest.objects.create(
                tenant_id=tenant_id,
                subscription=abonnement,
                plan=plan,
                billing_months=plan.billing_months,
                country=pays,
                currency=devise,
                amount=prix.amount,
                payment_method=moyen,
                method_kind=moyen.kind,
                method_label=moyen.libelle,
                method_account_number=moyen.account_number,
                method_account_holder=moyen.account_holder,
                reference=reference,
                reference_normalisee=normalisee,
                proof=asset,
                submitted_by=utilisateur,
            )

            # Une periode echue attend desormais une verification : on le dit.
            avant = abonnement.status
            if acces_de(abonnement).raison in ("grace", "expire") and avant in (
                Subscription.Status.EXPIRED,
                Subscription.Status.ACTIVE,
                Subscription.Status.TRIALING,
                Subscription.Status.PAST_DUE,
            ):
                abonnement.status = Subscription.Status.PENDING_PAYMENT
                abonnement.save(update_fields=["status", "updated_at"])
            _evenement(
                abonnement,
                SubscriptionEvent.Kind.PAYMENT_SUBMITTED,
                avant_statut=avant,
                avant_fin=abonnement.current_period_end,
                acteur=utilisateur,
                demande=demande,
            )
            _journaliser(
                "SUBSCRIPTION_PAYMENT_SUBMITTED",
                tenant_id=tenant_id,
                acteur=utilisateur,
                demande=demande,
            )
    except IntegrityError as erreur:
        # Les contraintes de la base ont le dernier mot, meme quand deux
        # envois se croisent entre la verification et l'ecriture.
        if "reference_de_paiement_unique" in str(erreur):
            raise PaiementRefuse(
                "Cette référence de transaction a déjà été déclarée.",
                "reference_deja_utilisee",
            ) from erreur
        if "une_demande_en_attente_par_salon" in str(erreur):
            raise PaiementRefuse(
                "Un paiement est déjà en cours de vérification.",
                "demande_en_attente",
            ) from erreur
        raise

    _prevenir_apres_validation("paiement_abonnement_a_verifier", demande)
    _ecrire_apres_validation("paiement_recu", demande.tenant_id, demande.id)
    _ecrire_apres_validation("paiement_a_verifier", demande.tenant_id, demande.id)
    return demande


# ---------------------------------------------------------------------------
# Verifier : approuver, refuser
# ---------------------------------------------------------------------------


# Les gestes de l'administration — approuver, refuser, prolonger, suspendre,
# reactiver — sont des operations de plateforme : elles visent un salon
# precis, quel que soit le contexte de la requete qui les declenche. Un
# administrateur qui est aussi membre d'un salon travaille, dans l'admin, sous
# le contexte de son propre salon ; sans `bypass_tenant_context`, ouvrir celui
# d'un autre salon serait refuse. La connexion, elle, retrouve son contexte a
# la sortie du bloc (voir `tenant_context`).


def _tenant_de_la_demande(demande_id):
    return (
        SubscriptionPaymentRequest.all_tenants.using("admin")
        .filter(pk=demande_id)
        .values_list("tenant_id", flat=True)
        .first()
    )


def approuver_paiement(demande_id, *, administrateur, note: str = "") -> SubscriptionPaymentRequest:
    """Approuve une demande et accorde sa periode, une seule fois.

    Verrouille la demande puis l'abonnement. Si la demande n'est plus en
    attente — deja approuvee par un autre clic, refusee entre-temps —, rien
    ne change et l'erreur le dit.
    """
    tenant_id = _tenant_de_la_demande(demande_id)
    if tenant_id is None:
        raise PaiementRefuse("Ce paiement n'existe pas.", "demande_inconnue")

    with bypass_tenant_context(), tenant_context(tenant_id):
        demande = (
            SubscriptionPaymentRequest.objects.select_for_update()
            .select_related("plan")
            .get(pk=demande_id)
        )
        if demande.status != SubscriptionPaymentRequest.Status.PENDING:
            raise PaiementRefuse(
                f"Ce paiement a déjà été traité ({demande.get_status_display().lower()}).",
                "deja_traitee",
            )

        abonnement = (
            Subscription.objects.select_for_update()
            .select_related("tenant", "plan")
            .get(pk=demande.subscription_id)
        )
        maintenant = timezone.now()
        avant_statut = abonnement.status
        avant_fin = abonnement.current_period_end

        debut, fin, ancre, mois = _periode_accordee(abonnement, demande.billing_months, maintenant)

        facture = Invoice.objects.create(
            tenant_id=tenant_id,
            subscription=abonnement,
            number=next_invoice_number(),
            period_start=debut,
            period_end=fin,
            amount=demande.amount,
            currency=demande.currency,
            label=f"Abonnement {demande.plan.name}",
            status=Invoice.Status.ISSUED,
            issued_at=maintenant,
            due_at=maintenant,
        )

        abonnement.plan = demande.plan
        abonnement.price_amount = demande.amount
        abonnement.currency = demande.currency
        abonnement.period_anchor = ancre
        abonnement.anchor_months = mois
        # Une periode qui prolonge la precedente garde son debut ; une periode
        # neuve en ouvre un.
        if debut != avant_fin or avant_statut not in (Subscription.Status.ACTIVE,):
            abonnement.current_period_start = debut
        abonnement.current_period_end = fin
        # Une suspension est une decision distincte : un paiement ne la leve
        # pas. Tout le reste redevient actif.
        if abonnement.status != Subscription.Status.SUSPENDED:
            abonnement.status = Subscription.Status.ACTIVE
        abonnement.save()

        mark_invoice_paid(
            facture,
            method=METHODE_FACTURE.get(demande.method_kind, Invoice.Method.OTHER),
            reference=demande.reference,
        )

        demande.status = SubscriptionPaymentRequest.Status.APPROVED
        demande.reviewed_by = administrateur
        demande.reviewed_at = maintenant
        demande.review_note = (note or "").strip()
        demande.period_start = debut
        demande.period_end = fin
        demande.invoice = facture
        demande.save()

        _evenement(
            abonnement,
            SubscriptionEvent.Kind.PAYMENT_APPROVED,
            avant_statut=avant_statut,
            avant_fin=avant_fin,
            acteur=administrateur,
            demande=demande,
            note=demande.review_note,
        )
        _journaliser(
            "SUBSCRIPTION_PAYMENT_APPROVED",
            tenant_id=tenant_id,
            acteur=administrateur,
            demande=demande,
            extra={"period_start": debut.isoformat(), "period_end": fin.isoformat()},
        )

    _prevenir_apres_validation("abonnement_decide", demande)
    _ecrire_apres_validation("paiement_valide", demande.tenant_id, demande.id)
    return demande


def _periode_accordee(abonnement: Subscription, mois_payes: int, maintenant: datetime):
    """Debut, fin, ancre et mois couverts de la periode qu'accorde un paiement.

    Une periode en cours — essai compris — est prolongee a partir de sa fin.
    Sinon, la periode commence maintenant. La suite de periodes payees garde
    son ancre, pour que les echeances tombent toujours le meme jour.
    """
    fin_actuelle = abonnement.current_period_end
    en_cours = (
        abonnement.status not in (Subscription.Status.CANCELLED,)
        and fin_actuelle is not None
        and fin_actuelle > maintenant
    )
    debut = fin_actuelle if en_cours else maintenant

    suite_payee = (
        en_cours
        and abonnement.period_anchor is not None
        and abonnement.status != Subscription.Status.TRIALING
    )
    if suite_payee:
        ancre = abonnement.period_anchor
        mois = abonnement.anchor_months + mois_payes
    else:
        ancre = debut
        mois = mois_payes
    fin = ajouter_mois(ancre, mois, _fuseau(abonnement))
    return debut, fin, ancre, mois


def refuser_paiement(
    demande_id, *, administrateur, motif: str, note: str = ""
) -> SubscriptionPaymentRequest:
    """Refuse une demande. Le motif est obligatoire : le salon le lira."""
    motif = (motif or "").strip()
    if not motif:
        raise PaiementRefuse(
            "Indiquez le motif du refus : il sera montré au salon.", "motif_requis"
        )

    tenant_id = _tenant_de_la_demande(demande_id)
    if tenant_id is None:
        raise PaiementRefuse("Ce paiement n'existe pas.", "demande_inconnue")

    with bypass_tenant_context(), tenant_context(tenant_id):
        demande = SubscriptionPaymentRequest.objects.select_for_update().get(pk=demande_id)
        if demande.status != SubscriptionPaymentRequest.Status.PENDING:
            raise PaiementRefuse(
                f"Ce paiement a déjà été traité ({demande.get_status_display().lower()}).",
                "deja_traitee",
            )
        abonnement = (
            Subscription.objects.select_for_update()
            .select_related("tenant")
            .get(pk=demande.subscription_id)
        )
        maintenant = timezone.now()

        demande.status = SubscriptionPaymentRequest.Status.REJECTED
        demande.reviewed_by = administrateur
        demande.reviewed_at = maintenant
        demande.rejection_reason = motif[:255]
        demande.review_note = (note or "").strip()
        demande.save()

        avant = abonnement.status
        if abonnement.status == Subscription.Status.PENDING_PAYMENT:
            abonnement.status = (
                Subscription.Status.ACTIVE
                if abonnement.current_period_end > maintenant
                else Subscription.Status.EXPIRED
            )
            abonnement.save(update_fields=["status", "updated_at"])

        _evenement(
            abonnement,
            SubscriptionEvent.Kind.PAYMENT_REJECTED,
            avant_statut=avant,
            avant_fin=abonnement.current_period_end,
            acteur=administrateur,
            demande=demande,
            note=motif,
        )
        _journaliser(
            "SUBSCRIPTION_PAYMENT_REJECTED",
            tenant_id=tenant_id,
            acteur=administrateur,
            demande=demande,
            extra={"motif": motif},
        )

    _prevenir_apres_validation("abonnement_decide", demande)
    _ecrire_apres_validation("paiement_refuse", demande.tenant_id, demande.id)
    return demande


# ---------------------------------------------------------------------------
# Gestes exceptionnels de l'administration
# ---------------------------------------------------------------------------


def prolonger_manuellement(tenant_id, *, administrateur, mois: int, note: str) -> Subscription:
    """Accorde des mois sans paiement : geste commercial, correction, litige.

    Exceptionnel, et trace comme tel : note obligatoire, evenement
    d'historique, journal d'audit. Aucune facture n'est emise — rien n'a ete
    encaisse.
    """
    note = (note or "").strip()
    if not note:
        raise PaiementRefuse("Une prolongation manuelle doit être justifiée.", "note_requise")
    if mois not in (1, 12):
        raise PaiementRefuse("Une prolongation porte sur 1 ou 12 mois.", "duree_invalide")

    with bypass_tenant_context(), tenant_context(tenant_id):
        abonnement = (
            Subscription.objects.select_for_update()
            .select_related("tenant")
            .get(tenant_id=tenant_id)
        )
        maintenant = timezone.now()
        avant_statut = abonnement.status
        avant_fin = abonnement.current_period_end
        debut, fin, ancre, total = _periode_accordee(abonnement, mois, maintenant)

        if debut != avant_fin:
            abonnement.current_period_start = debut
        abonnement.current_period_end = fin
        abonnement.period_anchor = ancre
        abonnement.anchor_months = total
        if abonnement.status != Subscription.Status.SUSPENDED:
            abonnement.status = Subscription.Status.ACTIVE
        abonnement.save()

        _evenement(
            abonnement,
            SubscriptionEvent.Kind.MANUAL_EXTENSION,
            avant_statut=avant_statut,
            avant_fin=avant_fin,
            acteur=administrateur,
            note=f"{mois} mois — {note}",
        )
        _journaliser(
            "SUBSCRIPTION_MANUAL_CHANGE",
            tenant_id=tenant_id,
            acteur=administrateur,
            extra={"geste": "prolongation", "mois": mois, "note": note, "fin": fin.isoformat()},
        )
        _ecrire_apres_validation("prolongation", tenant_id)
        return abonnement


def suspendre(tenant_id, *, administrateur, motif: str) -> Subscription:
    """Coupe l'acces d'un salon, quelles que soient ses dates."""
    motif = (motif or "").strip()
    if not motif:
        raise PaiementRefuse("Une suspension doit être motivée.", "motif_requis")
    with bypass_tenant_context(), tenant_context(tenant_id):
        abonnement = Subscription.objects.select_for_update().get(tenant_id=tenant_id)
        if abonnement.status == Subscription.Status.SUSPENDED:
            raise PaiementRefuse("Cet abonnement est déjà suspendu.", "deja_suspendu")
        avant = abonnement.status
        abonnement.status = Subscription.Status.SUSPENDED
        abonnement.save(update_fields=["status", "updated_at"])
        _evenement(
            abonnement,
            SubscriptionEvent.Kind.SUSPENDED,
            avant_statut=avant,
            avant_fin=abonnement.current_period_end,
            acteur=administrateur,
            note=motif,
        )
        _journaliser(
            "SUBSCRIPTION_MANUAL_CHANGE",
            tenant_id=tenant_id,
            acteur=administrateur,
            extra={"geste": "suspension", "motif": motif},
        )
        _ecrire_apres_validation("suspension", tenant_id)
        return abonnement


def reactiver(tenant_id, *, administrateur, note: str = "") -> Subscription:
    """Leve une suspension. Le statut redevient celui que disent les dates."""
    with bypass_tenant_context(), tenant_context(tenant_id):
        abonnement = Subscription.objects.select_for_update().get(tenant_id=tenant_id)
        if abonnement.status != Subscription.Status.SUSPENDED:
            raise PaiementRefuse("Cet abonnement n'est pas suspendu.", "non_suspendu")
        maintenant = timezone.now()
        en_essai = (
            abonnement.trial_ends_at is not None
            and abonnement.period_anchor is None
            and abonnement.current_period_end > maintenant
        )
        if abonnement.current_period_end > maintenant:
            abonnement.status = (
                Subscription.Status.TRIALING if en_essai else Subscription.Status.ACTIVE
            )
        else:
            abonnement.status = Subscription.Status.EXPIRED
        abonnement.save(update_fields=["status", "updated_at"])
        _evenement(
            abonnement,
            SubscriptionEvent.Kind.REACTIVATED,
            avant_statut=Subscription.Status.SUSPENDED,
            avant_fin=abonnement.current_period_end,
            acteur=administrateur,
            note=note,
        )
        _journaliser(
            "SUBSCRIPTION_MANUAL_CHANGE",
            tenant_id=tenant_id,
            acteur=administrateur,
            extra={"geste": "reactivation", "note": note},
        )
        _ecrire_apres_validation("reactivation", tenant_id)
        return abonnement


# ---------------------------------------------------------------------------
# Outils
# ---------------------------------------------------------------------------


def _journaliser(action: str, *, tenant_id, acteur=None, demande=None, extra=None) -> None:
    from apps.audit.models import AuditLog

    metadata = dict(extra or {})
    if demande is not None:
        metadata.update(
            {
                "plan": demande.plan.code,
                "amount": str(demande.amount),
                "currency": demande.currency,
                "method": demande.method_kind,
                "reference": demande.reference,
            }
        )
    AuditLog.objects.create(
        tenant_id=tenant_id,
        actor_user=acteur,
        action=getattr(AuditLog.Action, action),
        resource_type="subscription_payment" if demande is not None else "subscription",
        resource_id=str(demande.id) if demande is not None else "",
        metadata=metadata,
    )


def _prevenir_apres_validation(evenement: str, demande) -> None:
    """Une notification part apres la validation, et ne casse jamais rien.

    Apres : si la transaction etait annulee, on aurait annonce une decision
    qui n'a pas eu lieu. Sans casser : une panne de notification ne doit pas
    faire croire a l'administrateur que son approbation a echoue.

    Le module des notifications est importe a l'envoi : il importe lui-meme
    des modeles d'autres applications, et l'importer au chargement de
    celui-ci creerait un cycle.
    """

    def envoyer():
        try:
            from apps.notifications import evenements

            getattr(evenements, evenement)(demande)
        except Exception:
            logger.exception("Notification d'abonnement non déposée.")

    transaction.on_commit(envoyer)


def next_invoice_number() -> str:
    """Numero de facture, tire d'une sequence PostgreSQL.

    Le compteur porte sur toute la plateforme et non par salon : c'est elle
    qui vend, sa numerotation doit donc etre continue d'un client a l'autre.

    Compter les lignes existantes ne marcherait pas ici : les politiques RLS
    masquent les factures des autres salons, et une transaction ouverte cache
    celles qu'on vient d'ecrire. La sequence, elle, est atomique et
    indifferente aux deux.
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT nextval('billing_invoice_number_seq')")
        sequence = cursor.fetchone()[0]
    return f"F{sequence:06d}"


@transaction.atomic
def issue_invoice(subscription: Subscription, *, label: str = "") -> Invoice:
    """Emet la facture de la periode ecoulee et ouvre la suivante.

    Reste de l'ancien mode « a terme echu », garde pour l'action
    d'administration sur un abonnement a prix negocie.
    """
    now = timezone.now()
    invoice = Invoice.objects.create(
        tenant_id=subscription.tenant_id,
        subscription=subscription,
        number=next_invoice_number(),
        period_start=subscription.current_period_start,
        period_end=subscription.current_period_end,
        amount=subscription.price_amount,
        currency=subscription.currency,
        label=label or f"Abonnement {subscription.plan.name}",
        status=Invoice.Status.ISSUED,
        issued_at=now,
        due_at=now + timedelta(days=PAYMENT_TERMS_DAYS),
    )

    subscription.current_period_start = subscription.current_period_end
    subscription.current_period_end = subscription.current_period_end + timedelta(days=PERIOD_DAYS)
    subscription.save(update_fields=["current_period_start", "current_period_end", "updated_at"])
    return invoice


def mark_invoice_paid(invoice: Invoice, *, method: str, reference: str = "") -> Invoice:
    if invoice.status == Invoice.Status.PAID:
        raise BillingError("Cette facture est déjà réglée.")
    if invoice.status == Invoice.Status.VOID:
        raise BillingError("Cette facture est annulée.")

    invoice.status = Invoice.Status.PAID
    invoice.paid_at = timezone.now()
    invoice.payment_method = method
    invoice.payment_reference = reference
    invoice.save(
        update_fields=[
            "status",
            "paid_at",
            "payment_method",
            "payment_reference",
            "updated_at",
        ]
    )

    # L'abonnement devient une charge du salon, sans qu'il ait a la saisir.
    #
    # C'est une depense comme le loyer : il la subit, il ne la decide pas. Ce
    # serait absurde que le seul poste que la plateforme connait au centime
    # pres soit le seul que le salon doive recopier a la main.
    from apps.finance.services import record_subscription_expense

    record_subscription_expense(invoice)

    # Et la recette de la plateforme, de son cote du registre.
    from apps.platformledger.services import record_subscription_income

    record_subscription_income(invoice)

    # Un salon suspendu pour impaye retrouve son service des le reglement.
    subscription = invoice.subscription
    if subscription.status == Subscription.Status.PAST_DUE:
        subscription.status = Subscription.Status.ACTIVE
        subscription.save(update_fields=["status", "updated_at"])

    return invoice


def _ecrire_apres_validation(genre: str, tenant_id, demande_id=None) -> None:
    """Un e-mail d'abonnement part apres la validation, par Celery.

    Apres, pour la meme raison que les notifications : jamais l'annonce d'une
    decision annulee. Par Celery, pour qu'un serveur de courrier lent ne
    fasse pas attendre l'administrateur. Et sans casser : un courtier de
    taches injoignable ne doit pas faire echouer une approbation.
    """

    def deposer():
        try:
            from .tasks import envoyer_courrier_abonnement

            envoyer_courrier_abonnement.delay(
                genre, str(tenant_id), str(demande_id) if demande_id else None
            )
        except Exception:
            logger.exception("E-mail d'abonnement %s non déposé.", genre)

    transaction.on_commit(deposer)


def annoncer_tarif(prix: PlanPrice, ancien) -> None:
    """Annonce aux salons un tarif dont le montant vient de changer."""
    if ancien is None or prix.amount == ancien or not prix.active:
        return

    def deposer():
        try:
            from .tasks import annoncer_changement_de_tarif

            annoncer_changement_de_tarif.delay(str(prix.pk), str(ancien))
        except Exception:
            logger.exception("Annonce de tarif non déposée.")

    transaction.on_commit(deposer)


def run_billing_cycle(now=None) -> dict:
    """Balaye les salons et fait avancer leur abonnement.

    Deux actions, toutes deux idempotentes :

      - un salon sans abonnement en recoit un, en essai (voir `acces_de`) ;
      - une periode echue — essai ou periode payee — passe en « expire », ou
        en « paiement en verification » si un paiement attend.

    L'acces, lui, ne depend pas de ce passage : il se calcule sur les dates
    (`acces_de`). Cette tache tient seulement les statuts a jour pour
    l'administration et pour les ecrans.

    Il n'y a plus de facture emise d'office ni de conversion gratuite en fin
    d'essai : une periode payee ne s'ouvre que par un paiement approuve.
    """
    now = now or timezone.now()
    crees = expires = 0

    for tenant in Tenant.objects.all().only("id"):
        with tenant_context(tenant.id):
            abonnement = (
                Subscription.objects.select_related("tenant").filter(tenant_id=tenant.id).first()
            )
            if abonnement is None:
                try:
                    start_trial(Tenant.objects.get(pk=tenant.id))
                    crees += 1
                except BillingError:
                    logger.warning("Essai impossible pour %s : aucune offre d'essai.", tenant.id)
                continue

            echu = abonnement.current_period_end <= now
            if echu and abonnement.status in (
                Subscription.Status.TRIALING,
                Subscription.Status.ACTIVE,
                Subscription.Status.PAST_DUE,
            ):
                avant = abonnement.status
                en_attente = SubscriptionPaymentRequest.objects.filter(
                    tenant_id=tenant.id,
                    status=SubscriptionPaymentRequest.Status.PENDING,
                ).exists()
                abonnement.status = (
                    Subscription.Status.PENDING_PAYMENT
                    if en_attente
                    else Subscription.Status.EXPIRED
                )
                abonnement.save(update_fields=["status", "updated_at"])
                _evenement(
                    abonnement,
                    SubscriptionEvent.Kind.EXPIRED,
                    avant_statut=avant,
                    avant_fin=abonnement.current_period_end,
                )
                expires += 1

    logger.info(
        "Cycle d'abonnement : %s essai(s) ouvert(s), %s période(s) échue(s).",
        crees,
        expires,
    )
    return {"trials_started": crees, "expired": expires}
