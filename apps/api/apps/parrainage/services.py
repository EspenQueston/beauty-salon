"""Le parrainage, cote serveur : codes, detection, admissibilite, remises.

Tout calcul se fait ici. Le navigateur n'envoie qu'un code ; il ne choisit
ni son parrain apres coup, ni un pourcentage, ni un montant.

---------------------------------------------------------------------------
Integrite
---------------------------------------------------------------------------

  - **Idempotence** : chaque remise porte la reference de l'evenement qui la
    cree (`premier_paiement:<parrainage>`), unique en base.
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
# Sans chiffres ni lettres ambigus (0/O, 1/I/L) : un code se recopie.
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
LONGUEUR_CODE = 10
DEVISES_SANS_DECIMALES = {"XAF", "XOF", "CDF"}


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
    """Conserve la date de publication ; elle ne débloque aucun avantage."""
    Parrainage.objects.filter(filleul=tenant, publie_le__isnull=True).update(
        publie_le=quand or timezone.now()
    )


# ---------------------------------------------------------------------------
# Admissibilite et remises
# ---------------------------------------------------------------------------


def rendre_admissible(parrainage_id, maintenant=None, via: str = "delai"):
    # La publication et les corrections administratives ne remplacent plus un paiement.
    raise ValueError("Seul le premier paiement d’abonnement confirmé valide le parrainage.")


def evaluer(maintenant=None) -> dict:
    from .cycles import evaluer as traiter

    return traiter(maintenant)


def recompenser_paiement(demande, maintenant=None) -> None:
    if actif():
        from .cycles import paiement_confirme

        paiement_confirme(demande, maintenant)


@transaction.atomic
def expirer(maintenant=None) -> int:
    from .cycles import journal

    maintenant = maintenant or timezone.now()
    n = 0
    for r in Remise.objects.select_for_update().filter(
        statut="disponible", expire_le__lte=maintenant
    ):
        r.statut = "expiree"
        r.save(update_fields=["statut", "maj_le"])
        journal(r, "expiration")
        n += 1
    return n


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
    """Une seule remise du salon, la plus proche de son expiration."""
    maintenant = maintenant or timezone.now()
    if not actif():
        return []
    requete = Remise.objects.filter(
        beneficiaire_tenant_id=tenant_id,
        statut=Remise.Statut.DISPONIBLE,
        expire_le__gt=maintenant,
    ).order_by("expire_le", "cree_le")
    if verrouiller:
        requete = requete.select_for_update()
    # Les droits historiques sont conservés, mais jamais additionnés automatiquement.
    return list(requete[:1])


def calculer(montant_catalogue: Decimal, devise: str, remises) -> Calcul:
    """Le montant a payer, remises deduites. Chaque remise porte sa part, arrondie."""
    remises = list(remises)[:1]
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


@transaction.atomic
def reserver(demande, calcul: Calcul) -> None:
    """Les remises du calcul sont liees a la demande. Dans sa transaction."""
    from .cycles import journal, politique

    if len(calcul.remises) > 1:
        raise ValueError("Une seule remise par échéance.")
    for remise in calcul.remises:
        r = Remise.objects.select_for_update().get(pk=remise.pk)
        if r.statut != "disponible" or not r.expire_le or r.expire_le <= timezone.now():
            raise ValueError("Cette remise n’est plus disponible.")
        p = politique()
        heures = r.conditions.get("reservation_heures") or (p.reservation_heures if p else None)
        if not heures:
            raise ValueError("Le délai de réservation de la remise doit être configuré.")
        r.conditions = {
            **r.conditions,
            "reservation_fin": (timezone.now() + timedelta(hours=heures)).isoformat(),
        }
        r.statut, r.demande = "reservee", demande
        r.montant_deduit, r.devise = calcul.parts[r.id], demande.currency
        r.save(
            update_fields=["statut", "demande", "montant_deduit", "devise", "conditions", "maj_le"]
        )
        journal(r, "reservation", paiement=str(demande.pk), montant=str(r.montant_deduit))


def reservation_expiree(demande, maintenant=None):
    from django.utils.dateparse import parse_datetime

    maintenant = maintenant or timezone.now()
    for r in Remise.objects.filter(demande=demande, statut="reservee"):
        fin = parse_datetime(r.conditions.get("reservation_fin", ""))
        if fin and fin <= maintenant:
            return True
    return False


@transaction.atomic
def consommer(demande, maintenant=None) -> None:
    """La demande est approuvee : ses remises sont utilisees."""
    from .cycles import journal

    maintenant = maintenant or timezone.now()
    for r in Remise.objects.select_for_update().filter(demande=demande, statut="reservee"):
        r.statut, r.utilisee_le = "utilisee", maintenant
        r.save(update_fields=["statut", "utilisee_le", "maj_le"])
        journal(r, "utilisation", paiement=str(demande.pk), montant=str(r.montant_deduit))


@transaction.atomic
def liberer(demande, maintenant=None) -> None:
    """La demande est refusee : ses remises redeviennent disponibles (ou expirent)."""
    from .cycles import journal

    maintenant = maintenant or timezone.now()
    for remise in Remise.objects.select_for_update().filter(
        demande=demande, statut=Remise.Statut.RESERVEE
    ):
        invalide = (
            remise.parrainage_id
            and Parrainage.objects.filter(pk=remise.parrainage_id, statut="invalide").exists()
        )
        remise.statut = (
            "annulee"
            if invalide
            else ("disponible" if remise.expire_le and remise.expire_le > maintenant else "expiree")
        )
        remise.demande = None
        remise.montant_deduit = None
        remise.devise = ""
        remise.save(update_fields=["statut", "demande", "montant_deduit", "devise", "maj_le"])
        journal(remise, "liberation", paiement=str(demande.pk), statut=remise.statut)


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
        from .cycles import journal

        annulees = 0
        for r in Remise.objects.select_for_update().filter(
            parrainage=parrainage, statut__in=("disponible", "en_attente", "suspendue")
        ):
            r.statut, r.annulee_le, r.motif = "annulee", timezone.now(), motif[:255]
            r.save(update_fields=["statut", "annulee_le", "motif", "maj_le"])
            journal(r, "annulation", acteur=str(administrateur.pk), motif=motif)
            annulees += 1
        _journaliser(
            "REFERRAL_ADMIN",
            parrainage,
            administrateur,
            {"geste": "invalidation", "motif": motif, "remises_annulees": annulees},
        )
    return annulees


@transaction.atomic
def annuler_remise(remise: Remise, administrateur, motif: str) -> None:
    _exiger_motif(motif)
    remise = Remise.objects.select_for_update().get(pk=remise.pk)
    if remise.statut != Remise.Statut.DISPONIBLE:
        raise ValueError("Seule une remise disponible s'annule.")
    remise.statut = Remise.Statut.ANNULEE
    remise.annulee_le = timezone.now()
    remise.motif = motif[:255]
    remise.save(update_fields=["statut", "annulee_le", "motif", "maj_le"])
    from .cycles import journal

    journal(remise, "annulation", acteur=str(administrateur.pk), motif=motif)
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
