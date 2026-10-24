"""Les mots, au meme endroit.

---------------------------------------------------------------------------
Pourquoi ce fichier existe
---------------------------------------------------------------------------

Les six endroits qui declenchent une notification sont dissemines : une vue
publique, deux services de paiement, un service d'agenda. Si chacun redigeait
son titre, on aurait « Nouvelle reservation », « Nouveau RDV » et « Une
cliente a reserve » pour le meme evenement, et personne ne s'en apercevrait
avant de les voir cote a cote dans la cloche.

Ici, le declencheur passe l'objet metier et rien d'autre. Ce module decide de
la formulation, du lien et du genre — et c'est lui qu'on relit le jour ou
l'on veut changer un mot.

---------------------------------------------------------------------------
Ce qui tient dans un titre
---------------------------------------------------------------------------

Une notification systeme est lue sur un ecran verrouille, en diagonale, en
deux secondes. Le titre dit **ce qui est arrive**, le corps dit **a qui et
quand**. On y met le nom de la cliente : c'est ce qui fait la difference
entre une alerte qu'on ouvre et une alerte qu'on balaie.

Les montants ne figurent jamais dans le titre. Un ecran verrouille se lit
par-dessus l'epaule, et le chiffre d'affaires d'un salon ne regarde pas la
personne assise a cote dans le bus.

---------------------------------------------------------------------------
Deux langues
---------------------------------------------------------------------------

Chaque destinataire lit dans la langue retenue sur son compte. Les textes
sont donc des paires (francais, anglais) rangees dans `TEXTES`, et les
declencheurs passent a `prevenir_salon` une fonction de la langue plutot
qu'une phrase toute faite. Le nom de la cliente, celui de la prestation,
le commentaire d'un avis restent tels qu'ils ont ete saisis.

Les notifications de la plateforme restent en francais : elles ne
s'adressent qu'a l'equipe qui l'exploite.
"""

from __future__ import annotations

import logging

from .models import Genre
from .service import prevenir_plateforme, prevenir_salon

logger = logging.getLogger(__name__)

#: (francais, anglais) pour chaque phrase. Les champs entre accolades sont
#: remplis par `_texte`.
TEXTES: dict[str, tuple[str, str]] = {
    "reservation.titre": ("{cliente} a réservé", "{cliente} booked"),
    "rendez_vous.corps": ("{prestation} {quand}", "{prestation} {quand}"),
    "acompte.titre": ("Acompte à vérifier", "Deposit to check"),
    "acompte.corps": (
        "{cliente} a envoyé sa preuve de versement.",
        "{cliente} sent a proof of payment.",
    ),
    "expire.titre": ("Créneau libéré", "Time slot released"),
    "expire.corps": (
        "{cliente} n'a pas réglé son acompte à temps ({quand}).",
        "{cliente} did not pay the deposit in time ({quand}).",
    ),
    "annulation.titre": ("{cliente} a annulé", "{cliente} cancelled"),
    "avis.titre": ("Nouvel avis {etoiles}", "New review {etoiles}"),
    "attente.titre": ("{nom} attend une place", "{nom} is waiting for a spot"),
    "abonnement.actif": ("Abonnement actif jusqu'au {fin}", "Subscription active until {fin}"),
    "abonnement.verifie": (
        "{formule} · paiement de {montant} vérifié.",
        "{formule} · payment of {montant} verified.",
    ),
    "abonnement.refuse": ("Paiement d'abonnement refusé", "Subscription payment declined"),
    "abonnement.voir": ("Consultez la page Abonnement.", "See the Subscription page."),
    "une_cliente": ("Une cliente", "A client"),
}

_MOIS_EN = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _dire(cle: str, langue: str, **valeurs) -> str:
    francais, anglais = TEXTES[cle]
    return (anglais if langue == "en" else francais).format(**valeurs).strip()


def _texte(cle: str, **valeurs):
    """Une phrase a ecrire dans la langue de chaque destinataire.

    Une valeur peut elle-meme dependre de la langue (« Une cliente » /
    « A client », une date) : elle est alors passee en fonction.
    """

    def rediger(langue: str) -> str:
        return _dire(
            cle,
            langue,
            **{nom: v(langue) if callable(v) else v for nom, v in valeurs.items()},
        )

    return rediger


def _quand(booking):
    """« le 24/09 à 14:30 » / « on 24 Sep at 14:30 », dans le fuseau du
    salon.

    Le fuseau compte : un salon de Guangzhou qui lit « 06:30 » pour un
    rendez-vous de 14:30 cesse de faire confiance a l'ensemble.

    En anglais, le mois en lettres : « 03/04 » se lit 3 avril d'un cote de
    l'Atlantique et 4 mars de l'autre.
    """
    from apps.notifications.tasks import _tenant_timezone

    debut = getattr(booking, "starts_at", None)
    if debut is None:
        return lambda langue: ""
    local = debut.astimezone(_tenant_timezone(booking.tenant))

    def ecrire(langue: str) -> str:
        if langue == "en":
            return f"on {local.day} {_MOIS_EN[local.month - 1]} at {local:%H:%M}"
        return f"le {local:%d/%m} à {local:%H:%M}"

    return ecrire


