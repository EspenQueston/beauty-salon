"""Les e-mails partent-ils complets ?

---------------------------------------------------------------------------
Ce que ces tests attrapent, et pourquoi ils existent
---------------------------------------------------------------------------

Un gabarit d'e-mail echoue silencieusement. Django rend une variable absente
comme une chaine vide : le message part, le serveur l'accepte, la cliente
recoit un titre vide ou un bouton qui ne mene nulle part, et rien dans les
journaux ne le signale. Aucune exception, aucune alerte - juste un message
abime chez le destinataire.

C'est exactement ce qui s'est produit ici : un gabarit affichait un
paragraphe d'introduction que la tache ne fournissait pas.

Ces tests passent donc par le **vrai** chemin de code - les taches Celery,
pas un contexte recopie a la main. Un contexte recopie testerait la copie,
pas l'envoi, et laisserait passer la meme variable oubliee.
"""

import re
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core import mail
from django.template.loader import render_to_string
from django.utils import timezone

from apps.notifications import tasks
from apps.scheduling.models import Booking
from conftest import as_tenant
from tests.factories import BookingFactory

# Un element visible qui ne contient rien : la trace d'une variable absente.
CREUX = re.compile(r"(?is)<(h1|p|strong|span|a|div)\b[^>]*>\s*</\1>")
CELLULE_VIDE = re.compile(r"(?is)<td\b[^>]*>\s*</td>")
BALISES = re.compile(r"(?s)<[^>]+>")
TETE = re.compile(r"(?is)<head.*?</head>|<style.*?</style>|<!--.*?-->")
PREHEADER = re.compile(r'(?is)<div style="display:none.*?</div>')


def texte_visible(html: str) -> str:
    """Ce que la destinataire lit vraiment.

    Le `<head>` et les `<style>` sont retires d'abord : sans cela on mesure
    du CSS et l'on croit avoir du texte la ou il n'y en a pas.
    """
    corps = PREHEADER.sub(" ", TETE.sub(" ", html))
    return re.sub(r"\s+", " ", BALISES.sub(" ", corps)).strip()


def controler(template: str, contexte: dict, destinataires: list[str]) -> str:
    """Rend le gabarit et enonce ce qu'un e-mail correct doit respecter."""
    html = render_to_string(f"emails/{template}.html", contexte)
    inspecter(template, html)
    assert destinataires and all(destinataires), f"{template} : sans destinataire."
    return html


def inspecter(nom: str, html: str) -> str:
    """Les memes exigences, sur un HTML deja rendu."""
    corps = PREHEADER.sub(" ", TETE.sub(" ", html))
    lu = texte_visible(html)

    assert not CREUX.findall(corps), (
        f"{nom} : un element visible est vide - une variable manque."
    )
    assert not CELLULE_VIDE.findall(corps), f"{nom} : une cellule est vide."

    for marqueur in ("None", "{{", "{%"):
        assert marqueur not in lu, f"{nom} : {marqueur} apparait dans le texte."

    for lien in re.findall(r'href="([^"]*)"', corps):
        assert lien and not lien.endswith(("=", "None")), (
            f"{nom} : lien incomplet - {lien}"
        )

    # Outlook rend le HTML avec le moteur de Word : une mise en page en flex
    # ou en grid s'y effondre en une colonne de texte nu.
    assert "display:flex" not in html and "display:grid" not in html, (
        f"{nom} : flex ou grid ne survit pas a Outlook."
    )

    assert len(lu) > 80, f"{nom} : le message est presque vide."
    return html


@pytest.fixture
def envois(monkeypatch):
    """Intercepte les envois au lieu de les poster, et garde le contexte."""
    captures = []

    def faux_send(subject, template, context, to, salon=None):
        captures.append((template, {**context, "subject": subject}, list(to)))
        return True

    monkeypatch.setattr(tasks, "_send", faux_send)
    return captures


