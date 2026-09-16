"""Lecture de l'historique d'une cliente, un salon a la fois.

C'est le fichier qui porte la garantie d'isolation du cote client. Le
principe tient en une phrase : **on ne fait jamais une requete qui traverse
les salons**, on en fait une par salon, chacune dans son propre contexte.

La table de rattachement (`ClientSalonLink`) sert d'index et ne contient que
des identifiants. Tout ce qui est reellement sensible - le nom de la
prestation, le montant, la note interne - est lu derriere la politique RLS
du salon concerne.
"""

from apps.common.db import tenant_context

from apps.reviews.models import Review

from .models import ClientSalonLink, HiddenBooking

# Un historique de cliente se consulte, il ne se depouille pas.
MAX_BOOKINGS_PER_SALON = 40


def linked_salons(user):
    """Salons auxquels ce compte est rattache, du plus recent au plus ancien."""
    return list(
        ClientSalonLink.objects.filter(user=user)
        .select_related("tenant")
        .order_by("-created_at")
    )


def bookings_for(user) -> list[dict]:
    """Rendez-vous de cette cliente, tous salons confondus.

    Renvoie des dictionnaires deja aplatis plutot que des objets : les lignes
    viennent de contextes de base differents, et les manipuler ensemble sous
    forme d'instances Django inviterait a declencher, plus tard, une requete
    paresseuse hors du bon contexte.
    """
    from apps.payments.tokens import (
        checkin_code,
        checkin_token,
        payment_token,
        status_token,
    )
    from apps.scheduling.models import Booking

    # Visites que la cliente a retirees de sa vue. Chargees une fois : un
    # test par ligne ferait autant de requetes que de rendez-vous.
    hidden = set(
        HiddenBooking.objects.filter(user=user).values_list("booking_id", flat=True)
    )

    rows: list[dict] = []
    links = linked_salons(user)
    if not links:
        return []

    # On sort d'abord du contexte pose par le middleware.
    #
    # Une requete arrivant sur `blondrose.localhost` s'execute dans le
    # contexte de blondrose. Or cet espace n'appartient a aucun salon : il
    # appartient a la cliente. `tenant_context` refuse - a juste titre - de
    # basculer d'un salon vers un autre sans sortir, donc on repasse
    # explicitement par le vide avant d'entrer dans chacun.
    #
    # `None` ne desactive rien : il *vide* la variable de session, ce qui
    # rend au contraire toutes les tables tenant invisibles. La securite ne
    # depend donc jamais de la boucle ci-dessous, seulement du contexte
    # ouvert a chaque tour.
    with tenant_context(None):
        for link in links:
            # Un contexte par salon. C'est ce qui garantit qu'aucune ligne
            # d'un salon ne peut apparaitre dans la lecture d'un autre.
            with tenant_context(link.tenant_id):
                bookings = (
                    Booking.objects.filter(customer_id=link.customer_id)
                    .select_related("staff_member")
                    .order_by("-starts_at")[:MAX_BOOKINGS_PER_SALON]
                )

                for booking in bookings:
                    if booking.id in hidden:
                        continue
                    rows.append(
                        {
                            "id": str(booking.id),
                            "salon_name": link.tenant.name,
                            "salon_slug": link.tenant.slug,
                            "currency": link.tenant.currency,
                            "starts_at": booking.starts_at,
                            "ends_at": booking.ends_at,
                            "status": booking.status,
                            "service_name": booking.service_name,
                            "staff_member_name": (
                                booking.staff_member.name if booking.staff_member else ""
                            ),
                            "total_amount": str(booking.total_amount),
                            "deposit_amount": str(booking.deposit_amount),
                            "options_snapshot": booking.options_snapshot,
                            "travel_zone_name": booking.travel_zone_name,
                            "address": booking.address,
                            # Laissez-passer vers la page de paiement, pour
                            # les seuls rendez-vous qui attendent un acompte.
                            # Sans lui, une cliente qui a ferme l'onglet de
                            # paiement n'avait plus aucun chemin pour revenir
                            # regler - et son creneau se liberait sans qu'elle
                            # comprenne pourquoi.
                            "payment_token": (
                                payment_token(booking)
                                if booking.status == Booking.Status.PENDING_PAYMENT
                                else ""
                            ),
                            # QR d'arrivee, seulement une fois le rendez-vous
                            # confirme par le salon : le montrer avant
                            # laisserait croire qu'il vaut confirmation, et
                            # une cliente se presenterait pour un creneau que
                            # le salon n'a pas encore accepte.
                            "checkin_token": (
                                checkin_token(booking)
                                if booking.status == Booking.Status.CONFIRMED
                                else ""
                            ),
                            # Le meme droit d'arrivee, sous une forme qui se
                            # tape et se dicte. Il accompagne toujours le QR :
                            # l'appareil photo du salon peut etre en panne, et
                            # une cliente devant un comptoir n'a pas a
                            # repartir pour autant.
                            "checkin_code": (
                                checkin_code(booking)
                                if booking.status == Booking.Status.CONFIRMED
                                else ""
                            ),
                            # Le suivi detaille : tout ce que cette carte ne
                            # peut pas montrer sans devenir illisible - l'etat
                            # du versement, le detail des articles, le QR, le
                            # motif d'une annulation. Emis pour tous les
                            # rendez-vous, y compris passes : c'est la page
                            # qu'on rouvre pour retrouver ce qu'on a paye.
                            "status_token": status_token(booking),
                            # Une visite close se retire de l'historique ; un
                            # rendez-vous a venir, non - c'est au salon qu'on
                            # annule, pas en effacant la ligne.
                            "can_forget": booking.status
                            in (
                                Booking.Status.COMPLETED,
                                Booking.Status.CANCELLED,
                                Booking.Status.NO_SHOW,
                            ),
                            # ----- l'avis ---------------------------------
                            #
                            # L'eligibilite est decidee ici, par la meme
                            # fonction que la page d'avis elle-meme. Laisser
                            # le navigateur en juger - « termine et vieux de
                            # moins de 30 jours » - aurait produit deux
                            # verdicts qui finissent par diverger : un bouton
                            # propose sur une visite deja notee, ou refuse sur
                            # une visite qui l'accepte encore.
                            **_review_state(booking),
                        }
                    )

    # Tri final en Python : les listes viennent de requetes separees, il n'y
    # a pas de « ORDER BY » global possible.
    rows.sort(key=lambda row: row["starts_at"], reverse=True)
    return rows


