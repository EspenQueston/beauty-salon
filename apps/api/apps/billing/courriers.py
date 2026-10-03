"""Les e-mails de l'abonnement : rappels, decisions, tarifs.

---------------------------------------------------------------------------
Ce qui part, a qui, et quand
---------------------------------------------------------------------------

Au proprietaire du salon — c'est lui qui paie, et la page Abonnement lui
est reservee :

  - **rappels**, par la tache horaire (`envoyer_rappels`) : fin d'essai a
    J-7, J-3 et la veille ; fin de periode payee a J-7, J-3 et la veille
    (plus J-30 pour l'annuel) ; debut du delai de grace ; fermeture ;
  - **decisions**, a la validation de la transaction qui les prend :
    paiement recu, valide, refuse ; prolongation, suspension, reactivation ;
  - **tarifs** : un prix modifie par l'administration est annonce aux salons
    qui reglent dans cette devise.

A l'equipe de la plateforme : chaque paiement declare, a verifier.

---------------------------------------------------------------------------
Un seul gabarit
---------------------------------------------------------------------------

Tous ces messages ont la meme forme — un titre, une phrase, un montant,
quelques faits, un avertissement, un bouton. Un gabarit par message, ce
serait quinze fichiers qui divergent au premier ajustement ; ils passent
donc tous par `emails/abonnement.html`, et ce module ne produit que le
contenu. Les e-mails au salon restent en francais, comme son tableau de bord.

Rien ici ne promet un acces que seul un administrateur peut ouvrir : un
paiement declare est « en verification », jamais « recu et valide ».
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from apps.notifications.details import grouper
from apps.notifications.email import send_email

logger = logging.getLogger(__name__)

MOIS = (
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
)

GABARIT = "abonnement"


@dataclass
class Courrier:
    """Le contenu d'un e-mail d'abonnement, sans sa mise en forme."""

    sujet: str
    titre: str
    accroche: str
    preheader: str = ""
    montant: dict | None = None
    faits: list[dict] = field(default_factory=list)
    avis: dict | None = None
    paragraphes: list[str] = field(default_factory=list)
    bouton: tuple[str, str] | None = None
    pied: str = "Vous recevez ce message parce que vous êtes propriétaire de ce salon."

    def contexte(self, salon=None) -> dict:
        return {
            "salon": salon,
            "titre": self.titre,
            "accroche": self.accroche,
            "preheader": self.preheader or self.accroche,
            "montant": self.montant,
            "details": grouper(self.faits),
            "faits": self.faits,
            "avis": self.avis,
            "paragraphes": self.paragraphes,
            "bouton_texte": self.bouton[0] if self.bouton else "",
            "bouton_url": self.bouton[1] if self.bouton else "",
            "pied": self.pied,
        }


# ---------------------------------------------------------------------------
# Outils
# ---------------------------------------------------------------------------


def argent(montant, devise: str) -> str:
    """« 99 CNY », « 15 000 XAF » : milliers espaces, pas de decimales vides."""
    if montant is None:
        return ""
    valeur = Decimal(montant)
    if valeur == valeur.to_integral():
        texte = f"{int(valeur):,}".replace(",", " ")
    else:
        texte = f"{valeur:,.2f}".replace(",", " ").replace(".", ",")
    return f"{texte} {devise}"


def date_longue(moment: datetime | None, fuseau: str = "UTC") -> str:
    """« 9 octobre 2026 », dans le fuseau du salon."""
    if moment is None:
        return ""
    local = moment.astimezone(ZoneInfo(fuseau or "UTC"))
    jour = "1er" if local.day == 1 else str(local.day)
    return f"{jour} {MOIS[local.month - 1]} {local.year}"


def url_abonnement() -> str:
    return f"{settings.APP_BASE_URL.rstrip('/')}/abonnement"


def url_admin(nom: str, *args) -> str:
    return f"{settings.API_BASE_URL.rstrip('/')}{reverse(nom, args=args)}"


def proprietaires(tenant_id) -> list[str]:
    """Les adresses des proprietaires actifs du salon.

    Les proprietaires seulement : la facturation leur est reservee dans le
    tableau de bord, elle l'est aussi dans la boite de reception.
    """
    from apps.accounts.models import Membership

    return [
        adresse
        for adresse in Membership.objects.filter(
            tenant_id=tenant_id,
            status=Membership.Status.ACTIVE,
            role=Membership.Role.OWNER,
            user__is_active=True,
        ).values_list("user__email", flat=True)
        if adresse
    ]


def verificateurs() -> list[str]:
    """Les administrateurs de la plateforme qui peuvent trancher un paiement."""
    from apps.accounts.models import User

    return [
        utilisateur.email
        for utilisateur in User.objects.filter(is_active=True, is_platform_admin=True)
        if utilisateur.email and utilisateur.has_perm("billing.review_subscriptionpaymentrequest")
    ]


def envoyer(courrier: Courrier, destinataires: list[str], salon=None) -> int:
    """Envoie un courrier ; renvoie le nombre de destinataires."""
    adresses = sorted({adresse for adresse in destinataires if adresse})
    if not adresses:
        return 0
    # Le nom d'un salon entre dans certains objets : un retour a la ligne
    # y serait refuse par Django (en-tete injecte) et le message perdu.
    sujet = " ".join(courrier.sujet.split())
    send_email(sujet, GABARIT, courrier.contexte(salon), adresses)
    return len(adresses)


def _fuseau(abonnement) -> str:
    return getattr(getattr(abonnement, "tenant", None), "timezone", "") or "UTC"


def _suite(fuseau: str, fin: datetime | None) -> str:
    """Ce qui se passe apres une fin de periode non reglee — sans menacer."""
    from .services import GRACE

    if fin is None:
        return ""
    return (
        f"Sans paiement, vous disposez de {GRACE.days} jours de grâce, jusqu'au "
        f"{date_longue(fin + GRACE, fuseau)}. Ensuite, les réservations en ligne "
        "s'arrêtent et le tableau de bord passe en lecture seule — vos données "
        "restent intactes, et tout se rouvre dès la validation du paiement."
    )


def _tarifs(devise: str) -> tuple[str, list[dict], dict | None]:
    """Les prix des deux offres dans la devise du salon (ou en CNY a defaut)."""
    from .models import Plan
    from .services import economie_annuelle, offres_payantes, tarif

    offres = {offre.code: offre for offre in offres_payantes()}
    for code_devise in (devise, "CNY"):
        prix = {code: tarif(offre, code_devise) for code, offre in offres.items()}
        if any(prix.values()):
            break
    else:
        return devise, [], None

    faits = []
    mensuel = prix.get(Plan.Code.MONTHLY)
    annuel = prix.get(Plan.Code.YEARLY)
    if mensuel:
        faits.append({"label": "Mensuel", "value": f"{argent(mensuel.amount, code_devise)} / mois"})
    economie = economie_annuelle(
        mensuel.amount if mensuel else None, annuel.amount if annuel else None
    )
    if annuel:
        valeur = f"{argent(annuel.amount, code_devise)} / an"
        if economie:
            valeur += f" (−{economie['pourcentage']} %)"
        faits.append({"label": "Annuel", "value": valeur, "strong": True})
    return code_devise, faits, economie


# ---------------------------------------------------------------------------
# Rappels
# ---------------------------------------------------------------------------


def quand(fin: datetime, fuseau: str, maintenant: datetime) -> str:
    """« aujourd'hui », « demain », « dans 3 jours » — en jours du calendrier local."""
    zone = ZoneInfo(fuseau or "UTC")
    ecart = (fin.astimezone(zone).date() - maintenant.astimezone(zone).date()).days
    if ecart <= 0:
        return "aujourd'hui"
    if ecart == 1:
        return "demain"
    return f"dans {ecart} jours"


