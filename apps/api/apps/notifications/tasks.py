"""Envois differes.

Toutes les taches reposent tenant_context() elles-memes : un worker Celery
n'a pas de requete HTTP, donc pas de middleware, donc pas de contexte. Sans
ce bloc, les querysets tenant renvoient vide et les politiques RLS bloquent
tout - le systeme echoue ferme, ce qui est le comportement voulu, mais il
faut bien poser le contexte quelque part.
"""

import logging
import re
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

from celery import shared_task
from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.common.db import tenant_context
from apps.notifications.details import grouper
from apps.notifications.email import send_email
from apps.notifications.textes import Textes, textes
from apps.scheduling.models import Booking
from apps.tenants.models import Tenant
from apps.translations.services import texte as traduction

logger = logging.getLogger(__name__)

# Fenetre de rappel : les rendez-vous qui commencent dans ~24h.
REMINDER_LEAD = timedelta(hours=24)
REMINDER_WINDOW = timedelta(minutes=30)


# L'envoi lui-meme vit dans `email.py` : les comptes s'en servent aussi, et
# deux fonctions d'envoi finissent toujours par diverger. Importe sous son
# ancien nom pour que les taches ci-dessous restent lisibles.
_send = send_email


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_booking_notifications(self, booking_id: str, tenant_id: str):
    """Confirmation a la cliente et alerte au salon, juste apres la reservation."""
    try:
        with tenant_context(tenant_id):
            booking = (
                Booking.objects.select_related("customer", "staff_member", "tenant")
                .filter(id=booking_id)
                .first()
            )
            if booking is None:
                logger.warning("Reservation %s introuvable, notification abandonnee.", booking_id)
                return

            context = _booking_context(booking)

            _send(
                subject=context["t"].dire(
                    "confirmation_objet", salon=booking.tenant.name
                ),
                template="booking_confirmation",
                context={
                    **context,
                    "intro": context["t"].dire(
                        "confirmation_intro", salon=booking.tenant.name
                    ),
                    # Le delai figure dans l'e-mail parce que c'est la
                    # qu'on le lit : la page de paiement affiche un compte a
                    # rebours, mais une cliente qui a ferme l'onglet n'a plus
                    # que ce message pour savoir qu'il y en avait un.
                    "deposit_hint": _deposit_hint(booking, context["t"]),
                    # Le lien de reglement ne part que si l'acompte est
                    # encore du. C'est la seule facon de revenir a la page
                    # de paiement pour qui a ferme l'onglet - sans lui, le
                    # creneau expire alors que la cliente voulait payer.
                    "payment_url": _payment_url(booking),
                },
                to=[booking.customer.email],
            )
            _send(
                subject=f"Nouvelle réservation - {booking.service_name}",
                template="booking_notification_salon",
                context={
                    **context,
                    "intro": "Une nouvelle cliente vient de réserver.",
                    "awaiting_payment": booking.status
                    == Booking.Status.PENDING_PAYMENT,
                },
                to=_salon_recipients(booking.tenant),
            )
    except Exception as exc:  # noqa: BLE001 - on retente, sans perdre la trace
        logger.exception("Echec de notification pour la reservation %s.", booking_id)
        raise self.retry(exc=exc) from exc