def _cliente(booking):
    client = getattr(booking, "customer", None)
    nom = getattr(client, "full_name", "") or ""
    return lambda langue: nom or _dire("une_cliente", langue)


def _photo(objet) -> str:
    """La photo de la prestation concernee, pour l'image du push ; chaine
    vide sinon.

    Lue sur la relation et non figee sur la reservation : c'est la photo du
    catalogue d'aujourd'hui qu'on veut montrer, et une prestation supprimee
    depuis n'en a simplement plus.

    Rien ici ne doit empecher la notification de partir. Une tache qui
    tourne hors du contexte du salon ne voit pas la prestation — la
    politique RLS la masque, et Django leve `DoesNotExist` en suivant la
    relation. Le point de sauvegarde protege la transaction de l'appelant
    si c'est la base elle-meme qui refuse.
    """
    from django.db import transaction

    from .habillage import url_publique

    try:
        with transaction.atomic(using=objet._state.db or "default"):
            service = getattr(objet, "service", None)
            return url_publique(getattr(service, "image", None)) if service else ""
    except Exception:
        logger.warning("Photo de prestation illisible pour le push.", exc_info=True)
        return ""


def _lien(booking) -> str:
    """L'agenda, ouvert sur ce rendez-vous precis.

    Renvoyer vers `/agenda` tout court obligeait a retrouver soi-meme, dans
    une grille hebdomadaire, celui dont parlait la notification - et une
    notification qui ne mene pas a ce qu'elle annonce ne sert qu'a inquieter.

    `?rdv=` est lu par l'agenda, qui abandonne alors la periode affichee pour
    n'afficher que ce rendez-vous. Voir `BookingViewSet.get_queryset`.
    """
    return f"/agenda?rdv={booking.id}"


def nouvelle_reservation(booking) -> None:
    """Une cliente vient de demander un creneau."""
    _sans_casser(
        prevenir_salon,
        booking.tenant_id,
        genre=Genre.RESERVATION,
        titre=_texte("reservation.titre", cliente=_cliente(booking)),
        corps=_texte("rendez_vous.corps", prestation=booking.service_name, quand=_quand(booking)),
        lien=_lien(booking),
        image=_photo(booking),
    )


def acompte_a_verifier(booking) -> None:
    """Une preuve de versement attend d'etre regardee.

    C'est la notification la plus urgente du produit : de l'argent est parti,
    et quelqu'un attend une reponse.
    """
    _sans_casser(
        prevenir_salon,
        booking.tenant_id,
        genre=Genre.ACOMPTE_A_VERIFIER,
        titre=_texte("acompte.titre"),
        corps=_texte("acompte.corps", cliente=_cliente(booking)),
        lien=_lien(booking),
        image=_photo(booking),
    )


def acompte_expire(booking) -> None:
    """Le delai est passe : le creneau vient d'etre rendu."""
    _sans_casser(
        prevenir_salon,
        booking.tenant_id,
        genre=Genre.ACOMPTE_EXPIRE,
        titre=_texte("expire.titre"),
        corps=_texte("expire.corps", cliente=_cliente(booking), quand=_quand(booking)),
        lien=_lien(booking),
        image=_photo(booking),
    )


def rendez_vous_annule(booking, *, par_le_salon: bool) -> None:
    """Une annulation.

    On ne previent que si elle vient de la cliente. Annulee par le salon,
    l'annonce irait a la personne qui vient de cliquer sur « annuler » — et
    une notification qui repete ce qu'on vient de faire soi-meme est
    exactement ce qui fait couper les notifications.
    """
    if par_le_salon:
        return

    _sans_casser(
        prevenir_salon,
        booking.tenant_id,
        genre=Genre.ANNULATION,
        titre=_texte("annulation.titre", cliente=_cliente(booking)),
        corps=_texte("rendez_vous.corps", prestation=booking.service_name, quand=_quand(booking)),
        lien=_lien(booking),
        image=_photo(booking),
    )


def nouvel_avis(review) -> None:
    """Un avis vient d'etre depose."""
    note = getattr(review, "rating", None)
    etoiles = f"{note}/5" if note else ""
    _sans_casser(
        prevenir_salon,
        review.tenant_id,
        genre=Genre.AVIS,
        titre=_texte("avis.titre", etoiles=etoiles),
        corps=(getattr(review, "comment", "") or "")[:140],
        lien="/avis",
    )