def rappel(abonnement, genre: str, maintenant: datetime | None = None) -> Courrier:
    """Le rappel `genre` (voir SubscriptionReminder.Kind) pour cet abonnement."""
    maintenant = maintenant or timezone.now()
    fuseau = _fuseau(abonnement)
    fin = abonnement.current_period_end
    date_fin = date_longue(fin, fuseau)
    devise, faits_tarifs, economie = _tarifs(abonnement.currency)

    echeance = quand(fin, fuseau, maintenant)

    if genre.startswith("trial_"):
        return Courrier(
            sujet=f"Votre essai Beauty Salon se termine {echeance}",
            titre=f"Votre essai se termine {echeance}",
            accroche=(
                f"Votre période d'essai prend fin le {date_fin}. Choisissez votre "
                "offre pour que votre mini-site continue de prendre des rendez-vous "
                "sans interruption."
            ),
            faits=faits_tarifs,
            avis={
                "titre": "Payer maintenant ne vous fait perdre aucun jour.",
                "texte": "La période payée commence à la fin de votre essai.",
            },
            paragraphes=[_suite(fuseau, fin)],
            bouton=("Choisir mon offre", url_abonnement()),
        )

    if genre.startswith("renewal_"):
        paragraphes = [_suite(fuseau, fin)]
        mensuel = abonnement.plan.code == "monthly"
        if mensuel and economie:
            paragraphes.insert(
                0,
                f"Passez à l'offre annuelle et économisez "
                f"{argent(economie['montant'], devise)} par an "
                f"(−{economie['pourcentage']} %) : votre année commencera à la suite "
                "de la période en cours.",
            )
        return Courrier(
            sujet=f"Votre abonnement arrive à échéance {echeance}",
            titre=f"Votre abonnement se termine {echeance}",
            accroche=(
                f"Votre offre {abonnement.plan.name} couvre votre salon jusqu'au "
                f"{date_fin}. Réglez la période suivante dès maintenant : elle "
                "s'ajoutera à la suite, sans chevauchement."
            ),
            faits=faits_tarifs,
            paragraphes=paragraphes,
            bouton=(
                "Passer à l'annuel" if mensuel and economie else "Renouveler mon abonnement",
                url_abonnement(),
            ),
        )

    if genre == "grace":
        from .services import GRACE

        limite = date_longue(fin + GRACE, fuseau)
        return Courrier(
            sujet=f"Votre abonnement est arrivé à échéance — réglez avant le {limite}",
            titre="Votre période est terminée",
            accroche=(
                f"Votre abonnement a pris fin le {date_fin}. Votre salon reste "
                f"ouvert encore quelques jours : réglez avant le {limite} pour que "
                "vos clientes puissent continuer à réserver."
            ),
            faits=faits_tarifs,
            avis={
                "titre": f"Après le {limite}",
                "texte": (
                    "Les réservations en ligne s'arrêtent et le tableau de bord "
                    "passe en lecture seule. Vos données restent intactes."
                ),
            },
            bouton=("Régler mon abonnement", url_abonnement()),
        )

    if genre == "closed":
        en_attente = abonnement.payment_requests.filter(status="pending").exists()
        if en_attente:
            return Courrier(
                sujet="Réservations en ligne en pause — paiement en vérification",
                titre="Votre paiement est en cours de vérification",
                accroche=(
                    "Le délai de grâce est écoulé : les réservations en ligne sont en "
                    "pause le temps que notre équipe valide votre paiement. Tout se "
                    "rouvre dès sa validation, sans rien à refaire de votre côté."
                ),
                bouton=("Suivre mon paiement", url_abonnement()),
            )
        return Courrier(
            sujet="Réservations en ligne en pause sur votre mini-site",
            titre="Votre abonnement a expiré",
            accroche=(
                "Vos clientes ne peuvent plus réserver en ligne et votre tableau de "
                "bord est en lecture seule. Votre mini-site reste visible, et vos "
                "données sont intactes : tout se rouvre dès la validation de votre "
                "paiement."
            ),
            faits=faits_tarifs,
            bouton=("Réactiver mon salon", url_abonnement()),
        )

    raise ValueError(f"Rappel inconnu : {genre}")


