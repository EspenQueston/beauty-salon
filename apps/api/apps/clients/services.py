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
        ClientSalonLink.objects.filter(user=user).select_related("tenant").order_by("-created_at")
    )


def bookings_for(user) -> list[dict]:
    """Rendez-vous de cette cliente, tous salons confondus.

    Renvoie des dictionnaires deja aplatis plutot que des objets : les lignes
    viennent de contextes de base differents, et les manipuler ensemble sous
    forme d'instances Django inviterait a declencher, plus tard, une requete
    paresseuse hors du bon contexte.
    """
    from apps.payments.services import expirer
    from apps.payments.tokens import (
        checkin_code,
        checkin_token,
        payment_token,
        status_token,
    )
    from apps.scheduling.models import Booking
    from apps.scheduling.services.annulation import etat_annulation

    # Visites que la cliente a retirees de sa vue. Chargees une fois : un
    # test par ligne ferait autant de requetes que de rendez-vous.
    hidden = set(HiddenBooking.objects.filter(user=user).values_list("booking_id", flat=True))

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

                    # Un delai de reglement passe se solde ici aussi.
                    #
                    # L'espace cliente affichait « Un acompte reste a regler »
                    # avec un bouton qui menait a « le delai est depasse » :
                    # on invitait a payer, puis on fermait la porte. La cause
                    # etait que la transition n'existait que dans le balayage
                    # Celery, et qu'un poste sans worker la laissait en
                    # suspens indefiniment.
                    #
                    # `expirer` ne touche que ce qui est deja echu et sans
                    # preuve ; sur tout le reste elle ne fait rien.
                    expirer(booking)

                    rows.append(
                        {
                            "id": str(booking.id),
                            "salon_name": link.tenant.name,
                            "salon_slug": link.tenant.slug,
                            # Celle du rendez-vous, pas celle du salon
                            # aujourd'hui : un salon qui change de devise ne
                            # doit pas reetiqueter ses visites passees.
                            # `or` pour les lignes anterieures a la colonne.
                            "currency": booking.currency or link.tenant.currency,
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
                            "cancellation_reason": booking.cancellation_reason,
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
                            # ----- l'annulation ---------------------------
                            #
                            # Meme raisonnement que pour l'avis : la regle
                            # est decidee ici, par la fonction que la route
                            # d'annulation consulte elle aussi. Laisser le
                            # navigateur calculer « plus de 24 h avant »
                            # donnerait deux verdicts qui finissent par
                            # diverger — un bouton propose sur un rendez-vous
                            # que le serveur refusera.
                            **etat_annulation(booking),
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
        "review_until": ((booking.starts_at + TOKEN_MAX_AGE).isoformat() if can_review else ""),
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


# ---------------------------------------------------------------------------
# Mot de passe oublie
# ---------------------------------------------------------------------------


def demander_nouveau_mot_de_passe(email: str, tenant, langue: str = "fr") -> None:
    """Envoie a une cliente le lien pour choisir un nouveau mot de passe.

    Le lien ramene sur le mini-site d'ou vient la demande, aux couleurs du
    salon et dans la langue ou elle lisait. Un compte d'equipe (sans profil
    cliente) recoit le lien de l'espace professionnel, le seul ou son mot de
    passe lui sert.

    Rien ne distingue la reponse selon que le compte existe ou non : ce
    formulaire ne doit pas devenir un annuaire des adresses inscrites.
    """
    import logging

    from django.conf import settings
    from django.contrib.auth.tokens import default_token_generator
    from django.utils.encoding import force_bytes
    from django.utils.http import urlsafe_base64_encode

    from apps.accounts.models import User
    from apps.accounts.services import request_password_reset
    from apps.notifications.email import send_email
    from apps.notifications.tasks import _brand_colour, _salon_base_url
    from apps.notifications.textes import textes
    from apps.salons.models import SalonProfile

    logger = logging.getLogger(__name__)
    user = User.objects.filter(email=email.strip().lower(), is_active=True).first()
    if user is None:
        logger.info("Mot de passe oublie : adresse inconnue.")
        return
    if not hasattr(user, "client_profile"):
        request_password_reset(user.email)
        return

    langue = langue if langue in ("fr", "en") else "fr"
    t = textes(langue)
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    jeton = default_token_generator.make_token(user)
    heures = settings.PASSWORD_RESET_TIMEOUT // 3600
    lien = f"{_salon_base_url(tenant)}/{langue}/compte/mot-de-passe?uid={uid}&token={jeton}"

    with tenant_context(tenant.id):
        profil = SalonProfile.objects.filter(tenant_id=tenant.id).first()
        send_email(
            subject=t.dire("mdp_objet", salon=tenant.name),
            template="client_password_reset",
            context={
                "t": t,
                "langue": langue,
                "salon": tenant,
                "brand": _brand_colour(profil),
                "intro": t.dire("mdp_intro", salon=tenant.name),
                "validite": t.dire("mdp_validite", heures=heures),
                "reset_url": lien,
                "pied": t["mdp_pied"],
            },
            to=[user.email],
            salon=tenant,
        )