def liste_attente(entree) -> None:
    """Quelqu'un s'est inscrit sur la liste d'attente.

    Le nom de la prestation se lit sur la relation, pas sur un champ plat :
    contrairement a une reservation, une inscription en liste d'attente ne
    fige pas le libelle — rien n'a encore ete commande.
    """
    prestation = getattr(getattr(entree, "service", None), "name", "") or ""
    _sans_casser(
        prevenir_salon,
        entree.tenant_id,
        genre=Genre.LISTE_ATTENTE,
        titre=_texte("attente.titre", nom=entree.full_name),
        corps=prestation,
        lien="/liste-attente",
        image=_photo(entree),
    )


# ---------------------------------------------------------------------------
# Plateforme
# ---------------------------------------------------------------------------


def salon_inscrit(tenant) -> None:
    """Un salon vient de rejoindre la plateforme.

    Le lien mene a sa fiche dans l'administration : c'est la qu'on le publie,
    et c'est donc la seule chose qu'on vient faire en ouvrant ce message.
    """
    from django.urls import reverse

    ville = getattr(tenant, "city", "") or ""
    _sans_casser(
        prevenir_plateforme,
        genre=Genre.SALON_INSCRIT,
        titre=f"Nouveau salon : {tenant.name}",
        corps=ville,
        lien=reverse("admin:tenants_tenant_change", args=[tenant.id]),
        tenant_id=tenant.id,
    )


def paiement_abonnement_a_verifier(demande) -> None:
    """Un salon declare avoir paye son abonnement : quelqu'un doit verifier.

    Le lien ouvre la demande dans l'administration, preuve et reference
    comprises : c'est la seule chose qu'on vient faire en ouvrant ce message.
    """
    from django.urls import reverse

    from apps.notifications.tasks import _money

    salon = getattr(demande.tenant, "name", "") or "Un salon"
    _sans_casser(
        prevenir_plateforme,
        genre=Genre.PAIEMENT_ABONNEMENT,
        titre=f"Paiement à vérifier — {salon}",
        corps=(
            f"{demande.plan.name} · {_money(demande.amount, demande.currency)} · "
            f"{demande.method_label} · réf. {demande.reference}"
        ),
        lien=reverse("admin:billing_subscriptionpaymentrequest_change", args=[demande.id]),
        tenant_id=demande.tenant_id,
    )


def abonnement_decide(demande) -> None:
    """Le salon apprend ce qu'il est advenu de son paiement.

    Approuve : jusqu'a quand il est couvert, dans son fuseau. Refuse : le
    motif, tel que l'administrateur l'a ecrit — c'est ce qui lui permet de
    corriger et de renvoyer.
    """
    from apps.billing.courriers import nom_offre
    from apps.notifications.tasks import _money, _tenant_timezone

    if demande.status == demande.Status.APPROVED and demande.period_end:
        fin = demande.period_end.astimezone(_tenant_timezone(demande.tenant))
        titre = _texte(
            "abonnement.actif",
            fin=lambda langue: (
                f"{fin.day} {_MOIS_EN[fin.month - 1]} {fin.year}"
                if langue == "en"
                else f"{fin:%d/%m/%Y}"
            ),
        )
        corps = _texte(
            "abonnement.verifie",
            formule=lambda langue: nom_offre(demande.plan, langue),
            montant=_money(demande.amount, demande.currency),
        )
    else:
        titre = _texte("abonnement.refuse")
        # Le motif, tel que l'administrateur l'a ecrit : il n'est pas traduit.
        motif = demande.rejection_reason
        corps = (lambda langue: motif) if motif else _texte("abonnement.voir")

    _sans_casser(
        prevenir_salon,
        demande.tenant_id,
        genre=Genre.ABONNEMENT,
        titre=titre,
        corps=lambda langue: corps(langue)[:280],
        lien="/abonnement",
    )


def incident_facturation(tenant, detail: str) -> None:
    """Une facture n'a pas pu etre honoree."""
    _sans_casser(
        prevenir_plateforme,
        genre=Genre.FACTURE,
        titre=f"Facturation — {tenant.name if tenant else 'plateforme'}",
        corps=detail[:280],
        tenant_id=getattr(tenant, "id", None),
    )


def _sans_casser(fonction, *args, **kwargs) -> None:
    """Appelle, et ne laisse jamais remonter.

    Chacune de ces fonctions est appelee depuis une transaction qui fait
    quelque chose d'important : enregistrer une reservation, encaisser un
    acompte. Une notification est un service rendu par-dessus ; elle ne doit
    en aucun cas faire echouer ce qui l'a declenchee.

    La trace part dans les journaux, ou elle sera vue. Pas dans le visage de
    la cliente, qui n'y peut rien.
    """
    try:
        fonction(*args, **kwargs)
    except Exception:
        logger.exception("Notification non déposée (%s).", getattr(fonction, "__name__", fonction))