# ---------------------------------------------------------------------------
# Paiements et decisions
# ---------------------------------------------------------------------------


def _faits_demande(demande, fuseau: str) -> list[dict]:
    faits = [
        {"label": "Offre", "value": f"{demande.plan.name} · {demande.billing_months} mois"},
        {"label": "Moyen", "value": demande.method_label},
        {"label": "Référence", "value": demande.reference, "strong": True},
        {"label": "Déclaré le", "value": date_longue(demande.created_at, fuseau)},
    ]
    return faits


def paiement_recu(demande) -> Courrier:
    fuseau = _fuseau(demande.subscription)
    return Courrier(
        sujet="Paiement reçu — en cours de vérification",
        titre="Nous vérifions votre paiement",
        accroche=(
            "Merci ! Votre déclaration est enregistrée. Notre équipe retrouve le "
            "versement sur le compte crédité, puis ouvre votre période."
        ),
        montant={
            "label": "Montant déclaré",
            "texte": argent(demande.amount, demande.currency),
        },
        faits=_faits_demande(demande, fuseau),
        avis={
            "titre": "Votre accès n'est pas encore prolongé.",
            "texte": "Il le sera à la validation : vous recevrez alors un e-mail.",
        },
        bouton=("Suivre mon paiement", url_abonnement()),
    )


