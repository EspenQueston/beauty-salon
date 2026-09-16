"""Les reglages qui decident des creneaux, et ce qu'ils refusent.

Le risque de cet ecran n'est pas la faute de frappe : c'est le reglage
**silencieux**. Un delai minimal plus long que la fenetre de reservation ne
produit aucune erreur, il produit une liste vide - et personne ne relie
« aucune disponibilite » au champ qui en est la cause.
"""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from apps.salons.models import SalonProfile
from conftest import as_tenant, salon_host

BRAZZAVILLE = ZoneInfo("Africa/Brazzaville")
HOST = {"Host": salon_host("blondrose")}
PASSWORD = "motdepasse-solide"


def login(client, user):
    assert client.login(email=user.email, password=PASSWORD)
    return client


@pytest.mark.django_db
def test_the_booking_window_cannot_exceed_thirty_days(api_client, salon_a):
    """Personne ne sait en janvier de quoi sera fait son mois de mai."""
    login(api_client, salon_a.owner)

    response = api_client.patch(
        "/api/v1/salon-profile", {"max_advance_days": 365}, format="json"
    )

    assert response.status_code == 400
    assert "max_advance_days" in str(response.data)


@pytest.mark.django_db
def test_a_lead_time_longer_than_the_window_is_refused(api_client, salon_a):
    """Le reglage qui vide l'agenda sans rien dire."""
    login(api_client, salon_a.owner)

    # Six jours de delai sur une fenetre de trois : chaque valeur est
    # acceptable seule, c'est leur combinaison qui vide l'agenda. Seul un
    # controle croise peut l'attraper.
    response = api_client.patch(
        "/api/v1/salon-profile",
        {"min_lead_time_minutes": 60 * 24 * 6, "max_advance_days": 3},
        format="json",
    )

    assert response.status_code == 400
    assert "plus aucun créneau" in str(response.data)


@pytest.mark.django_db
def test_sensible_settings_are_accepted(api_client, salon_a):
    login(api_client, salon_a.owner)

    response = api_client.patch(
        "/api/v1/salon-profile",
        {"min_lead_time_minutes": 120, "max_advance_days": 30},
        format="json",
    )

    assert response.status_code == 200


@pytest.mark.django_db
def test_the_public_range_never_exceeds_the_salons_horizon(api_client, salon_a):
    """Une plage demandee au-dela de la fenetre ne doit rien inventer."""
    with as_tenant(salon_a.tenant):
        SalonProfile.objects.filter(tenant=salon_a.tenant).update(max_advance_days=7)

    today = datetime.now(BRAZZAVILLE).date()
    far: date = today + timedelta(days=25)

    response = api_client.get(
        "/api/v1/public/availability",
        {
            "service": str(salon_a.service.id),
            "date_from": far.isoformat(),
            "date_to": (far + timedelta(days=3)).isoformat(),
        },
        headers=HOST,
    )

    assert response.status_code == 200
    # Au-dela de l'horizon du salon, la liste est vide plutot que fausse.
    assert response.data["slots"] == []


@pytest.mark.django_db
def test_slots_stay_within_the_opening_hours(api_client, salon_a):
    """Le moteur ne propose rien hors des heures d'ouverture."""
    from apps.scheduling.models import BusinessHours

    today = datetime.now(BRAZZAVILLE).date()
    ahead = (0 - today.weekday()) % 7 or 7
    monday = today + timedelta(days=ahead + 7)

    response = api_client.get(
        "/api/v1/public/availability",
        {
            "service": str(salon_a.service.id),
            "date_from": monday.isoformat(),
            "date_to": monday.isoformat(),
        },
        headers=HOST,
    )

    with as_tenant(salon_a.tenant):
        hours = list(
            BusinessHours.objects.filter(weekday=0, staff_member__isnull=True)
        )

    assert hours, "Le jeu d'essai doit ouvrir le lundi"
    windows = [(row.starts_at, row.ends_at) for row in hours]

    for slot in response.data["slots"]:
        local = datetime.fromisoformat(
            slot["starts_at"].replace("Z", "+00:00")
        ).astimezone(BRAZZAVILLE)
        moment: time = local.time()
        assert any(
            start <= moment < end for start, end in windows
        ), f"{moment} tombe hors des heures d'ouverture {windows}"