@pytest.fixture
def cliente(salon_a):
    """La cliente de reference, avec une adresse.

    `CustomerFactory` n'en donne pas, et c'est correct : on peut reserver par
    telephone sans adresse. Mais un e-mail sans destinataire ne part pas, et
    ce fichier teste justement ce qui part.
    """
    with as_tenant(salon_a.tenant):
        salon_a.customer.email = "cliente@example.com"
        salon_a.customer.save(update_fields=["email"])
    return salon_a.customer


@pytest.fixture
def reservation(salon_a, cliente):
    """Une reservation avec acompte : le cas qui remplit le plus de blocs."""
    starts_at = timezone.now() + timedelta(days=2)
    with as_tenant(salon_a.tenant):
        return BookingFactory(
            tenant=salon_a.tenant,
            customer=salon_a.customer,
            staff_member=salon_a.staff,
            service=salon_a.service,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=120),
            status=Booking.Status.PENDING_PAYMENT,
            deposit_amount=Decimal("50"),
            customer_note="Je viendrai avec ma fille.",
        )


@pytest.mark.django_db
def test_every_notification_renders_a_complete_message(salon_a, reservation, envois):
    """Les six taches declenchees a la main, de bout en bout."""
    identifiants = (str(reservation.id), str(salon_a.tenant.id))

    with as_tenant(salon_a.tenant):
        tasks.send_booking_notifications.run(*identifiants)
        tasks.send_deposit_proof_alert.run(*identifiants)
        tasks.send_booking_accepted.run(*identifiants)
        tasks.send_deposit_rejected.run(*identifiants)
        tasks.send_booking_cancelled.run(*identifiants, by_salon=True)
        tasks.send_booking_cancelled.run(*identifiants, by_salon=False)

    vus = {template for template, _, _ in envois}
    assert vus == {
        "booking_confirmation",
        "booking_notification_salon",
        "deposit_proof_alert",
        "booking_accepted",
        "deposit_rejected",
        "booking_cancelled",
        "booking_cancelled_salon",
    }

    for template, contexte, destinataires in envois:
        controler(template, contexte, destinataires)


@pytest.mark.django_db
def test_the_reminder_and_the_review_request_render_completely(
    salon_a, reservation, envois
):
    """Les deux taches de balayage, amenees a trouver la reservation."""
    maintenant = timezone.now()

    with as_tenant(salon_a.tenant):
        Booking.objects.filter(id=reservation.id).update(
            starts_at=maintenant + tasks.REMINDER_LEAD + timedelta(minutes=5),
            ends_at=maintenant + tasks.REMINDER_LEAD + timedelta(minutes=125),
            status=Booking.Status.CONFIRMED,
        )
    tasks.send_booking_reminders()

    with as_tenant(salon_a.tenant):
        Booking.objects.filter(id=reservation.id).update(
            starts_at=maintenant - timedelta(hours=9),
            ends_at=maintenant - timedelta(hours=7),
            status=Booking.Status.COMPLETED,
        )
    tasks.send_review_requests()

    assert {template for template, _, _ in envois} == {
        "booking_reminder",
        "review_request",
    }
    for template, contexte, destinataires in envois:
        controler(template, contexte, destinataires)


@pytest.mark.django_db
def test_a_salon_email_offers_the_customer_number_as_a_link(
    salon_a, reservation, envois
):
    """Le salon lit ses e-mails sur un telephone, entre deux poses.

    Un numero en texte brut oblige a le recopier a la main pendant une pose.
    En `tel:`, un appui suffit - c'est le geste que ces messages appellent.
    """
    with as_tenant(salon_a.tenant):
        tasks.send_booking_notifications.run(
            str(reservation.id), str(salon_a.tenant.id)
        )

    contexte = next(c for t, c, _ in envois if t == "booking_notification_salon")
    html = render_to_string("emails/booking_notification_salon.html", contexte)

    assert f'href="tel:{reservation.customer.phone}"' in html
    assert f'href="mailto:{reservation.customer.email}"' in html


