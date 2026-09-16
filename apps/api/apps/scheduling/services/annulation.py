"""Qui peut annuler, et jusqu'a quand.

---------------------------------------------------------------------------
Pourquoi une regle, et un seul endroit ou elle vit
---------------------------------------------------------------------------

Le salon publie sa politique : « annulation gratuite jusqu'a 24 h avant ».
C'est une promesse, pas un texte decoratif — et jusqu'ici elle n'etait
appliquee nulle part. La cliente n'avait aucun bouton, donc aucune facon de
tenir sa part ; le salon recevait des appels telephoniques pour un geste que
la page aurait pu faire.

Trois endroits doivent maintenant s'accorder sur la meme reponse : l'espace
de la cliente, la page de suivi d'un rendez-vous, et la route qui execute
l'annulation. Trois calculs separes auraient fini par diverger — un bouton
propose sur un rendez-vous qui refuse, ou refuse sur un rendez-vous qui
accepte. C'est le meme piege que l'eligibilite d'un avis, resolu de la meme
facon : une fonction, appelee partout.

---------------------------------------------------------------------------
Ce que la cliente peut annuler, et ce qu'elle ne peut pas
---------------------------------------------------------------------------

Elle annule ce qui n'a pas encore commence. Une fois arrivee au salon, le
rendez-vous ne se decommande plus depuis un telephone : il se termine, ou il
se constate. Un « annuler » sur une prestation en cours ferait disparaitre
une seance que quelqu'un est en train de realiser.

Au-dela du delai annonce, le bouton disparait — et il est remplace par le
numero du salon. C'est la seule reponse honnete : la politique dit qu'il
faut parler a quelqu'un, la page ne doit pas laisser croire l'inverse.
"""

from datetime import timedelta

from django.utils import timezone

from ..models import Booking

# Etats depuis lesquels une cliente peut encore se decommander elle-meme.
#
# `CHECKED_IN` en est volontairement absent : elle est dans le fauteuil.
ANNULABLES = (
    Booking.Status.PENDING_PAYMENT,
    Booking.Status.REQUESTED,
    Booking.Status.CONFIRMED,
)


def delai_du_salon(tenant) -> int:
    """Heures d'avance exigees avant une annulation, selon le salon."""
    from apps.salons.models import SalonProfile

    profile = SalonProfile.objects.filter(tenant_id=tenant.id if tenant else None).first()
    return profile.cancellation_deadline_hours if profile else 24


def limite(booking, heures: int | None = None):
    """Instant apres lequel la cliente ne peut plus annuler seule."""
    if heures is None:
        heures = delai_du_salon(booking.tenant)
    return booking.starts_at - timedelta(hours=heures)


def cliente_peut_annuler(booking, maintenant=None, heures: int | None = None) -> bool:
    """La cliente est-elle encore dans la fenetre annoncee par le salon ?

    Le salon, lui, n'est pas soumis a cette fenetre : sa politique engage ses
    clientes, pas lui. `cancel_booking` reste donc appelable depuis le
    tableau de bord quel que soit le delai.
    """
    if booking.status not in ANNULABLES:
        return False

    maintenant = maintenant or timezone.now()
    return maintenant <= limite(booking, heures)


def etat_annulation(booking, maintenant=None) -> dict:
    """Ce qu'il faut pour afficher — et pour justifier — le bouton.

    Renvoie toujours les trois cles, y compris quand l'annulation est
    fermee : l'interface a besoin de la date limite pour expliquer *pourquoi*
    le bouton n'est pas la, et un champ absent se lit comme une erreur de
    chargement.
    """
    from apps.payments.tokens import cancel_token

    heures = delai_du_salon(booking.tenant)
    possible = cliente_peut_annuler(booking, maintenant, heures)

    return {
        "can_cancel": possible,
        # Le jeton n'est emis que si l'annulation est reellement ouverte :
        # une capacite qu'on distribue « au cas ou » finit par etre utilisee
        # hors du cas prevu.
        "cancel_token": cancel_token(booking) if possible else "",
        "cancel_until": limite(booking, heures).isoformat()
        if booking.status in ANNULABLES
        else "",
        "cancel_deadline_hours": heures,
    }