@shared_task
def send_booking_reminders():
    """Rappels J-1, balayes toutes les 15 minutes.

    Une tache periodique idempotente est preferable a une tache planifiee a
    l'heure exacte : il n'y a rien a revoquer quand un rendez-vous est annule
    ou deplace, et `reminder_sent_at` garantit un seul envoi.
    """
    now = timezone.now()
    target_start = now + REMINDER_LEAD
    target_end = target_start + REMINDER_WINDOW

    sent = 0
    # Parcours inter-tenants : chaque salon est traite dans son propre
    # contexte, jamais tous ensemble.
    for tenant_id in Tenant.objects.filter(status=Tenant.Status.ACTIVE).values_list(
        "id", flat=True
    ):
        with tenant_context(tenant_id):
            bookings = Booking.objects.select_related(
                "customer", "staff_member", "tenant"
            ).filter(
                status__in=(Booking.Status.REQUESTED, Booking.Status.CONFIRMED),
                reminder_sent_at__isnull=True,
                starts_at__gte=target_start,
                starts_at__lt=target_end,
            )

            for booking in bookings:
                rappel = _booking_context(booking)
                delivered = _send(
                    subject=rappel["t"].dire(
                        "rappel_objet", salon=booking.tenant.name
                    ),
                    template="booking_reminder",
                    context={
                        **rappel,
                        "intro": rappel["t"].dire(
                            "rappel_intro", salon=booking.tenant.name
                        ),
                        "pre": rappel["t"].dire(
                            "pre_rappel",
                            heure=rappel["time_label"],
                            salon=booking.tenant.name,
                        ),
                    },
                    to=[booking.customer.email],
                )
                # Marque meme sans e-mail : sinon la cliente sans adresse
                # serait reexaminee a chaque passage de la tache.
                booking.reminder_sent_at = now
                booking.save(update_fields=["reminder_sent_at", "updated_at"])
                sent += int(delivered)

    logger.info("Rappels envoyes : %s", sent)
    return sent


def _booking_context(booking: Booking) -> dict:
    """Tout ce dont un gabarit a besoin, dans la langue de la cliente."""
    from apps.salons.models import SalonProfile

    # La langue retenue au moment de la reservation, et non celle du salon
    # aujourd'hui : c'est dans celle-la que la cliente a lu ce qu'elle
    # acceptait.
    t = textes(booking.language)

    local_start = booking.starts_at.astimezone(_tenant_timezone(booking.tenant))

    # Le profil porte les regles que la cliente doit connaitre avant de venir
    # - retard, annulation. Les rappeler dans l'e-mail est le seul moment ou
    # elle les lit vraiment : sur le mini-site, elle a deja decide.
    profile = SalonProfile.objects.filter(tenant_id=booking.tenant_id).first()

    # Les regles du salon, dans la langue de la cliente quand elles y sont.
    #
    # Le gabarit lisait `profile.late_policy` en direct, donc le francais : un
    # e-mail anglais portait sa politique de retard en francais au milieu. Les
    # serialiseurs du mini-site font deja ce remplacement ; ici il n y a pas de
    # serialiseur, il faut donc le demander.
    regles = (
        SimpleNamespace(
            late_policy=traduction(profile, "late_policy", booking.language),
            late_tolerance_minutes=profile.late_tolerance_minutes,
            cancellation_policy=traduction(
                profile, "cancellation_policy", booking.language
            ),
            cancellation_deadline_hours=profile.cancellation_deadline_hours,
        )
        if profile is not None
        else None
    )

    site = _salon_base_url(booking.tenant)

    return {
        "t": t,
        "langue": booking.language,
        "booking": booking,
        "salon": booking.tenant,
        "profile": regles,
        "customer": booking.customer,
        "staff_member": booking.staff_member,
        # Couleur de marque du salon, pour les e-mails qui lui sont adresses.
        # Le HTML d'un e-mail ne lit aucune variable CSS : la valeur doit
        # etre resolue ici et interpolee en dur.
        "brand": _brand_colour(profile),
        "details": _detail_rows(booking, profile, t),
        "deposit_label": _money(booking.deposit_amount, booking.tenant.currency),
        "late_title": _late_title(profile, t),
        "site_url": site,
        "booking_url": f"{site}/reserver",
        # L'espace professionnel, pas le mini-site : ces liens ne partent
        # qu'aux e-mails du salon.
        "agenda_url": f"{settings.APP_BASE_URL}/dashboard/agenda",
        "waitlist_url": f"{settings.APP_BASE_URL}/dashboard/liste-attente",
        "maps_url": _maps_url(profile),
        "local_start": local_start,
        # Duree reelle du rendez-vous, options comprises : la duree de la
        # prestation seule serait fausse des qu'une option rallonge la pose.
        "duration_label": _duration_label(booking, t),
        "date_label": local_start.strftime("%d/%m/%Y"),
        "time_label": local_start.strftime("%H:%M"),
        # Le pre-en-tete par defaut : ce que la boite de reception montre a
        # cote de l'objet. Chaque tache peut le remplacer.
        # Le pied porte le nom du salon : comme la salutation, il ne peut pas
        # se resoudre dans le gabarit.
        "pied": t.dire("pied_cliente", salon=booking.tenant.name),
        # La salutation porte le prenom : le gabarit ne sait pas appeler
        # une phrase avec des variables.
        "salutation": t.dire(
            "bonjour", prenom=booking.customer.full_name
        ),
        "pre": t.dire(
            "pre_confirmation",
            service=booking.service_name,
            date=local_start.strftime("%d/%m/%Y"),
            heure=local_start.strftime("%H:%M"),
        ),
    }