@pytest.mark.django_db
def test_no_message_is_sent_as_html_only(salon_a, reservation):
    """Un message sans partie texte est un signal de courrier indesirable.

    La plupart des filtres notent a la baisse un e-mail qui n'a qu'une
    partie HTML. Le corps texte n'est donc pas un vestige : il conditionne
    l'arrivee du message.
    """
    with as_tenant(salon_a.tenant):
        tasks.send_booking_notifications.run(
            str(reservation.id), str(salon_a.tenant.id)
        )

    assert mail.outbox, "aucun message n'est parti"
    for message in mail.outbox:
        assert message.body.strip(), "partie texte vide"
        types = {type_ for _, type_ in message.alternatives}
        assert types == {"text/html"}, "la partie HTML manque"


@pytest.mark.django_db
def test_a_booking_without_a_deposit_shows_no_payment_button(
    salon_a, cliente, envois
):
    """Un bouton de reglement sur un rendez-vous sans acompte inquiete pour
    rien : il laisse croire qu'il reste quelque chose a payer."""
    starts_at = timezone.now() + timedelta(days=2)
    with as_tenant(salon_a.tenant):
        sans_acompte = BookingFactory(
            tenant=salon_a.tenant,
            customer=salon_a.customer,
            staff_member=salon_a.staff,
            service=salon_a.service,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=120),
            status=Booking.Status.CONFIRMED,
            deposit_amount=Decimal("0"),
        )
        tasks.send_booking_notifications.run(
            str(sans_acompte.id), str(salon_a.tenant.id)
        )

    contexte = next(c for t, c, _ in envois if t == "booking_confirmation")
    html = render_to_string("emails/booking_confirmation.html", contexte)

    assert "acompte" not in html.lower()
    assert "/paiement" not in html
    # Et le message reste complet malgre tout.
    controler("booking_confirmation", contexte, [sans_acompte.customer.email])


@pytest.mark.django_db
def test_a_booking_with_a_deposit_carries_the_link_back_to_the_payment_page(
    salon_a, reservation, envois
):
    """Sans ce lien, une cliente qui ferme l'onglet perd son creneau.

    Le parcours web mene a la page de reglement, mais rien ne garantit
    qu'elle y aille tout de suite. Passe le delai, la tache de liberation
    rend le creneau - alors qu'elle voulait payer et n'avait plus le chemin.
    L'e-mail de confirmation est ce chemin.
    """
    with as_tenant(salon_a.tenant):
        tasks.send_booking_notifications.run(
            str(reservation.id), str(salon_a.tenant.id)
        )

    contexte = next(c for t, c, _ in envois if t == "booking_confirmation")
    html = render_to_string("emails/booking_confirmation.html", contexte)

    assert "/paiement?token=" in html, "le lien de reglement manque"
    assert "50 " in html, "le montant de l'acompte n'apparait pas"


# ---------------------------------------------------------------------------
# Les e-mails de compte
#
# Ils partaient en texte brut : ils avaient leur propre fonction d'envoi,
# ecrite avant celle des notifications et jamais alignee sur elle. Le premier
# message qu'un salon recevait de nous - la bienvenue - etait l'un des trois.
# ---------------------------------------------------------------------------


def dernier_html():
    """La partie HTML du dernier message parti."""
    assert mail.outbox, "aucun message n'est parti"
    alternatives = mail.outbox[-1].alternatives
    assert alternatives, "le message est parti sans partie HTML"
    return alternatives[0][0]


@pytest.mark.django_db
def test_the_welcome_email_is_designed_like_the_others(
    db, django_capture_on_commit_callbacks
):
    from apps.accounts.services import signup_salon

    # L'envoi est accroche a `on_commit` : une inscription a moitie faite ne
    # doit pas laisser partir un message de bienvenue. Sous test, rien n'est
    # jamais valide, donc il faut declencher les rappels a la main.
    with django_capture_on_commit_callbacks(execute=True):
        signup_salon(
            name="Chez Awa",
            slug="chezawa",
            email="awa@example.com",
            password="motdepasse-solide",
        )

    inspecter("signup_welcome", dernier_html())


