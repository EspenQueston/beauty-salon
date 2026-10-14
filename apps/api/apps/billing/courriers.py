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
contenu.

---------------------------------------------------------------------------
Deux langues
---------------------------------------------------------------------------

Chaque proprietaire lit dans la langue retenue sur son compte : chaque
fabrique prend une `langue`, et `envoyer_par_langue` en ecrit une version
par langue presente parmi les destinataires. Les phrases sont ecrites par
paires, `d(francais, anglais)`, a l'endroit ou elles servent : le sens d'un
rappel depend de ses chiffres, et les separer de leur phrase rendrait la
relecture impossible. Les dates, montants et pourcentages suivent les
usages de chaque langue (« 9 octobre 2026 » / « 9 October 2026 »,
« 15 000 XAF » / « 15,000 XAF »). Les messages a l'equipe de la plateforme
restent en francais.

Rien ici ne promet un acces que seul un administrateur peut ouvrir : un
paiement declare est « en verification », jamais « recu et valide ».
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from apps.notifications.details import grouper
from apps.notifications.email import send_email
from apps.notifications.textes import textes
from apps.translations.langue import adresse_app, normaliser, par_langue

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
MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)

#: Le nom des offres en anglais, par code — les memes que l'espace pro. En
#: francais, le nom saisi dans l'administration fait foi.
OFFRES_EN = {
    "trial": "Trial",
    "pro": "Pro (legacy)",
    "monthly": "Standard monthly",
    "yearly": "Standard yearly",
    "pro_monthly": "Pro monthly",
    "pro_yearly": "Pro yearly",
}

GABARIT = "abonnement"