def _review_state(booking) -> dict:
    """Ou en est l'avis sur cette visite.

    -----------------------------------------------------------------------
    Trois etats, et un seul bouton
    -----------------------------------------------------------------------

      - **notable** : la prestation est honoree, elle date de moins de trente
        jours, et personne n'a encore ecrit. Un jeton part avec la ligne.
      - **deja note** : l'avis existe. Le bouton disparait - reproposer de
        noter une visite deja notee ferait cliquer pour rien, et la page
        d'avis repondrait par un refus.
      - **trop ancienne** : au-dela de trente jours, le souvenir est trop
        flou pour que la note dise encore quelque chose d'utile. La ligne
        reste dans l'historique, sans bouton.

    La decision est prise ici, par `is_eligible` - la meme fonction que la
    page d'avis interroge. Laisser le navigateur en juger aurait produit deux
    verdicts qui divergent tot ou tard.

    `review_until` accompagne le jeton pour que l'ecran puisse dire combien de
    temps il reste. Une echeance qu'on ne voit pas approcher n'en est pas une.
    """
    from apps.reviews.services import TOKEN_MAX_AGE, is_eligible, make_token

    reviewed = Review.objects.filter(booking_id=booking.id).exists()
    can_review, _ = is_eligible(booking)

    return {
        "reviewed": reviewed,
        "can_review": can_review,
        "review_token": make_token(booking.id) if can_review else "",
        "review_until": (
            (booking.starts_at + TOKEN_MAX_AGE).isoformat() if can_review else ""
        ),
    }


def attach(user, tenant_id, customer_id) -> None:
    """Rattache une fiche cliente d'un salon a un compte plateforme.

    Appele au moment de la reservation quand la cliente est connectee. Sans
    ce rattachement, le rendez-vous existe mais n'apparaitrait jamais dans
    son espace.
    """
    ClientSalonLink.objects.get_or_create(
        user=user, tenant_id=tenant_id, defaults={"customer_id": customer_id}
    )