@pytest.mark.django_db
def test_the_invitation_email_is_designed_like_the_others(salon_a):
    from apps.accounts.services import invite_member

    with as_tenant(salon_a.tenant):
        invite_member(
            tenant=salon_a.tenant,
            email="nouvelle@example.com",
            role="manager",
            invited_by=salon_a.owner,
        )

    inspecter("team_invitation", dernier_html())


@pytest.mark.django_db
def test_the_password_reset_email_is_designed_like_the_others(salon_a):
    """Et il ne parle pas d'« espace professionnel ».

    Les clientes et les salons partagent le meme modele de compte : ce
    message part aussi bien a une cliente qu'a une gerante, et le pied de
    page par defaut ne conviendrait qu'a la seconde.
    """
    from apps.accounts.services import request_password_reset

    request_password_reset(salon_a.owner.email)

    html = inspecter("password_reset", dernier_html())
    assert "espace professionnel" not in html


# ---------------------------------------------------------------------------
# Les commentaires qui n'en sont pas
# ---------------------------------------------------------------------------


def test_aucun_commentaire_de_gabarit_ne_fuit_dans_la_page():
    """`{# … #}` ne commente qu'une seule ligne.

    Étalé sur plusieurs, Django ne le reconnaît pas et le rend **tel quel**.
    Rien n'échoue : le gabarit se rend, l'e-mail part, et la cliente lit une
    note de développeur au milieu de son rendez-vous.

    C'est arrivé : l'e-mail de report en contenait une de trois lignes,
    visible par toutes les clientes dont un rendez-vous avait été déplacé.
    Un commentaire sur plusieurs lignes s'écrit `{% comment %}`.
    """
    import re
    from pathlib import Path

    from django.conf import settings

    racines = [Path(d) for d in settings.TEMPLATES[0]["DIRS"]]
    fautifs = []

    for racine in racines:
        for fichier in sorted(racine.rglob("*.html")):
            texte = fichier.read_text(encoding="utf-8")
            for ouverture in re.finditer(r"\{#", texte):
                fermeture = texte.find("#}", ouverture.start())
                if fermeture == -1 or "\n" in texte[ouverture.start() : fermeture]:
                    ligne = texte[: ouverture.start()].count("\n") + 1
                    fautifs.append(f"{fichier.relative_to(racine)}:{ligne}")

    assert not fautifs, (
        "Ces commentaires s'étalent sur plusieurs lignes et seront affichés "
        f"tels quels. Utilisez {{% comment %}} : {fautifs}"
    )


@pytest.mark.django_db
def test_la_cliente_recoit_un_message_signe_du_salon(salon_a, reservation):
    """Le nom du salon en expediteur, et la reponse qui va au salon."""
    from django.core import mail

    with as_tenant(salon_a.tenant):
        salon_a.profile.contact_email = "contact@blondrose.com"
        salon_a.profile.save(update_fields=["contact_email"])
        tasks.send_booking_notifications.run(str(reservation.id), str(salon_a.tenant.id))

    cliente = next(m for m in mail.outbox if reservation.customer.email in m.to)
    salon = next(m for m in mail.outbox if reservation.customer.email not in m.to)
    assert cliente.from_email.startswith(f"{salon_a.tenant.name} via Beauty Salon <")
    assert cliente.reply_to == ["contact@blondrose.com"]
    # L'alerte au salon garde l'expediteur de la plateforme.
    assert "via Beauty Salon" not in salon.from_email
    assert salon.reply_to == []


@pytest.mark.django_db
def test_sans_email_de_contact_la_reponse_n_est_pas_detournee(salon_a, reservation):
    from django.core import mail

    with as_tenant(salon_a.tenant):
        tasks.send_booking_notifications.run(str(reservation.id), str(salon_a.tenant.id))

    cliente = next(m for m in mail.outbox if reservation.customer.email in m.to)
    assert cliente.reply_to == []
