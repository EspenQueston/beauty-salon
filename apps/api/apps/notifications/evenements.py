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
"""

from __future__ import annotations

import logging

from .models import Genre
from .service import prevenir_plateforme, prevenir_salon

logger = logging.getLogger(__name__)


def _quand(booking) -> str:
    """« le 24/09 à 14:30 », dans le fuseau du salon.

    Le fuseau compte : un salon de Guangzhou qui lit « 06:30 » pour un
    rendez-vous de 14:30 cesse de faire confiance a l'ensemble.
    """
    from apps.notifications.tasks import _tenant_timezone

    debut = getattr(booking, "starts_at", None)
    if debut is None:
        return ""
    local = debut.astimezone(_tenant_timezone(booking.tenant))
    return f"le {local.strftime('%d/%m')} à {local.strftime('%H:%M')}"


def _cliente(booking) -> str:
    client = getattr(booking, "customer", None)
    return getattr(client, "full_name", "") or "Une cliente"


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
        titre=f"{_cliente(booking)} a réservé",
        corps=f"{booking.service_name} {_quand(booking)}".strip(),
        lien=_lien(booking),
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
        titre="Acompte à vérifier",
        corps=f"{_cliente(booking)} a envoyé sa preuve de versement.",
        lien=_lien(booking),
    )


def acompte_expire(booking) -> None:
    """Le delai est passe : le creneau vient d'etre rendu."""
    _sans_casser(
        prevenir_salon,
        booking.tenant_id,
        genre=Genre.ACOMPTE_EXPIRE,
        titre="Créneau libéré",
        corps=(
            f"{_cliente(booking)} n'a pas réglé son acompte à temps "
            f"({_quand(booking)})."
        ),
        lien=_lien(booking),
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
        titre=f"{_cliente(booking)} a annulé",
        corps=f"{booking.service_name} {_quand(booking)}".strip(),
        lien=_lien(booking),
    )


def nouvel_avis(review) -> None:
    """Un avis vient d'etre depose."""
    note = getattr(review, "rating", None)
    etoiles = f"{note}/5" if note else ""
    _sans_casser(
        prevenir_salon,
        review.tenant_id,
        genre=Genre.AVIS,
        titre=f"Nouvel avis {etoiles}".strip(),
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
        titre=f"{entree.full_name} attend une place",
        corps=prestation,
        lien="/liste-attente",
    )


# ---------------------------------------------------------------------------
# Plateforme
# ---------------------------------------------------------------------------


def salon_inscrit(tenant) -> None:
    """Un salon vient de rejoindre la plateforme."""
    ville = getattr(tenant, "city", "") or ""
    _sans_casser(
        prevenir_plateforme,
        genre=Genre.SALON_INSCRIT,
        titre=f"Nouveau salon : {tenant.name}",
        corps=ville,
        tenant_id=tenant.id,
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
