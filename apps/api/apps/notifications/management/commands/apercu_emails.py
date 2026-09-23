"""Rend tous les e-mails dans un dossier, pour les regarder.

    python manage.py apercu_emails --dossier vues/emails

Un e-mail ne se relit pas dans son code : on le regarde. Cette commande écrit
un fichier par message et par langue, plus un sommaire qui les ouvre tous.

---------------------------------------------------------------------------
Un contexte de démonstration, et pourquoi c'est le bon choix ici
---------------------------------------------------------------------------

Le contexte est fabriqué de toutes pièces, sans base de données. Ce n'est pas
un raccourci : cette commande sert à **regarder la mise en page**, et une
mise en page se juge sur un cas complet — un rendez-vous avec options, article
acheté, déplacement à domicile et acompte — qu'aucune base de développement ne
contient par hasard.

La vérification que les vraies tâches remplissent bien toutes les variables
est un autre travail, et il est fait ailleurs : `tests/test_email_templates.py`
passe par les tâches Celery elles-mêmes et refuse tout élément vide.

Rien n'est envoyé.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from django.core.management.base import BaseCommand
from django.template.loader import render_to_string

from apps.notifications.details import grouper
from apps.notifications.textes import textes

#: Les messages adressés aux clientes suivent la langue ; ceux du salon et des
#: comptes restent en français, et sont rendus une seule fois.
CLIENTE = [
    "booking_confirmation",
    "booking_reminder",
    "booking_accepted",
    "booking_cancelled",
    "booking_rescheduled",
    "deposit_rejected",
    "review_request",
]
SALON = [
    "booking_notification_salon",
    "booking_cancelled_salon",
    "deposit_proof_alert",
    "signup_welcome",
    "team_invitation",
    "password_reset",
]

MARQUE = "#B4436C"


ACCROCHES = {
    "booking_confirmation": "confirmation_intro",
    "booking_reminder": "rappel_intro",
    "booking_accepted": "accepte_intro",
    "booking_cancelled": "annule_intro_salon",
    "booking_rescheduled": "deplace_intro",
    "deposit_rejected": "acompte_refuse_intro",
    "review_request": "avis_comment",
}

SALON_ACCROCHES = {
    "booking_notification_salon": "Une nouvelle cliente vient de reserver.",
    "booking_cancelled_salon": "Une cliente a annule son rendez-vous.",
    "deposit_proof_alert": "Une preuve de paiement attend votre verification.",
    "signup_welcome": "Votre salon est cree. Voici ou le retrouver.",
    "team_invitation": "Vous etes invitee a rejoindre une equipe.",
    "password_reset": "Vous avez demande a reinitialiser votre mot de passe.",
}


def _accroche(nom: str, t, salon: str) -> str:
    if nom in SALON_ACCROCHES:
        return SALON_ACCROCHES[nom]
    return t.dire(ACCROCHES.get(nom, "confirmation_intro"), salon=salon)


def _contexte(nom: str, langue: str) -> dict:
    """Un rendez-vous de démonstration, volontairement chargé."""
    t = textes(langue)
    salon = SimpleNamespace(name="Blond Rose", currency="XAF", slug="blondrose")
    cliente = SimpleNamespace(
        full_name="Grâce Mabiala",
        phone="+242 06 12 34 56",
        email="grace@example.com",
    )
    profile = SimpleNamespace(
        late_policy=(
            "Nous faisons notre possible pour vous prendre quand même, mais la "
            "prestation peut être raccourcie."
        ),
        late_tolerance_minutes=15,
        address="12 avenue de la Paix",
        city="Brazzaville",
    )
    booking = SimpleNamespace(
        service_name="Box braids longues, mèches XXL",
        total_amount=Decimal("52000"),
        deposit_amount=Decimal("15000"),
        deposit_received=Decimal("15000"),
        deposit_paid=True,
        cancellation_reason="Imprévu familial",
        options_snapshot=[{"name": "Baby hair", "price": "0.00"}],
        items_snapshot=[
            {"name": "Mèches Kanekalon", "quantity": 3, "total": "9000"}
        ],
        travel_zone_name="Poto-Poto",
        address="12 avenue de la Paix, immeuble bleu",
        language=langue,
    )

    faits = [
        {"label": t["prestation"], "value": booking.service_name, "wide": True},
        {"label": t["date"], "value": t.dire("le_a", date="14/10/2026", heure="10:30")},
        {"label": t["duree"], "value": t.dire("duree_heures_minutes", heures=3, minutes="30")},
        {"label": t["avec"], "value": "Fatou"},
        {"label": "Baby hair", "value": t["inclus"]},
        {"label": "Mèches Kanekalon × 3", "value": "9 000 XAF"},
        {"label": t["a_domicile"], "value": "Poto-Poto"},
        {"label": t["adresse"], "value": booking.address, "wide": True},
        {"label": t["total"], "value": "52 000 XAF", "strong": True},
    ]

    return {
        "t": t,
        "langue": langue,
        "subject": "Aperçu",
        "salon": salon,
        "customer": cliente,
        "profile": profile,
        "booking": booking,
        "staff_member": SimpleNamespace(name="Fatou"),
        "invitation": SimpleNamespace(get_role_display=lambda: "Gérante"),
        "user": SimpleNamespace(email="awa@example.com"),
        "brand": MARQUE,
        "details": grouper(faits),
        "salutation": t.dire("bonjour", prenom=cliente.full_name),
        "pre": t.dire(
            "pre_confirmation",
            service=booking.service_name,
            date="14/10/2026",
            heure="10:30",
        ),
        # Chaque message a sa propre accroche : une seule pour tous donnerait
        # un apercu qui ment — on verrait le texte de la cliente en haut de
        # l e-mail du salon.
        "intro": _accroche(nom, t, salon.name),
        "headline": t["annule_par_salon"] if "cancel" in nom else t["deplace_titre"],
        "deposit_label": "15 000 XAF",
        "deposit_hint": t.dire("acompte_a_regler_dans", minutes=30),
        "deposit_title": t.dire("annule_acompte", montant="15 000 XAF"),
        "late_title": t.dire("retard_tolere", minutes=15),
        "ancien_titre": t.dire("deplace_ancien_titre", date="12/10/2026", heure="09:00"),
        "inchange": t.dire("deplace_inchange", acompte=t["deplace_inchange_acompte"]),
        "reason": "La capture est illisible.",
        "by_salon": True,
        "awaiting_payment": True,
        "date_label": "14/10/2026",
        "time_label": "10:30",
        "duration_label": t.dire("duree_heures_minutes", heures=3, minutes="30"),
        "review_criteria": ["Accueil", "Écoute", "Résultat", "Propreté", "Ponctualité"],
        "review_url": "https://blondrose.example.com/avis?token=x",
        "payment_url": "https://blondrose.example.com/paiement?token=x",
        "status_url": "https://blondrose.example.com/rendez-vous?token=x",
        "booking_url": "https://blondrose.example.com/reserver",
        "maps_url": "https://maps.example.com/?q=blondrose",
        "agenda_url": "https://app.example.com/dashboard/agenda",
        "app_url": "https://app.example.com",
        "dashboard_url": "https://app.example.com",
        "accept_url": "https://app.example.com/invitation?token=x",
        "reset_url": "https://app.example.com/mot-de-passe/nouveau?token=x",
        "hostname": "blondrose.example.com",
        "role": "Gérante",
        "invited_by": SimpleNamespace(email="awa@example.com"),
        "pied": (
            t.dire("avis_pied", salon=salon.name)
            if nom == "review_request"
            else t.dire("pied_cliente", salon=salon.name)
        ),
        "name": "Awa",
    }


class Command(BaseCommand):
    help = "Rend les e-mails en HTML, dans les deux langues, sans rien envoyer."

    def add_arguments(self, parser):
        parser.add_argument("--dossier", default="vues/emails")

    def handle(self, *args, **options):
        dossier = Path(options["dossier"])
        dossier.mkdir(parents=True, exist_ok=True)

        a_rendre = [(langue, nom) for langue in ("fr", "en") for nom in CLIENTE]
        a_rendre += [("fr", nom) for nom in SALON]

        rendus: list[tuple[str, str, str]] = []
        for langue, nom in a_rendre:
            try:
                html = render_to_string(f"emails/{nom}.html", _contexte(nom, langue))
            except Exception as exc:  # noqa: BLE001 - on veut savoir lequel
                self.stderr.write(f"  {nom} [{langue}] : {exc}")
                continue
            fichier = dossier / f"{langue}-{nom}.html"
            fichier.write_text(html, encoding="utf-8")
            rendus.append((langue, nom, fichier.name))

        self._sommaire(dossier, rendus)
        self.stdout.write(self.style.SUCCESS(f"{len(rendus)} e-mail(s) rendus"))

    def _sommaire(self, dossier: Path, rendus) -> None:
        lignes = "".join(
            f'<li><a href="{fichier}">{langue} · {nom}</a></li>'
            for langue, nom, fichier in rendus
        )
        (dossier / "index.html").write_text(
            "<!doctype html><meta charset=utf-8>"
            "<title>Apercu des e-mails</title>"
            "<style>body{font:15px/1.6 system-ui;padding:2rem}li{margin:.2rem 0}</style>"
            f"<h1>Apercu des e-mails</h1><ul>{lignes}</ul>",
            encoding="utf-8",
        )
