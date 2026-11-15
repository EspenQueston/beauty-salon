"""La langue retenue sur le compte, et ce qu'elle change cote serveur.

L'espace pro se lit en francais ou en anglais. Ce choix est enregistre sur
le compte (`User.locale`) pour que ce qui part hors de toute requete — la
cloche, le push sur le telephone — parle a chacun dans sa langue. Deux
personnes du meme salon peuvent lire le meme evenement dans deux langues.
"""

from datetime import UTC, datetime, timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Membership
from apps.notifications import evenements
from apps.notifications.models import Genre, Notification
from apps.notifications.service import prevenir_salon
from apps.translations.langue import normaliser
from conftest import as_tenant
from tests.factories import BookingFactory, MembershipFactory, UserFactory

PASSWORD = "motdepasse-solide"


@pytest.fixture
def charges(monkeypatch):
    """Ce qui serait parti vers les appareils, par envoi."""
    from apps.notifications import tasks

    capturees = []
    monkeypatch.setattr(
        tasks.pousser_notification,
        "delay",
        lambda comptes, portee, charge: capturees.append((set(comptes), charge)),
    )
    return capturees


@pytest.fixture
def gerante_anglophone(salon_a):
    gerante = UserFactory(locale="en")
    MembershipFactory(tenant=salon_a.tenant, user=gerante, role=Membership.Role.MANAGER)
    return gerante


def notifications_de(salon, user) -> list[Notification]:
    with as_tenant(salon.tenant):
        return list(Notification.objects.filter(recipient=user))


# ---------------------------------------------------------------------------
# Retenir la langue
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_la_langue_choisie_est_retenue_sur_le_compte(api_client, salon_a):
    assert api_client.login(email=salon_a.owner.email, password=PASSWORD)

    reponse = api_client.post(reverse("accounts:langue"), {"langue": "en"}, format="json")

    assert reponse.status_code == 200
    assert reponse.json() == {"langue": "en"}
    salon_a.owner.refresh_from_db()
    assert salon_a.owner.locale == "en"


@pytest.mark.django_db
def test_une_langue_non_proposee_est_refusee(api_client, salon_a):
    assert api_client.login(email=salon_a.owner.email, password=PASSWORD)

    reponse = api_client.post(reverse("accounts:langue"), {"langue": "de"}, format="json")

    assert reponse.status_code == 400
    assert reponse.json()["code"] == "langue_inconnue"
    salon_a.owner.refresh_from_db()
    assert salon_a.owner.locale == "fr"


@pytest.mark.django_db
def test_sans_session_on_ne_retient_rien(api_client):
    reponse = api_client.post(reverse("accounts:langue"), {"langue": "en"}, format="json")

    assert reponse.status_code in (401, 403)


@pytest.mark.parametrize(
    "valeur, attendue",
    [
        ("en", "en"), ("en-GB", "en"), ("EN", "en"),
        ("fr", "fr"), ("de", "fr"), ("", "fr"), (None, "fr"),
    ],
)
def test_une_langue_inconnue_vaut_le_francais(valeur, attendue):
    assert normaliser(valeur) == attendue


# ---------------------------------------------------------------------------
# Chacun lit dans sa langue
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_le_meme_evenement_se_lit_dans_deux_langues(
    salon_a, gerante_anglophone, charges, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        combien = prevenir_salon(
            salon_a.tenant.id,
            genre=Genre.ACOMPTE_A_VERIFIER,
            titre=lambda langue: "Deposit to check" if langue == "en" else "Acompte à vérifier",
            lien="/agenda",
        )

    assert combien == 2
    (francaise,) = notifications_de(salon_a, salon_a.owner)
    (anglaise,) = notifications_de(salon_a, gerante_anglophone)
    assert francaise.titre == "Acompte à vérifier"
    assert anglaise.titre == "Deposit to check"

    # Un envoi par langue, chacun a ses seuls destinataires, boutons compris.
    par_titre = {charge["titre"]: (comptes, charge) for comptes, charge in charges}
    assert set(par_titre) == {"Acompte à vérifier", "Deposit to check"}
    comptes_en, charge_en = par_titre["Deposit to check"]
    assert comptes_en == {str(gerante_anglophone.id)}
    assert [a["titre"] for a in charge_en["actions"]] == ["Check deposit", "Open calendar"]
    _, charge_fr = par_titre["Acompte à vérifier"]
    assert [a["titre"] for a in charge_fr["actions"]] == ["Vérifier l'acompte", "Ouvrir l'agenda"]


@pytest.mark.django_db
def test_une_phrase_toute_faite_part_telle_quelle_pour_tous(salon_a, gerante_anglophone):
    """Les appelants qui n'ont qu'une phrase continuent de fonctionner."""
    prevenir_salon(salon_a.tenant.id, genre=Genre.AVIS, titre="Nouvel avis")

    assert notifications_de(salon_a, gerante_anglophone)[0].titre == "Nouvel avis"


@pytest.mark.django_db
def test_une_reservation_annoncee_en_anglais(salon_a, gerante_anglophone, charges):
    salon_a.tenant.timezone = "Asia/Shanghai"
    salon_a.tenant.save(update_fields=["timezone"])
    # 06:30 UTC le 3 avril : 14:30 a Guangzhou.
    debut = datetime(timezone.now().year + 1, 4, 3, 6, 30, tzinfo=UTC)
    with as_tenant(salon_a.tenant):
        reservation = BookingFactory(
            tenant=salon_a.tenant,
            service=salon_a.service,
            staff_member=salon_a.staff,
            customer=salon_a.customer,
            starts_at=debut,
            ends_at=debut + timedelta(minutes=60),
        )
        evenements.nouvelle_reservation(reservation)

    nom = salon_a.customer.full_name
    (anglaise,) = notifications_de(salon_a, gerante_anglophone)
    assert anglaise.titre == f"{nom} booked"
    assert anglaise.corps.endswith("on 3 Apr at 14:30")
    (francaise,) = notifications_de(salon_a, salon_a.owner)
    assert francaise.titre == f"{nom} a réservé"
    assert francaise.corps.endswith("le 03/04 à 14:30")