# Teinte par defaut, identique a celle du produit. Un salon qui n'a pas
# choisi de palette garde un e-mail coherent plutot qu'un lien noir.
DEFAULT_BRAND = "#B4436C"


def _maps_url(profile) -> str:
    """Itineraire vers le salon, ou chaine vide.

    Vide plutot que None : le gabarit teste la verite de la variable, et un
    bouton « Voir l'itineraire » qui mene nulle part est pire qu'absent.
    """
    if profile is None:
        return ""
    query = " ".join(part for part in (profile.address, profile.city) if part)
    if not query:
        return ""
    from urllib.parse import quote

    return f"https://www.google.com/maps/search/?api=1&query={quote(query)}"


def _brand_colour(profile) -> str:
    theme = getattr(profile, "theme_config", None) or {}
    colour = theme.get("primary") or DEFAULT_BRAND
    # Une valeur libre finirait interpolee dans un attribut `style` : on
    # n'accepte que ce qui ressemble vraiment a une couleur hexadecimale.
    return colour if re.fullmatch(r"#[0-9a-fA-F]{6}", colour) else DEFAULT_BRAND


def _money(amount, currency: str) -> str:
    """« 150 CNY ». Le formatage fin appartient au navigateur, pas ici."""
    if amount is None:
        return ""
    quantised = amount.quantize(Decimal("1")) if amount == amount.to_integral() else amount
    return f"{quantised} {currency}"


