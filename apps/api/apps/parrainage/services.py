"""Le parrainage, cote serveur : codes, detection, admissibilite, remises.

Tout calcul se fait ici. Le navigateur n'envoie qu'un code ; il ne choisit
ni son parrain apres coup, ni un pourcentage, ni un montant.

---------------------------------------------------------------------------
Integrite
---------------------------------------------------------------------------

  - **Idempotence** : chaque remise porte la reference de l'evenement qui la
    cree (`inscription:<parrainage>`, `paiement:<demande>`), unique en base.
    Un evenement rejoue retrouve la remise existante au lieu d'en creer une
    seconde.
  - **Pas de remise sur un paiement non confirme** : la remise « paiement »
    n'est creee qu'a l'approbation, dans la meme transaction.
  - **Pas de double usage** : les remises sont verrouillees le temps de la
    reservation, et un salon n'a jamais qu'une demande de paiement en
    attente (contrainte en base, cote abonnements).
  - **Reservation, puis consommation** : une remise reservee par une demande
    est consommee a l'approbation, rendue au refus.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import CodeParrainage, Parrainage, Remise

logger = logging.getLogger(__name__)

POURCENTAGE = Decimal("10")
PLAFOND_PAR_PAIEMENT = Decimal("30")
VALIDITE = timedelta(days=365)
DELAI_ADMISSIBILITE = timedelta(days=14)
REMISES_PAIEMENT_MAX = 12
# Au-dela, sur 30 jours, les nouveaux filleuls d'un meme parrain attendent
# une validation humaine : c'est la signature d'une fabrique de faux salons.
ADMISSIBLES_PAR_MOIS = 10
# Sans chiffres ni lettres ambigus (0/O, 1/I/L) : un code se recopie.
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
LONGUEUR_CODE = 10
DEVISES_SANS_DECIMALES = {"XAF", "CDF"}


class CodeInconnu(ValueError):
    pass


def actif() -> bool:
    return bool(getattr(settings, "PARRAINAGE_ACTIF", True))


# ---------------------------------------------------------------------------
# Codes
# ---------------------------------------------------------------------------


def _nouveau_code() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(LONGUEUR_CODE))


def _creer_code(**titulaire) -> CodeParrainage:
    for _ in range(5):
        try:
            with transaction.atomic():
                return CodeParrainage.objects.create(code=_nouveau_code(), **titulaire)
        except IntegrityError:
            existant = CodeParrainage.objects.filter(**titulaire).first()
            if existant is not None:
                return existant
    raise RuntimeError("Impossible de générer un code de parrainage unique.")


def code_du_salon(tenant) -> CodeParrainage:
    return CodeParrainage.objects.filter(tenant=tenant).first() or _creer_code(tenant=tenant)


def code_de_l_utilisateur(user) -> CodeParrainage:
    return CodeParrainage.objects.filter(user=user).first() or _creer_code(user=user)


def normaliser_code(saisie: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (saisie or "").upper())


def resoudre(saisie: str) -> CodeParrainage | None:
    code = normaliser_code(saisie)
    if not code:
        return None
    return (
        CodeParrainage.objects.select_related("tenant", "user")
        .filter(code=code, actif=True)
        .first()
    )


def lien(code: CodeParrainage) -> str:
    base = getattr(settings, "APP_BASE_URL", "").rstrip("/")
    return f"{base}/inscription?parrain={code.code}"


# ---------------------------------------------------------------------------
# Detection, a l'inscription du filleul
# ---------------------------------------------------------------------------


def empreinte(valeur: str) -> str:
    if not valeur:
        return ""
    return hmac.new(
        settings.SECRET_KEY.encode(), valeur.strip().lower().encode(), hashlib.sha256
    ).hexdigest()


def _chiffres(valeur: str) -> str:
    return re.sub(r"\D", "", valeur or "")


def _meme_personne(proprietaire, autre) -> bool:
    if autre is None:
        return False
    if autre.pk == proprietaire.pk:
        return True
    if (autre.email or "").strip().lower() == (proprietaire.email or "").strip().lower():
        return True
    tel_a, tel_b = _chiffres(autre.phone), _chiffres(proprietaire.phone)
    return bool(tel_a) and len(tel_a) >= 6 and tel_a == tel_b


def _motif_de_refus(code: CodeParrainage, filleul, proprietaire) -> str:
    """Pourquoi ce parrainage ne peut pas etre retenu, ou chaine vide."""
    from apps.accounts.models import Membership

    if code.user_id and _meme_personne(proprietaire, code.user):
        return "Le parrain et le propriétaire du salon filleul sont la même personne."
    if code.tenant_id:
        if code.tenant_id == filleul.pk:
            return "Un salon ne peut pas se parrainer lui-même."
        membres = Membership.objects.filter(tenant_id=code.tenant_id).select_related("user")
        if any(_meme_personne(proprietaire, m.user) for m in membres):
            return "Le propriétaire du salon filleul est déjà membre du salon parrain."
    return ""


def detecter(filleul, proprietaire, saisie: str, ip: str = "") -> Parrainage | None:
    """Enregistre le parrainage a l'inscription. A appeler dans sa transaction.

    Le parrain est fige ici : aucune route ne permet de le changer ensuite.
    """
    if not actif() or not saisie:
        return None
    code = resoudre(saisie)
    if code is None:
        raise CodeInconnu("Code de parrainage inconnu ou désactivé.")

    motif = _motif_de_refus(code, filleul, proprietaire)
    parrainage = Parrainage.objects.create(
        filleul=filleul,
        code=code,
        type_parrain=code.type_parrain,
        parrain_tenant_id=code.tenant_id,
        parrain_user_id=code.user_id,
        statut=Parrainage.Statut.REFUSE if motif else Parrainage.Statut.EN_VERIFICATION,
        motif=motif,
        empreinte_ip=empreinte(ip),
    )
    _journaliser("REFERRAL_DETECTED", parrainage, extra={"refuse": bool(motif), "motif": motif})
    return parrainage


def noter_publication(tenant, quand: datetime | None = None) -> None:
    """Le salon filleul vient d'etre publie : le delai de 14 jours part d'ici."""
    Parrainage.objects.filter(filleul=tenant, publie_le__isnull=True).update(
        publie_le=quand or timezone.now()
    )


# ---------------------------------------------------------------------------
# Admissibilite et remises
# ---------------------------------------------------------------------------


def _beneficiaire(parrainage: Parrainage) -> dict:
    if parrainage.type_parrain == Parrainage.TypeParrain.SALON:
        return {"beneficiaire_tenant_id": parrainage.parrain_tenant_id}
    return {"beneficiaire_user_id": parrainage.parrain_user_id}


def _creer_remise(
    parrainage: Parrainage, declencheur: str, reference: str, maintenant
) -> Remise | None:
    """Idempotent : un evenement deja traite retrouve sa remise."""
    beneficiaire = _beneficiaire(parrainage)
    if not any(beneficiaire.values()):
        return None  # parrain supprime depuis
    remise, creee = Remise.objects.get_or_create(
        reference=reference,
        defaults={
            "parrainage": parrainage,
            "filleul_nom": parrainage.filleul.name[:120],
            "declencheur": declencheur,
            "pourcentage": POURCENTAGE,
            "expire_le": maintenant + VALIDITE,
            **beneficiaire,
        },
    )
    if creee:
        _journaliser(
            "REFERRAL_REWARD_CREATED",
            parrainage,
            extra={"remise": str(remise.id), "declencheur": declencheur, "reference": reference},
        )
    return remise


def rendre_admissible(parrainage_id, maintenant=None, via: str = "delai") -> Parrainage | None:
    maintenant = maintenant or timezone.now()
    with transaction.atomic():
        parrainage = (
            Parrainage.objects.select_for_update()
            .select_related("filleul")
            .filter(pk=parrainage_id)
            .first()
        )
        if parrainage is None or parrainage.statut != Parrainage.Statut.EN_VERIFICATION:
            return parrainage
        parrainage.statut = Parrainage.Statut.ADMISSIBLE
        parrainage.admissible_le = maintenant
        parrainage.revue_requise = False
        parrainage.save(update_fields=["statut", "admissible_le", "revue_requise", "maj_le"])
        _journaliser("REFERRAL_ELIGIBLE", parrainage, extra={"via": via})
        _creer_remise(
            parrainage, Remise.Declencheur.INSCRIPTION, f"inscription:{parrainage.pk}", maintenant
        )
        return parrainage


def _salon_suspendu(tenant_id) -> bool:
    from apps.billing.models import Subscription
    from apps.common.db import bypass_tenant_context, tenant_context

    with bypass_tenant_context(), tenant_context(tenant_id):
        return Subscription.objects.filter(
            tenant_id=tenant_id, status=Subscription.Status.SUSPENDED
        ).exists()


def _meme_parrain(parrainage: Parrainage) -> dict:
    if parrainage.parrain_tenant_id:
        return {"parrain_tenant_id": parrainage.parrain_tenant_id}
    return {"parrain_user_id": parrainage.parrain_user_id}


def evaluer(maintenant=None) -> dict:
    """Passe quotidienne : fait avancer les parrainages en verification."""
    from apps.tenants.models import Tenant

    maintenant = maintenant or timezone.now()
    admis = revues = 0
    if not actif():
        return {"admissibles": 0, "revues": 0, "expirees": 0}
    for parrainage in Parrainage.objects.select_related("filleul").filter(
        statut=Parrainage.Statut.EN_VERIFICATION
    ):
        filleul = parrainage.filleul
        if filleul.status != Tenant.Status.ACTIVE:
            continue
        if parrainage.publie_le is None:
            # Publie avant que la passe ne le voie : le delai part d'ici.
            Parrainage.objects.filter(pk=parrainage.pk).update(publie_le=maintenant)
            continue
        if maintenant - parrainage.publie_le < DELAI_ADMISSIBILITE or _salon_suspendu(filleul.pk):
            continue
        if parrainage.revue_requise:
            continue
        recents = 0
        if parrainage.parrain_tenant_id or parrainage.parrain_user_id:
            recents = Parrainage.objects.filter(
                **_meme_parrain(parrainage),
                statut=Parrainage.Statut.ADMISSIBLE,
                admissible_le__gte=maintenant - timedelta(days=30),
            ).count()
        if recents >= ADMISSIBLES_PAR_MOIS:
            Parrainage.objects.filter(pk=parrainage.pk).update(revue_requise=True)
            _journaliser("REFERRAL_REVIEW_REQUIRED", parrainage, extra={"recents": recents})
            revues += 1
            continue
        rendre_admissible(parrainage.pk, maintenant, via="delai")
        admis += 1
    expirees = expirer(maintenant)
    return {"admissibles": admis, "revues": revues, "expirees": expirees}


def recompenser_paiement(demande, maintenant=None) -> None:
    """Un paiement du filleul vient d'etre approuve. Dans la transaction d'approbation."""
    if not actif():
        return
    maintenant = maintenant or timezone.now()
    parrainage = Parrainage.objects.filter(filleul_id=demande.tenant_id).first()
    if parrainage is None or parrainage.statut in (
        Parrainage.Statut.REFUSE,
        Parrainage.Statut.INVALIDE,
    ):
        return
    if parrainage.statut == Parrainage.Statut.EN_VERIFICATION:
        # Un paiement approuve prouve le salon mieux qu'un delai.
        parrainage = rendre_admissible(parrainage.pk, maintenant, via="premier_paiement")
    if parrainage.type_parrain != Parrainage.TypeParrain.SALON:
        return  # une cliente marraine n'est recompensee qu'une fois
    deja = Remise.objects.filter(
        parrainage=parrainage, declencheur=Remise.Declencheur.PAIEMENT
    ).count()
    if deja >= REMISES_PAIEMENT_MAX:
        return
    _creer_remise(parrainage, Remise.Declencheur.PAIEMENT, f"paiement:{demande.pk}", maintenant)


def expirer(maintenant=None) -> int:
    maintenant = maintenant or timezone.now()
    return Remise.objects.filter(statut=Remise.Statut.DISPONIBLE, expire_le__lte=maintenant).update(
        statut=Remise.Statut.EXPIREE, maj_le=maintenant
    )


# ---------------------------------------------------------------------------
# Application a un paiement d'abonnement
# ---------------------------------------------------------------------------


def arrondir(montant: Decimal, devise: str) -> Decimal:
    pas = Decimal("1") if devise in DEVISES_SANS_DECIMALES else Decimal("0.01")
    return montant.quantize(pas, rounding=ROUND_HALF_UP)


@dataclass
class Calcul:
    montant_catalogue: Decimal
    montant: Decimal
    pourcentage: Decimal = Decimal("0")
    remise: Decimal = Decimal("0")
    remises: list = field(default_factory=list)
    parts: dict = field(default_factory=dict)  # id de remise -> montant deduit


def utilisables(tenant_id, utilisateur, maintenant=None, verrouiller: bool = False):
    """Les remises applicables au prochain paiement de ce salon, par ce proprietaire.

    Celles du salon, et celles de l'utilisateur lui-meme (une cliente
    marraine qui a ouvert un salon). Les plus proches de l'expiration d'abord.
    """
    from django.db.models import Q

    maintenant = maintenant or timezone.now()
    if not actif():
        return []
    filtre = Q(beneficiaire_tenant_id=tenant_id)
    if getattr(utilisateur, "pk", None):
        filtre |= Q(beneficiaire_user_id=utilisateur.pk)
    requete = Remise.objects.filter(
        filtre, statut=Remise.Statut.DISPONIBLE, expire_le__gt=maintenant
    ).order_by("expire_le", "cree_le")
    if verrouiller:
        requete = requete.select_for_update()
    remises, total = [], Decimal("0")
    for remise in requete:
        if total + remise.pourcentage > PLAFOND_PAR_PAIEMENT:
            break
        remises.append(remise)
        total += remise.pourcentage
    return remises


def calculer(montant_catalogue: Decimal, devise: str, remises) -> Calcul:
    """Le montant a payer, remises deduites. Chaque remise porte sa part, arrondie."""
    parts = {r.id: arrondir(montant_catalogue * r.pourcentage / 100, devise) for r in remises}
    deduction = min(sum(parts.values(), Decimal("0")), montant_catalogue)
    return Calcul(
        montant_catalogue=montant_catalogue,
        montant=montant_catalogue - deduction,
        pourcentage=sum((r.pourcentage for r in remises), Decimal("0")),
        remise=deduction,
        remises=list(remises),
        parts=parts,
    )


def reserver(demande, calcul: Calcul) -> None:
    """Les remises du calcul sont liees a la demande. Dans sa transaction."""
    for remise in calcul.remises:
        Remise.objects.filter(pk=remise.pk, statut=Remise.Statut.DISPONIBLE).update(
            statut=Remise.Statut.RESERVEE,
            demande=demande,
            montant_deduit=calcul.parts[remise.id],
            devise=demande.currency,
        )


def consommer(demande, maintenant=None) -> None:
    """La demande est approuvee : ses remises sont utilisees."""
    maintenant = maintenant or timezone.now()
    Remise.objects.filter(demande=demande, statut=Remise.Statut.RESERVEE).update(
        statut=Remise.Statut.UTILISEE, utilisee_le=maintenant
    )


def liberer(demande, maintenant=None) -> None:
    """La demande est refusee : ses remises redeviennent disponibles (ou expirent)."""
    maintenant = maintenant or timezone.now()
    for remise in Remise.objects.select_for_update().filter(
        demande=demande, statut=Remise.Statut.RESERVEE
    ):
        remise.statut = (
            Remise.Statut.DISPONIBLE if remise.expire_le > maintenant else Remise.Statut.EXPIREE
        )
        remise.demande = None
        remise.montant_deduit = None
        remise.devise = ""
        remise.save(update_fields=["statut", "demande", "montant_deduit", "devise", "maj_le"])


# ---------------------------------------------------------------------------
# Gestes de l'administration : motives et journalises
# ---------------------------------------------------------------------------


def valider_manuellement(parrainage: Parrainage, administrateur, motif: str) -> None:
    _exiger_motif(motif)
    if parrainage.statut != Parrainage.Statut.EN_VERIFICATION:
        raise ValueError("Seul un parrainage en vérification se valide.")
    rendre_admissible(parrainage.pk, via="administration")
    _journaliser(
        "REFERRAL_ADMIN", parrainage, administrateur, {"geste": "validation", "motif": motif}
    )


def invalider(parrainage: Parrainage, administrateur, motif: str) -> int:
    """Invalide le parrainage et annule ses remises encore disponibles.

    Les remises reservees ou utilisees ne sont pas touchees : la demande de
    paiement en cours se tranche a part (refus = remise liberee puis annulee
    a la prochaine invalidation), et une remise utilisee reste un fait.
    """
    _exiger_motif(motif)
    with transaction.atomic():
        Parrainage.objects.filter(pk=parrainage.pk).update(
            statut=Parrainage.Statut.INVALIDE, motif=motif[:255]
        )
        annulees = Remise.objects.filter(
            parrainage=parrainage, statut=Remise.Statut.DISPONIBLE
        ).update(statut=Remise.Statut.ANNULEE, annulee_le=timezone.now(), motif=motif[:255])
        _journaliser(
            "REFERRAL_ADMIN",
            parrainage,
            administrateur,
            {"geste": "invalidation", "motif": motif, "remises_annulees": annulees},
        )
    return annulees


def annuler_remise(remise: Remise, administrateur, motif: str) -> None:
    _exiger_motif(motif)
    if remise.statut != Remise.Statut.DISPONIBLE:
        raise ValueError("Seule une remise disponible s'annule.")
    remise.statut = Remise.Statut.ANNULEE
    remise.annulee_le = timezone.now()
    remise.motif = motif[:255]
    remise.save(update_fields=["statut", "annulee_le", "motif", "maj_le"])
    if remise.parrainage_id:
        _journaliser(
            "REFERRAL_ADMIN",
            remise.parrainage,
            administrateur,
            {"geste": "annulation_remise", "remise": str(remise.pk), "motif": motif},
        )


def _exiger_motif(motif: str) -> None:
    if len((motif or "").strip()) < 10:
        raise ValueError("Indiquez un motif (10 caractères au moins).")


def _journaliser(action: str, parrainage: Parrainage, acteur=None, extra=None) -> None:
    from apps.audit.models import AuditLog

    # Dans la transaction de l'evenement : une trace ne survit pas a un
    # evenement annule, et un evenement ne passe pas sans sa trace.
    AuditLog.objects.create(
        tenant_id=parrainage.filleul_id,
        actor_user=acteur,
        action=getattr(AuditLog.Action, action),
        resource_type="parrainage",
        resource_id=str(parrainage.pk),
        metadata={"statut": parrainage.statut, **(extra or {})},
    )