def paiement_a_verifier(demande) -> Courrier:
    salon = getattr(demande.tenant, "name", "") or "Un salon"
    faits = [
        {"label": "Salon", "value": salon, "strong": True},
        *_faits_demande(demande, "UTC"),
    ]
    if demande.method_account_number:
        faits.append({"label": "Compte crédité", "value": demande.method_account_number})
    return Courrier(
        sujet=f"Paiement d'abonnement à vérifier — {salon}",
        titre="Un paiement attend votre vérification",
        accroche=(
            "Retrouvez ce versement sur le compte crédité avant de l'approuver : "
            "une capture d'écran se fabrique, la référence et le relevé font foi."
        ),
        montant={"label": "Montant", "texte": argent(demande.amount, demande.currency)},
        faits=faits,
        bouton=(
            "Vérifier le paiement",
            url_admin("admin:billing_subscriptionpaymentrequest_change", demande.id),
        ),
        pied="Vous recevez ce message parce que vous vérifiez les paiements de la plateforme.",
    )


def paiement_valide(demande) -> Courrier:
    fuseau = _fuseau(demande.subscription)
    faits = [
        {"label": "Offre", "value": demande.plan.name},
        {"label": "Moyen", "value": demande.method_label},
        {"label": "Du", "value": date_longue(demande.period_start, fuseau)},
        {"label": "Au", "value": date_longue(demande.period_end, fuseau), "strong": True},
    ]
    if demande.invoice_id:
        faits.append({"label": "Facture", "value": demande.invoice.number})
    return Courrier(
        sujet=f"Paiement validé — abonnement actif jusqu'au "
        f"{date_longue(demande.period_end, fuseau)}",
        titre="Votre paiement est validé",
        accroche=(
            "Merci pour votre confiance. Votre salon est couvert jusqu'au "
            f"{date_longue(demande.period_end, fuseau)} : réservations en ligne et "
            "tableau de bord sont pleinement ouverts."
        ),
        montant={"label": "Montant réglé", "texte": argent(demande.amount, demande.currency)},
        faits=faits,
        bouton=("Voir mon abonnement", url_abonnement()),
    )


