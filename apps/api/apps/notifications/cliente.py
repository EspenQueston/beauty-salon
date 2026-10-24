"""Les notifications sur l'appareil d'une cliente.

Les e-mails partent toujours ; le push s'y ajoute pour les comptes clientes
qui l'ont accepte depuis leur espace (portee « cliente »). Il ne touche que
les rendez-vous qui appartiennent a un compte (voir `comptes_de_la_cliente`) :
une cliente qui a reserve sans compte n'a pas d'appareil inscrit, et n'est
donc jamais visee.

Cinq moments, ceux ou rater l'information coute un rendez-vous : la
confirmation, le rappel de la veille, l'annulation par le salon, le
deplacement, l'acompte non retrouve.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

TEXTES = {
    "fr": {
        "accepte": ("Rendez-vous confirmé — {salon}", "{service} le {date} à {heure}."),
        "rappel": ("Rappel : votre rendez-vous chez {salon}", "{service} le {date} à {heure}."),
        "annule": (
            "Rendez-vous annulé par {salon}",
            "{service} du {date}. Touchez pour reprendre rendez-vous.",
        ),
        "deplace": ("Rendez-vous déplacé — {salon}", "Nouveau créneau : {date} à {heure}."),
        "acompte_refuse": (
            "Acompte non retrouvé — {salon}",
            "Renvoyez votre preuve de versement pour garder votre créneau du {date}.",
        ),
    },
    "en": {
        "accepte": ("Appointment confirmed — {salon}", "{service} on {date} at {heure}."),
        "rappel": ("Reminder: your appointment at {salon}", "{service} on {date} at {heure}."),
        "annule": (
            "Appointment cancelled by {salon}",
            "{service} on {date}. Tap to book again.",
        ),
        "deplace": ("Appointment moved — {salon}", "New time: {date} at {heure}."),
        "acompte_refuse": (
            "Deposit not found — {salon}",
            "Send your proof of payment again to keep your {date} slot.",
        ),
    },
}


def comptes_de_la_cliente(booking) -> list[str]:
    """Les comptes a qui ce rendez-vous appartient.

    Les memes que ceux qui le voient dans leur espace
    (`clients.services.bookings_for`) : le compte connecte qui l'a pris, et
    le compte cliente verifie qui porte l'adresse du rendez-vous. Jamais
    les comptes rattaches a la fiche : elle est retrouvee par le telephone,
    et pousser a ses comptes previendrait qui a reserve un jour avec le
    numero d'une autre.
    """
    from apps.accounts.models import User
    from apps.clients.services import est_cliente

    candidats = []
    if booking.compte_id:
        candidats += list(User.objects.filter(pk=booking.compte_id, is_active=True))
    if booking.contact_email:
        candidats += list(
            User.objects.filter(
                email__iexact=booking.contact_email,
                is_active=True,
                email_verified_at__isnull=False,
            )
        )
    return sorted({str(user.pk) for user in candidats if est_cliente(user)})


def prevenir_cliente(booking, genre: str, *, date: str, heure: str) -> None:
    """Pousse la notification aux appareils de la cliente. Ne leve jamais."""
    try:
        comptes = comptes_de_la_cliente(booking)
        if not comptes:
            return
        langue = booking.language if booking.language in TEXTES else "fr"
        titre, corps = TEXTES[langue][genre]
        valeurs = {
            "salon": booking.tenant.name,
            "service": booking.service_name,
            "date": date,
            "heure": heure,
        }
        # Le francais n'a pas de prefixe dans l'adresse, l'anglais si. Et
        # toujours l'espace cliente : il liste les rendez-vous de tous ses
        # salons, ou que l'appareil ait ete inscrit.
        lien = ("/en" if langue == "en" else "") + "/compte#rendez-vous"
        charge = {
            "titre": titre.format(**valeurs)[:120],
            "corps": corps.format(**valeurs)[:240],
            "lien": lien,
            "genre": f"cliente_{genre}",
        }

        from .service import _pousser_apres_commit

        _pousser_apres_commit(comptes, "cliente", charge)
    except Exception:  # noqa: BLE001 - l'e-mail est deja parti, c'est l'essentiel
        logger.exception("Push cliente non depose (%s).", genre)