def _choix(langue: str) -> Callable[[str, str], str]:
    """`d(francais, anglais)` : la phrase de la langue voulue."""
    anglais = normaliser(langue) == "en"
    return lambda francais, english: english if anglais else francais


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
    pied: str = ""
    langue: str = "fr"

    def __post_init__(self):
        if not self.pied:
            self.pied = _choix(self.langue)(
                "Vous recevez ce message parce que vous êtes propriétaire de ce salon.",
                "You are receiving this message because you own this salon.",
            )

    def contexte(self, salon=None) -> dict:
        return {
            "t": textes(self.langue),
            "langue": self.langue,
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


def argent(montant, devise: str, langue: str = "fr") -> str:
    """« 99 CNY », « 15 000 XAF » (« 15,000 XAF » en anglais) : pas de
    decimales vides. En francais, les milliers sont separes par une espace
    fine insecable : le montant ne se coupe jamais en fin de ligne."""
    if montant is None:
        return ""
    valeur = Decimal(montant)
    anglais = normaliser(langue) == "en"
    if valeur == valeur.to_integral():
        texte = f"{int(valeur):,}"
        if not anglais:
            texte = texte.replace(",", " ")
    else:
        texte = f"{valeur:,.2f}"
        if not anglais:
            texte = texte.replace(",", " ").replace(".", ",")
    return f"{texte} {devise}"


def pourcent(valeur, langue: str = "fr") -> str:
    """« 17 % » en francais (espace insecable), « 17% » en anglais."""
    return f"{valeur}%" if normaliser(langue) == "en" else f"{valeur} %"


def date_longue(moment: datetime | None, fuseau: str = "UTC", langue: str = "fr") -> str:
    """« 9 octobre 2026 » / « 9 October 2026 », dans le fuseau du salon."""
    if moment is None:
        return ""
    local = moment.astimezone(ZoneInfo(fuseau or "UTC"))
    if normaliser(langue) == "en":
        return f"{local.day} {MONTHS[local.month - 1]} {local.year}"
    jour = "1er" if local.day == 1 else str(local.day)
    return f"{jour} {MOIS[local.month - 1]} {local.year}"


def nom_offre(plan, langue: str = "fr") -> str:
    """Le nom d'une offre dans la langue du destinataire."""
    if normaliser(langue) == "en":
        return OFFRES_EN.get(getattr(plan, "code", ""), plan.name)
    return plan.name


def url_abonnement(langue: str = "fr") -> str:
    return adresse_app("/abonnement", langue)


def url_admin(nom: str, *args) -> str:
    return f"{settings.API_BASE_URL.rstrip('/')}{reverse(nom, args=args)}"


def _proprietaires_qs(tenant_id):
    from apps.accounts.models import Membership

    return Membership.objects.filter(
        tenant_id=tenant_id,
        status=Membership.Status.ACTIVE,
        role=Membership.Role.OWNER,
        user__is_active=True,
    )


def proprietaires(tenant_id) -> list[str]:
    """Les adresses des proprietaires actifs du salon.

    Les proprietaires seulement : la facturation leur est reservee dans le
    tableau de bord, elle l'est aussi dans la boite de reception.
    """
    return [
        adresse
        for adresse in _proprietaires_qs(tenant_id).values_list("user__email", flat=True)
        if adresse
    ]


def proprietaires_par_langue(tenant_id) -> dict[str, list[str]]:
    """Les memes adresses, regroupees par la langue retenue sur chaque compte."""
    return par_langue(
        _proprietaires_qs(tenant_id).values_list("user__email", "user__locale")
    )


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


def envoyer_par_langue(
    composer: Callable[[str], Courrier], groupes: dict[str, list[str]], salon=None
) -> int:
    """Ecrit le courrier une fois par langue, a ceux qui la lisent.

    `composer` recoit la langue et rend le courrier ; `groupes` vient de
    `proprietaires_par_langue`. Renvoie le nombre total de destinataires.
    """
    return sum(
        envoyer(composer(langue), adresses, salon) for langue, adresses in groupes.items()
    )


def _fuseau(abonnement) -> str:
    return getattr(getattr(abonnement, "tenant", None), "timezone", "") or "UTC"


def _suite(fuseau: str, fin: datetime | None, langue: str = "fr") -> str:
    """Ce qui se passe apres une fin de periode non reglee — sans menacer."""
    from .services import GRACE

    if fin is None:
        return ""
    limite = date_longue(fin + GRACE, fuseau, langue)
    return _choix(langue)(
        f"Sans paiement, vous disposez de {GRACE.days} jours de grâce, jusqu'au "
        f"{limite}. Ensuite, les réservations en ligne s'arrêtent et le tableau de "
        "bord passe en lecture seule — vos données restent intactes, et tout se "
        "rouvre dès la validation du paiement.",
        f"Without payment, you have a {GRACE.days}-day grace period, until {limite}. "
        "After that, online bookings stop and the dashboard becomes read-only — "
        "your data stays intact, and everything reopens as soon as the payment is "
        "validated.",
    )


def _tarifs(devise: str, langue: str = "fr") -> tuple[str, list[dict], dict | None]:
    """Les prix des deux offres dans la devise du salon (ou en CNY a defaut)."""
    from .models import Plan
    from .services import economie_annuelle, offres_payantes, tarif

    d = _choix(langue)
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
        faits.append({
            "label": d("Mensuel", "Monthly"),
            "value": f"{argent(mensuel.amount, code_devise, langue)} {d('/ mois', '/ month')}",
        })
    economie = economie_annuelle(
        mensuel.amount if mensuel else None, annuel.amount if annuel else None
    )
    if annuel:
        valeur = f"{argent(annuel.amount, code_devise, langue)} {d('/ an', '/ year')}"
        if economie:
            valeur += f" (−{pourcent(economie['pourcentage'], langue)})"
        faits.append({"label": d("Annuel", "Annual"), "value": valeur, "strong": True})
    return code_devise, faits, economie


# ---------------------------------------------------------------------------
# Rappels
# ---------------------------------------------------------------------------


def quand(fin: datetime, fuseau: str, maintenant: datetime, langue: str = "fr") -> str:
    """« aujourd'hui », « demain », « dans 3 jours » — en jours du calendrier local."""
    d = _choix(langue)
    zone = ZoneInfo(fuseau or "UTC")
    ecart = (fin.astimezone(zone).date() - maintenant.astimezone(zone).date()).days
    if ecart <= 0:
        return d("aujourd'hui", "today")
    if ecart == 1:
        return d("demain", "tomorrow")
    return d(f"dans {ecart} jours", f"in {ecart} days")


def rappel(
    abonnement, genre: str, maintenant: datetime | None = None, langue: str = "fr"
) -> Courrier:
    """Le rappel `genre` (voir SubscriptionReminder.Kind) pour cet abonnement."""
    d = _choix(langue)
    maintenant = maintenant or timezone.now()
    fuseau = _fuseau(abonnement)
    fin = abonnement.current_period_end
    date_fin = date_longue(fin, fuseau, langue)
    devise, faits_tarifs, economie = _tarifs(abonnement.currency, langue)
    lien = url_abonnement(langue)

    echeance = quand(fin, fuseau, maintenant, langue)

    if genre.startswith("trial_"):
        return Courrier(
            langue=langue,
            sujet=d(
                f"Votre essai Beauty Salon se termine {echeance}",
                f"Your Beauty Salon trial ends {echeance}",
            ),
            titre=d(f"Votre essai se termine {echeance}", f"Your trial ends {echeance}"),
            accroche=d(
                f"Votre période d'essai prend fin le {date_fin}. Choisissez votre "
                "offre pour que votre mini-site continue de prendre des rendez-vous "
                "sans interruption.",
                f"Your trial period ends on {date_fin}. Choose your plan so that your "
                "mini-site keeps taking bookings without interruption.",
            ),
            faits=faits_tarifs,
            avis={
                "titre": d(
                    "Payer maintenant ne vous fait perdre aucun jour.",
                    "Paying now does not cost you a single day.",
                ),
                "texte": d(
                    "La période payée commence à la fin de votre essai.",
                    "The paid period starts when your trial ends.",
                ),
            },
            paragraphes=[_suite(fuseau, fin, langue)],
            bouton=(d("Choisir mon offre", "Choose my plan"), lien),
        )

    if genre.startswith("renewal_"):
        paragraphes = [_suite(fuseau, fin, langue)]
        mensuel = abonnement.plan.code == "monthly"
        if mensuel and economie:
            gain = argent(economie["montant"], devise, langue)
            taux = pourcent(economie["pourcentage"], langue)
            paragraphes.insert(
                0,
                d(
                    f"Passez à l'offre annuelle et économisez {gain} par an (−{taux}) : "
                    "votre année commencera à la suite de la période en cours.",
                    f"Switch to the annual plan and save {gain} a year (−{taux}): your "
                    "year will start right after the current period.",
                ),
            )
        offre = nom_offre(abonnement.plan, langue)
        return Courrier(
            langue=langue,
            sujet=d(
                f"Votre abonnement arrive à échéance {echeance}",
                f"Your subscription expires {echeance}",
            ),
            titre=d(
                f"Votre abonnement se termine {echeance}",
                f"Your subscription ends {echeance}",
            ),
            accroche=d(
                f"Votre offre {offre} couvre votre salon jusqu'au {date_fin}. Réglez la "
                "période suivante dès maintenant : elle s'ajoutera à la suite, sans "
                "chevauchement.",
                f"Your {offre} plan covers your salon until {date_fin}. Pay for the next "
                "period now: it will be added right after, with no overlap.",
            ),
            faits=faits_tarifs,
            paragraphes=paragraphes,
            bouton=(
                d("Passer à l'annuel", "Switch to annual")
                if mensuel and economie
                else d("Renouveler mon abonnement", "Renew my subscription"),
                lien,
            ),
        )

    if genre == "grace":
        from .services import GRACE

        limite = date_longue(fin + GRACE, fuseau, langue)
        return Courrier(
            langue=langue,
            sujet=d(
                f"Votre abonnement est arrivé à échéance — réglez avant le {limite}",
                f"Your subscription has expired — pay before {limite}",
            ),
            titre=d("Votre période est terminée", "Your period has ended"),
            accroche=d(
                f"Votre abonnement a pris fin le {date_fin}. Votre salon reste "
                f"ouvert encore quelques jours : réglez avant le {limite} pour que "
                "vos clientes puissent continuer à réserver.",
                f"Your subscription ended on {date_fin}. Your salon stays open for a "
                f"few more days: pay before {limite} so that your clients can keep "
                "booking.",
            ),
            faits=faits_tarifs,
            avis={
                "titre": d(f"Après le {limite}", f"After {limite}"),
                "texte": d(
                    "Les réservations en ligne s'arrêtent et le tableau de bord "
                    "passe en lecture seule. Vos données restent intactes.",
                    "Online bookings stop and the dashboard becomes read-only. Your "
                    "data stays intact.",
                ),
            },
            bouton=(d("Régler mon abonnement", "Pay my subscription"), lien),
        )

    if genre == "closed":
        en_attente = abonnement.payment_requests.filter(status="pending").exists()
        if en_attente:
            return Courrier(
                langue=langue,
                sujet=d(
                    "Réservations en ligne en pause — paiement en vérification",
                    "Online bookings paused — payment being checked",
                ),
                titre=d(
                    "Votre paiement est en cours de vérification",
                    "Your payment is being checked",
                ),
                accroche=d(
                    "Le délai de grâce est écoulé : les réservations en ligne sont en "
                    "pause le temps que notre équipe valide votre paiement. Tout se "
                    "rouvre dès sa validation, sans rien à refaire de votre côté.",
                    "The grace period is over: online bookings are paused while our "
                    "team validates your payment. Everything reopens as soon as it is "
                    "validated, with nothing to redo on your side.",
                ),
                bouton=(d("Suivre mon paiement", "Track my payment"), lien),
            )
        return Courrier(
            langue=langue,
            sujet=d(
                "Réservations en ligne en pause sur votre mini-site",
                "Online bookings paused on your mini-site",
            ),
            titre=d("Votre abonnement a expiré", "Your subscription has expired"),
            accroche=d(
                "Vos clientes ne peuvent plus réserver en ligne et votre tableau de "
                "bord est en lecture seule. Votre mini-site reste visible, et vos "
                "données sont intactes : tout se rouvre dès la validation de votre "
                "paiement.",
                "Your clients can no longer book online and your dashboard is "
                "read-only. Your mini-site stays visible and your data is intact: "
                "everything reopens as soon as your payment is validated.",
            ),
            faits=faits_tarifs,
            bouton=(d("Réactiver mon salon", "Reactivate my salon"), lien),
        )

    raise ValueError(f"Rappel inconnu : {genre}")


# ---------------------------------------------------------------------------
# Paiements et decisions
# ---------------------------------------------------------------------------


def _faits_demande(demande, fuseau: str, langue: str = "fr") -> list[dict]:
    d = _choix(langue)
    mois = demande.billing_months
    return [
        {
            "label": d("Offre", "Plan"),
            "value": f"{nom_offre(demande.plan, langue)} · "
            + d(f"{mois} mois", f"{mois} month{'s' if mois != 1 else ''}"),
        },
        {"label": d("Moyen", "Method"), "value": demande.method_label},
        {"label": d("Référence", "Reference"), "value": demande.reference, "strong": True},
        {
            "label": d("Déclaré le", "Declared on"),
            "value": date_longue(demande.created_at, fuseau, langue),
        },
    ]


def paiement_recu(demande, langue: str = "fr") -> Courrier:
    d = _choix(langue)
    fuseau = _fuseau(demande.subscription)
    return Courrier(
        langue=langue,
        sujet=d(
            "Paiement reçu — en cours de vérification",
            "Payment received — being checked",
        ),
        titre=d("Nous vérifions votre paiement", "We are checking your payment"),
        accroche=d(
            "Merci ! Votre déclaration est enregistrée. Notre équipe retrouve le "
            "versement sur le compte crédité, puis ouvre votre période.",
            "Thank you! Your declaration is recorded. Our team finds the payment on "
            "the credited account, then opens your period.",
        ),
        montant={
            "label": d("Montant déclaré", "Declared amount"),
            "texte": argent(demande.amount, demande.currency, langue),
        },
        faits=_faits_demande(demande, fuseau, langue),
        avis={
            "titre": d(
                "Votre accès n'est pas encore prolongé.",
                "Your access is not extended yet.",
            ),
            "texte": d(
                "Il le sera à la validation : vous recevrez alors un e-mail.",
                "It will be upon validation: you will then receive an email.",
            ),
        },
        bouton=(d("Suivre mon paiement", "Track my payment"), url_abonnement(langue)),
    )


def paiement_a_verifier(demande) -> Courrier:
    """Pour l'equipe de la plateforme : en francais."""
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


def paiement_valide(demande, langue: str = "fr") -> Courrier:
    d = _choix(langue)
    fuseau = _fuseau(demande.subscription)
    fin = date_longue(demande.period_end, fuseau, langue)
    faits = [
        {"label": d("Offre", "Plan"), "value": nom_offre(demande.plan, langue)},
        {"label": d("Moyen", "Method"), "value": demande.method_label},
        {"label": d("Du", "From"), "value": date_longue(demande.period_start, fuseau, langue)},
        {"label": d("Au", "To"), "value": fin, "strong": True},
    ]
    if demande.invoice_id:
        faits.append({"label": d("Facture", "Invoice"), "value": demande.invoice.number})
    return Courrier(
        langue=langue,
        sujet=d(
            f"Paiement validé — abonnement actif jusqu'au {fin}",
            f"Payment validated — subscription active until {fin}",
        ),
        titre=d("Votre paiement est validé", "Your payment is validated"),
        accroche=d(
            f"Merci pour votre confiance. Votre salon est couvert jusqu'au {fin} : "
            "réservations en ligne et tableau de bord sont pleinement ouverts.",
            f"Thank you for your trust. Your salon is covered until {fin}: online "
            "bookings and the dashboard are fully open.",
        ),
        montant={
            "label": d("Montant réglé", "Amount paid"),
            "texte": argent(demande.amount, demande.currency, langue),
        },
        faits=faits,
        bouton=(d("Voir mon abonnement", "View my subscription"), url_abonnement(langue)),
    )


def paiement_refuse(demande, langue: str = "fr") -> Courrier:
    d = _choix(langue)
    fuseau = _fuseau(demande.subscription)
    return Courrier(
        langue=langue,
        sujet=d(
            "Votre paiement n'a pas pu être validé",
            "Your payment could not be validated",
        ),
        titre=d("Paiement non validé", "Payment not validated"),
        accroche=d(
            "Notre équipe n'a pas pu rapprocher votre déclaration d'un versement "
            "reçu. Vérifiez la référence, puis déclarez votre paiement à nouveau.",
            "Our team could not match your declaration with a received payment. "
            "Check the reference, then declare your payment again.",
        ),
        montant={
            "label": d("Montant déclaré", "Declared amount"),
            "texte": argent(demande.amount, demande.currency, langue),
        },
        faits=_faits_demande(demande, fuseau, langue),
        # Le motif, tel que l'administrateur l'a ecrit : il n'est pas traduit.
        avis={"titre": d("Motif", "Reason"), "texte": demande.rejection_reason},
        paragraphes=[
            d(
                "Si vous pensez qu'il s'agit d'une erreur, contactez l'équipe Beauty "
                "Salon en indiquant la référence ci-dessus.",
                "If you think this is a mistake, contact the Beauty Salon team with "
                "the reference above.",
            )
        ],
        bouton=(d("Déclarer à nouveau", "Declare again"), url_abonnement(langue)),
    )


def geste(abonnement, genre: str, langue: str = "fr") -> Courrier:
    """Prolongation, suspension ou reactivation decidee par l'administration."""
    d = _choix(langue)
    fuseau = _fuseau(abonnement)
    fin = date_longue(abonnement.current_period_end, fuseau, langue)
    bouton = (d("Voir mon abonnement", "View my subscription"), url_abonnement(langue))
    if genre == "prolongation":
        return Courrier(
            langue=langue,
            sujet=d(
                f"Votre abonnement est prolongé jusqu'au {fin}",
                f"Your subscription is extended until {fin}",
            ),
            titre=d("Votre abonnement est prolongé", "Your subscription is extended"),
            accroche=d(
                "L'équipe Beauty Salon a prolongé votre abonnement : votre salon est "
                f"couvert jusqu'au {fin}.",
                "The Beauty Salon team extended your subscription: your salon is "
                f"covered until {fin}.",
            ),
            bouton=bouton,
        )
    if genre == "suspension":
        return Courrier(
            langue=langue,
            sujet=d(
                "Votre abonnement Beauty Salon est suspendu",
                "Your Beauty Salon subscription is suspended",
            ),
            titre=d("Votre abonnement est suspendu", "Your subscription is suspended"),
            accroche=d(
                "Les réservations en ligne sont en pause et le tableau de bord est en "
                "lecture seule. Vos données sont intactes. Contactez l'équipe Beauty "
                "Salon pour rouvrir votre salon.",
                "Online bookings are paused and the dashboard is read-only. Your data "
                "is intact. Contact the Beauty Salon team to reopen your salon.",
            ),
            bouton=bouton,
        )
    if genre == "reactivation":
        couvert = abonnement.current_period_end > timezone.now()
        return Courrier(
            langue=langue,
            sujet=d(
                "Votre abonnement Beauty Salon est réactivé",
                "Your Beauty Salon subscription is reactivated",
            ),
            titre=d("Votre salon est de nouveau ouvert", "Your salon is open again"),
            accroche=d(
                "La suspension est levée. "
                + (
                    f"Votre salon est couvert jusqu'au {fin}."
                    if couvert
                    else "Réglez votre abonnement pour rouvrir les réservations."
                ),
                "The suspension is lifted. "
                + (
                    f"Your salon is covered until {fin}."
                    if couvert
                    else "Pay your subscription to reopen bookings."
                ),
            ),
            bouton=bouton,
        )
    raise ValueError(f"Geste inconnu : {genre}")


def tarif_modifie(prix, ancien: Decimal, applicable: datetime, langue: str = "fr") -> Courrier:
    d = _choix(langue)
    nouveau = prix.amount
    hausse = nouveau > ancien
    offre = nom_offre(prix.plan, langue)
    avant = argent(ancien, prix.currency, langue)
    apres = argent(nouveau, prix.currency, langue)
    date = date_longue(applicable, langue=langue)
    return Courrier(
        langue=langue,
        sujet=d(
            f"Évolution du tarif {offre} ({prix.currency})",
            f"{offre} price change ({prix.currency})",
        ),
        titre=d(f"Le tarif {offre} évolue", f"The {offre} price is changing"),
        accroche=d(
            f"À partir du {date}, l'offre {offre} passe de {avant} à {apres}.",
            f"From {date}, the {offre} plan goes from {avant} to {apres}.",
        ),
        montant={
            "label": d("Nouveau tarif", "New price"),
            "texte": apres,
            "aide": d(f"au lieu de {avant}", f"instead of {avant}"),
        },
        faits=[
            {"label": d("Offre", "Plan"), "value": offre},
            {"label": d("Devise", "Currency"), "value": prix.currency},
        ],
        avis={
            "titre": d(
                "Votre période en cours ne change pas.",
                "Your current period does not change.",
            ),
            "texte": d(
                "Les paiements déjà déclarés restent au tarif d'origine.",
                "Payments already declared stay at the original price.",
            ),
        },
        paragraphes=(
            [
                d(
                    "L'offre annuelle vous permet de fixer votre budget pour douze mois "
                    "d'un seul règlement.",
                    "The annual plan lets you set your budget for twelve months in a "
                    "single payment.",
                )
            ]
            if hausse
            else [
                d(
                    "Bonne nouvelle : la baisse s'applique à votre prochain paiement.",
                    "Good news: the decrease applies to your next payment.",
                )
            ]
        ),
        bouton=(d("Voir les offres", "View the plans"), url_abonnement(langue)),
    )