def paiement_refuse(demande) -> Courrier:
    fuseau = _fuseau(demande.subscription)
    return Courrier(
        sujet="Votre paiement n'a pas pu être validé",
        titre="Paiement non validé",
        accroche=(
            "Notre équipe n'a pas pu rapprocher votre déclaration d'un versement "
            "reçu. Vérifiez la référence, puis déclarez votre paiement à nouveau."
        ),
        montant={"label": "Montant déclaré", "texte": argent(demande.amount, demande.currency)},
        faits=_faits_demande(demande, fuseau),
        avis={"titre": "Motif", "texte": demande.rejection_reason},
        paragraphes=[
            "Si vous pensez qu'il s'agit d'une erreur, contactez l'équipe Beauty "
            "Salon en indiquant la référence ci-dessus."
        ],
        bouton=("Déclarer à nouveau", url_abonnement()),
    )


def geste(abonnement, genre: str) -> Courrier:
    """Prolongation, suspension ou reactivation decidee par l'administration."""
    fuseau = _fuseau(abonnement)
    fin = date_longue(abonnement.current_period_end, fuseau)
    if genre == "prolongation":
        return Courrier(
            sujet=f"Votre abonnement est prolongé jusqu'au {fin}",
            titre="Votre abonnement est prolongé",
            accroche=(
                f"L'équipe Beauty Salon a prolongé votre abonnement : votre salon est "
                f"couvert jusqu'au {fin}."
            ),
            bouton=("Voir mon abonnement", url_abonnement()),
        )
    if genre == "suspension":
        return Courrier(
            sujet="Votre abonnement Beauty Salon est suspendu",
            titre="Votre abonnement est suspendu",
            accroche=(
                "Les réservations en ligne sont en pause et le tableau de bord est en "
                "lecture seule. Vos données sont intactes. Contactez l'équipe Beauty "
                "Salon pour rouvrir votre salon."
            ),
            bouton=("Voir mon abonnement", url_abonnement()),
        )
    if genre == "reactivation":
        return Courrier(
            sujet="Votre abonnement Beauty Salon est réactivé",
            titre="Votre salon est de nouveau ouvert",
            accroche=(
                "La suspension est levée. "
                + (
                    f"Votre salon est couvert jusqu'au {fin}."
                    if abonnement.current_period_end > timezone.now()
                    else "Réglez votre abonnement pour rouvrir les réservations."
                )
            ),
            bouton=("Voir mon abonnement", url_abonnement()),
        )
    raise ValueError(f"Geste inconnu : {genre}")


def tarif_modifie(prix, ancien: Decimal, applicable: datetime) -> Courrier:
    nouveau = prix.amount
    hausse = nouveau > ancien
    return Courrier(
        sujet=f"Évolution du tarif {prix.plan.name} ({prix.currency})",
        titre=f"Le tarif {prix.plan.name} évolue",
        accroche=(
            f"À partir du {date_longue(applicable)}, l'offre {prix.plan.name} "
            f"passe de {argent(ancien, prix.currency)} à "
            f"{argent(nouveau, prix.currency)}."
        ),
        montant={
            "label": "Nouveau tarif",
            "texte": argent(nouveau, prix.currency),
            "aide": f"au lieu de {argent(ancien, prix.currency)}",
        },
        faits=[
            {"label": "Offre", "value": prix.plan.name},
            {"label": "Devise", "value": prix.currency},
        ],
        avis={
            "titre": "Votre période en cours ne change pas.",
            "texte": "Les paiements déjà déclarés restent au tarif d'origine.",
        },
        paragraphes=(
            [
                "L'offre annuelle vous permet de fixer votre budget pour douze mois "
                "d'un seul règlement."
            ]
            if hausse
            else ["Bonne nouvelle : la baisse s'applique à votre prochain paiement."]
        ),
        bouton=("Voir les offres", url_abonnement()),
    )