def _deposit_hint(booking, t: Textes) -> str:
    """La phrase sous le montant de l'acompte, ou rien."""
    if not booking.deposit_amount:
        return ""
    if booking.deposit_paid:
        return t["acompte_deja_regle"]

    from apps.payments.services import PAYMENT_WINDOW

    minutes = int(PAYMENT_WINDOW.total_seconds() // 60)
    return t.dire("acompte_a_regler_dans", minutes=minutes)


def _late_title(profile, t: Textes) -> str:
    minutes = getattr(profile, "late_tolerance_minutes", 0) or 0
    if minutes <= 0:
        return t["retard_a_l_heure"]
    return t.dire("retard_tolere", minutes=minutes)


def _detail_rows(booking, profile, t: Textes) -> list[list[dict]]:
    """Les faits du rendez-vous, groupes deux par deux.

    Compose ici plutot que dans chaque gabarit : douze gabarits qui
    recomposent la meme liste divergent au premier champ ajoute, et c'est
    exactement ce qui produit un e-mail ou le prix manque.

    Rend des **rangees** et non des faits : le gabarit se contente de les
    poser, sans avoir a ouvrir un `<tr>` au milieu d'une boucle selon la
    parite et selon la largeur du fait. Voir `_grouper`.
    """
    currency = booking.tenant.currency
    local = booking.starts_at.astimezone(_tenant_timezone(booking.tenant))

    faits = [
        # `wide` : un nom de prestation ne tient pas dans une demi-largeur de
        # telephone, et se briserait au milieu d'un mot.
        {
            "label": t["prestation"],
            "value": booking.service_name or t["prestation"],
            "wide": True,
        },
        {
            "label": t["date"],
            "value": t.dire(
                "le_a", date=f"{local:%d/%m/%Y}", heure=f"{local:%H:%M}"
            ),
        },
        {"label": t["duree"], "value": _duration_label(booking, t)},
    ]

    if booking.staff_member:
        faits.append({"label": t["avec"], "value": booking.staff_member.name})

    for item in booking.options_snapshot or []:
        faits.append({"label": item.get("name", t["option"]), "value": t["inclus"]})

    for item in booking.items_snapshot or []:
        nom = item.get("name", t["article"])
        quantite = item.get("quantity", 1)
        faits.append(
            {
                "label": f"{nom} × {quantite}",
                "value": _money(Decimal(item.get("total", "0")), currency),
            }
        )

    if booking.travel_zone_name:
        faits.append({"label": t["a_domicile"], "value": booking.travel_zone_name})
        if booking.address:
            faits.append(
                {"label": t["adresse"], "value": booking.address, "wide": True}
            )

    faits.append(
        {
            "label": t["total"],
            "value": _money(booking.total_amount, currency),
            "strong": True,
        }
    )
    return grouper(faits)


def _duration_label(booking, t: Textes) -> str:
    """« 3 h 30 » plutot que « 210 minutes » : c'est ainsi qu'on lit un
    rendez-vous."""
    minutes = int((booking.ends_at - booking.starts_at).total_seconds() // 60)
    hours, rest = divmod(minutes, 60)
    if hours and rest:
        return t.dire("duree_heures_minutes", heures=hours, minutes=f"{rest:02d}")
    if hours:
        return t.dire("duree_heures", heures=hours)
    return t.dire("duree_minutes", minutes=rest)


def _tenant_timezone(tenant):
    from zoneinfo import ZoneInfo

    return ZoneInfo(tenant.timezone)


def _salon_recipients(tenant) -> list[str]:
    from apps.accounts.models import Membership

    return list(
        Membership.objects.filter(
            tenant=tenant,
            status=Membership.Status.ACTIVE,
            role__in=(Membership.Role.OWNER, Membership.Role.MANAGER),
        ).values_list("user__email", flat=True)
    )


# Les criteres notes, nommes dans l'e-mail d'invitation. Importes du modele
# plutot que recopies : deux listes qui divergent, et la cliente lit dans son
# courrier des criteres que le formulaire ne lui demande pas.
#
# En bas de fichier et non en tete : `apps.reviews` importe `scheduling`, qui
# importe ce module pour ses taches. Remonter cette ligne referme la boucle au
# demarrage. D'ou le `noqa` — la regle a raison en general, pas ici.
from apps.reviews.models import Review as _Review  # noqa: E402

ReviewCriteria = _Review.CRITERIA


def _invite_to_review(booking) -> bool:
    """Envoie la demande d'avis pour ce rendez-vous, une fois.

    `review_invited_at` est pose **meme quand l'e-mail ne part pas** - cliente
    sans adresse, serveur SMTP muet. Sans cela, le balayage de securite
    reexaminerait la meme ligne a chaque passage, indefiniment.
    """
    from apps.reviews.services import review_url

    if booking.review_invited_at is not None:
        return False

    context = _booking_context(booking)
    t = context["t"]
    context["intro"] = t.dire("avis_comment", salon=booking.tenant.name)
    context["pre"] = t.dire("pre_avis", service=booking.service_name)
    context["pied"] = t.dire("avis_pied", salon=booking.tenant.name)
    context["review_url"] = review_url(booking, _salon_base_url(booking.tenant))
    # Les critères sont nommés dans l'e-mail : savoir sur quoi on va être
    # interrogée avant de cliquer fait la différence entre « encore un
    # formulaire » et « deux minutes, je sais quoi dire ».
    context["review_criteria"] = [str(label) for _, label in ReviewCriteria]

    delivered = _send(
        subject=context["t"].dire("avis_objet", salon=booking.tenant.name),
        template="review_request",
        context=context,
        to=[booking.customer.email],
    )

    booking.review_invited_at = timezone.now()
    booking.save(update_fields=["review_invited_at", "updated_at"])
    return bool(delivered)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_review_request(self, booking_id: str, tenant_id: str):
    """Demande d'avis, declenchee par le salon lui-meme.

    -----------------------------------------------------------------------
    Pourquoi a la confirmation, et non a l'heure de fin prevue
    -----------------------------------------------------------------------

    L'envoi etait auparavant accroche a `ends_at` - l'heure a laquelle le
    rendez-vous *devait* se terminer - avec quatre heures de politesse, parce
    qu'on ne savait pas si la cliente etait encore dans le salon. Deux
    consequences : une prestation qui debordait recevait sa demande avant
    d'etre finie, et une prestation marquee terminee le lendemain matin
    n'en recevait aucune.

    C'est desormais le salon qui declenche : quand il marque « Terminée », il
    affirme que la prestation est finie. Il n'y a plus rien a deviner, donc
    plus de delai a respecter.
    """
    try:
        with tenant_context(tenant_id):
            booking = (
                Booking.objects.select_related("customer", "staff_member", "tenant")
                .filter(id=booking_id, status=Booking.Status.COMPLETED)
                .first()
            )
            if booking is None:
                return
            _invite_to_review(booking)
    except Exception as exc:  # noqa: BLE001 - on retente, sans perdre la trace
        logger.exception("Echec de demande d'avis pour %s.", booking_id)
        raise self.retry(exc=exc) from exc


@shared_task
def send_review_requests():
    """Filet de securite : les prestations terminees qu'aucun envoi n'a
    couvertes.

    La demande part normalement a l'instant ou le salon marque « Terminée »
    (voir `send_review_request`). Ce balayage rattrape les cas ou cet envoi
    n'a pas eu lieu - worker arrete au mauvais moment, statut change
    directement en base, tache perdue. Il est idempotent : `review_invited_at`
    garantit qu'aucune cliente ne recoit deux fois la meme demande.
    """
    now = timezone.now()
    sent = 0

    for tenant_id in Tenant.objects.filter(status=Tenant.Status.ACTIVE).values_list(
        "id", flat=True
    ):
        with tenant_context(tenant_id):
            bookings = Booking.objects.select_related(
                "customer", "staff_member", "tenant"
            ).filter(
                status=Booking.Status.COMPLETED,
                review_invited_at__isnull=True,
                # Au-dela de quelques jours, la demande arrive trop tard pour
                # etre utile et ressemble a du courrier non sollicite.
                ends_at__gte=now - timedelta(days=7),
            )

            for booking in bookings:
                sent += int(_invite_to_review(booking))

    logger.info("Demandes d'avis rattrapees : %s", sent)
    return sent


def _payment_url(booking) -> str:
    """Lien signé vers la page de règlement, ou chaîne vide.

    Vide quand il n'y a rien à régler : le gabarit teste la variable, et un
    bouton « Régler l'acompte » sur un rendez-vous déjà payé inquiète.
    """
    if not booking.deposit_amount or booking.deposit_paid:
        return ""

    from apps.payments.tokens import payment_token

    return (
        f"{_salon_base_url(booking.tenant)}/paiement"
        f"?token={payment_token(booking)}"
    )


def _salon_base_url(tenant) -> str:
    """Adresse publique du mini-site, d'ou part le lien d'avis."""
    scheme = "http" if settings.DEBUG else "https"
    port = f":{settings.WEB_PORT}" if settings.DEBUG else ""
    return f"{scheme}://{tenant.slug}.{settings.PLATFORM_DOMAIN}{port}"


# ---------------------------------------------------------------------------
# Acompte : prevenir, des deux cotes
# ---------------------------------------------------------------------------


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_deposit_proof_alert(self, booking_id: str, tenant_id: str):
    """Prévient le salon qu'un acompte attend d'être vérifié.

    C'est la notification la plus urgente du produit : une cliente a envoyé
    de l'argent et attend une réponse. Sans alerte, elle reste devant un
    téléphone muet et rappelle — ou annule.

    L'envoi va aux adresses de la direction, comme les réservations. Le SMS
    et WhatsApp demanderaient un fournisseur qui n'est pas encore choisi.
    """
    try:
        with tenant_context(tenant_id):
            booking = (
                Booking.objects.select_related("customer", "staff_member", "tenant")
                .filter(id=booking_id)
                .first()
            )
            if booking is None:
                logger.warning("Reservation %s introuvable.", booking_id)
                return

            _send(
                subject=f"Acompte à vérifier — {booking.customer.full_name}",
                template="deposit_proof_alert",
                context={
                    **_booking_context(booking),
                    "intro": (
                        "Une cliente a envoyé une preuve de versement "
                        "pour son acompte."
                    ),
                },
                to=_salon_recipients(booking.tenant),
            )
    except Exception as exc:  # noqa: BLE001 - on retente, sans perdre la trace
        logger.exception("Echec d'alerte d'acompte pour %s.", booking_id)
        raise self.retry(exc=exc) from exc


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_booking_accepted(self, booking_id: str, tenant_id: str):
    """Confirme à la cliente que le salon a tout validé."""
    try:
        with tenant_context(tenant_id):
            booking = (
                Booking.objects.select_related("customer", "staff_member", "tenant")
                .filter(id=booking_id)
                .first()
            )
            if booking is None:
                return

            accepte = _booking_context(booking)
            _send(
                subject=accepte["t"].dire(
                    "accepte_objet", salon=booking.tenant.name
                ),
                template="booking_accepted",
                context={
                    **accepte,
                    "intro": accepte["t"].dire(
                        "accepte_intro", salon=booking.tenant.name
                    ),
                    "pre": accepte["t"].dire(
                        "pre_accepte",
                        date=accepte["date_label"],
                        heure=accepte["time_label"],
                    ),
                },
                to=[booking.customer.email],
            )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Echec de confirmation pour %s.", booking_id)
        raise self.retry(exc=exc) from exc


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_deposit_rejected(self, booking_id: str, tenant_id: str):
    """Dit à la cliente que le salon n'a pas retrouvé son versement.

    Le rendez-vous n'est pas annulé : elle peut renvoyer une capture. Le
    message doit donc ouvrir une porte, pas la fermer.
    """
    try:
        with tenant_context(tenant_id):
            booking = (
                Booking.objects.select_related("customer", "staff_member", "tenant")
                .filter(id=booking_id)
                .first()
            )
            if booking is None:
                return

            context = _booking_context(booking)
            proof = getattr(booking, "deposit_proof", None)
            context["reason"] = proof.rejection_reason if proof else ""
            context["intro"] = (
                f"Bonjour {booking.customer.full_name}, {booking.tenant.name} "
                "n'a pas retrouvé votre versement."
            )
            context["payment_url"] = _payment_url(booking)

            _send(
                subject=context["t"].dire(
                    "acompte_refuse_objet", salon=booking.tenant.name
                ),
                template="deposit_rejected",
                context=context,
                to=[booking.customer.email],
            )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Echec d'avis de refus pour %s.", booking_id)
        raise self.retry(exc=exc) from exc


@shared_task
def release_unpaid_bookings():
    """Rend les créneaux réservés puis jamais réglés.

    Balayage périodique idempotent, comme les rappels : rien à révoquer si
    la cliente paie entre deux passages.
    """
    from apps.payments.services import release_expired

    released = 0
    for tenant_id in Tenant.objects.filter(status=Tenant.Status.ACTIVE).values_list(
        "id", flat=True
    ):
        with tenant_context(tenant_id):
            released += release_expired()

    logger.info("Creneaux rendus faute de paiement : %s", released)
    return released


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_booking_cancelled(self, booking_id: str, tenant_id: str, by_salon: bool = True):
    """Prévient quand un rendez-vous est annulé.

    C'était le seul moment du parcours où personne n'était averti. Une
    cliente qui se déplace pour un rendez-vous annulé la veille est le pire
    résultat possible du produit — et c'était silencieux.

    Le message dit **qui** a annulé : « le salon a annulé » et « vous avez
    annulé » n'appellent pas la même réaction, et se tromper de sujet dans
    ce message-là fâche plus que de ne rien envoyer.
    """
    try:
        with tenant_context(tenant_id):
            booking = (
                Booking.objects.select_related("customer", "staff_member", "tenant")
                .filter(id=booking_id)
                .first()
            )
            if booking is None:
                return

            context = _booking_context(booking)
            context["by_salon"] = by_salon
            t = context["t"]
            context["headline"] = (
                t["annule_par_salon"] if by_salon else t["annule_par_cliente"]
            )
            context["intro"] = (
                t.dire("annule_intro_salon", salon=booking.tenant.name)
                if by_salon
                else t["annule_intro_cliente"]
            )
            context["deposit_title"] = t.dire(
                "annule_acompte",
                montant=_money(
                    booking.deposit_received, booking.tenant.currency
                ),
            )
            context["pre"] = t.dire(
                "pre_annule",
                service=booking.service_name,
                date=context["date_label"],
            )

            _send(
                subject=context["t"].dire(
                    "annule_objet", salon=booking.tenant.name
                ),
                template="booking_cancelled",
                context=context,
                to=[booking.customer.email],
            )

            # Le salon aussi : une annulation libère un créneau qu'il peut
            # reproposer, et la liste d'attente n'existe que pour ça.
            if not by_salon:
                _send(
                    subject=f"Annulation — {booking.customer.full_name}",
                    template="booking_cancelled_salon",
                    context={
                        **context,
                        "intro": "Une cliente a annulé son rendez-vous.",
                    },
                    to=_salon_recipients(booking.tenant),
                )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Echec d'avis d'annulation pour %s.", booking_id)
        raise self.retry(exc=exc) from exc


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_booking_rescheduled(
    self, booking_id: str, tenant_id: str, ancienne_date: str = ""
):
    """Previent la cliente qu'un rendez-vous a change d'heure.

    C'etait silencieux. Le salon deplacait le creneau depuis son agenda, la
    cliente se presentait a l'ancienne heure — exactement le defaut qu'on
    avait corrige pour l'annulation, et qu'on avait laisse ouvert a cote.

    Le message met les deux dates cote a cote, l'ancienne en premier. Donner
    seulement la nouvelle obligerait a retrouver l'e-mail precedent pour
    comprendre ce qui a bouge, et une cliente qui doute de sa memoire
    telephonera.
    """
    try:
        with tenant_context(tenant_id):
            booking = (
                Booking.objects.select_related("customer", "staff_member", "tenant")
                .filter(id=booking_id)
                .first()
            )
            if booking is None:
                return

            context = _booking_context(booking)
            t = context["t"]
            context["headline"] = t["deplace_titre"]
            context["intro"] = t.dire(
                "deplace_intro", salon=booking.tenant.name
            )
            context["pre"] = t.dire(
                "pre_deplace",
                date=context["date_label"],
                heure=context["time_label"],
            )

            ancien = _ancienne_date(booking, ancienne_date)
            context["ancienne_date"] = ancien["date"]
            context["ancienne_heure"] = ancien["heure"]
            context["ancien_titre"] = (
                t.dire(
                    "deplace_ancien_titre",
                    date=ancien["date"],
                    heure=ancien["heure"],
                )
                if ancien["date"]
                else t["deplace_ancien_annule"]
            )
            context["inchange"] = t.dire(
                "deplace_inchange",
                acompte=(
                    t["deplace_inchange_acompte"] if booking.deposit_paid else ""
                ),
            )
            context["status_url"] = _status_url(booking)

            _send(
                subject=context["t"].dire(
                    "deplace_objet", salon=booking.tenant.name
                ),
                template="booking_rescheduled",
                context=context,
                to=[booking.customer.email],
            )
    except Exception as exc:  # noqa: BLE001
        raise self.retry(exc=exc) from exc


def _ancienne_date(booking, iso: str) -> dict:
    """L'ancien creneau, dans le fuseau du salon.

    Il arrive en ISO depuis le service, qui l'a lu avant d'ecrire : la tache
    s'execute apres l'enregistrement et ne peut plus le retrouver en base.
    """
    if not iso:
        return {"date": "", "heure": ""}

    from django.utils.dateparse import parse_datetime

    moment = parse_datetime(iso)
    if moment is None:
        return {"date": "", "heure": ""}

    local = moment.astimezone(_tenant_timezone(booking.tenant))
    return {"date": local.strftime("%d/%m/%Y"), "heure": local.strftime("%H:%M")}


def _status_url(booking) -> str:
    """Page de suivi du rendez-vous, sur le mini-site du salon."""
    from apps.payments.tokens import status_token

    return f"{_salon_base_url(booking.tenant)}/rendez-vous?token={status_token(booking)}"


# ---------------------------------------------------------------------------
# Notifications push
# ---------------------------------------------------------------------------


@shared_task(bind=True, max_retries=3, default_retry_delay=120)
def pousser_notification(
    self,
    comptes: list[str],
    portee: str,
    charge: dict,
    abonnements: list[str] | None = None,
):
    """Depose une notification sur les appareils d'un ou plusieurs comptes.

    -----------------------------------------------------------------------
    Pourquoi la reprise ne rejoue pas le lot entier
    -----------------------------------------------------------------------

    Une gerante a souvent trois appareils : un telephone, un ordinateur au
    salon, un portable. Si le deuxieme echoue sur un 500 passager, rejouer la
    tache telle quelle ferait sonner les deux autres une seconde fois — puis
    une troisieme. On preferera toujours une notification manquee a trois
    notifications identiques : la seconde apprend qu'il ne faut pas les lire.

    La reprise ne repart donc qu'avec les abonnements reellement en echec,
    passes explicitement par `abonnements`.

    -----------------------------------------------------------------------
    Ce que fait cette tache des abonnements morts
    -----------------------------------------------------------------------

    Elle les supprime. Un service de push qui repond 404 ou 410 dit que la
    boite n'existe plus — desinstallation, donnees du site videes, telephone
    change. La ligne ne redeviendra jamais valide, et la garder ferait
    reessayer a chaque evenement, pour toujours.
    """
    from apps.notifications import push
    from apps.notifications.models import PushSubscription

    if not push.configure():
        # Installation sans cles VAPID : la cloche fonctionne, le push non.
        # Ce n'est pas une erreur, c'est une configuration.
        return {"envoyes": 0, "motif": "push non configure"}

    cibles = PushSubscription.objects.filter(user_id__in=comptes, portee=portee)
    if abonnements is not None:
        cibles = cibles.filter(pk__in=abonnements)

    envoyes = 0
    disparus: list[str] = []
    a_reprendre: list[str] = []

    for abonnement in cibles:
        try:
            vivant = push.envoyer(abonnement, charge)
        except Exception:
            # Passager : on compte, on garde, et on repassera.
            a_reprendre.append(str(abonnement.pk))
            PushSubscription.objects.filter(pk=abonnement.pk).update(
                echecs=models.F("echecs") + 1
            )
            continue

        if vivant:
            envoyes += 1
            PushSubscription.objects.filter(pk=abonnement.pk).update(
                derniere_reussite=timezone.now(), echecs=0
            )
        else:
            disparus.append(str(abonnement.pk))

    if disparus:
        PushSubscription.objects.filter(pk__in=disparus).delete()

    if a_reprendre and self.request.retries < self.max_retries:
        raise self.retry(
            kwargs={
                "comptes": comptes,
                "portee": portee,
                "charge": charge,
                "abonnements": a_reprendre,
            }
        )

    return {"envoyes": envoyes, "supprimes": len(disparus), "repris": len(a_reprendre)}
