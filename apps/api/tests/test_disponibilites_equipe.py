"""Les disponibilités vues depuis le tableau de bord.

---------------------------------------------------------------------------
Ce que ces tests protègent
---------------------------------------------------------------------------

Le panneau « Déplacer le rendez-vous » interrogeait `public/availability`.
Ce préfixe n'est pas une convention de nommage : c'est ce sur quoi le
middleware décide comment déterminer le salon — par le **nom d'hôte** pour
`public/`, par le membership ailleurs. Le tableau de bord n'ayant aucun
sous-domaine de salon, le serveur répondait 404 à chaque ouverture du
panneau. Le déplacement d'un rendez-vous n'a donc jamais fonctionné.

Le premier test ci-dessous échoue si l'on revient en arrière ; le second
tient la règle que cette route existe pour honorer.
"""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Membership
from apps.catalog.models import Service
from conftest import as_tenant
from tests.factories import MembershipFactory, UserFactory

PASSWORD = "motdepasse-solide"


def login(client, user):
    assert client.login(email=user.email, password=PASSWORD)
    return client


def prochain_jour_ouvre(salon) -> str:
    """Un lundi-samedi à venir : le salon est fermé le dimanche."""
    jour = timezone.localtime(timezone.now()).date() + timedelta(days=1)
    while jour.weekday() == 6:
        jour += timedelta(days=1)
    return jour.isoformat()


@pytest.mark.django_db
def test_le_tableau_de_bord_lit_les_disponibilites_sans_sous_domaine(
    api_client, salon_a
):
    """Le cœur du défaut.

    L'appel part de `app.<domaine>` vers l'API : aucun nom d'hôte de salon
    n'est en jeu, seul le membership dit de quel salon il s'agit.
    """
    login(api_client, salon_a.owner)

    reponse = api_client.get(
        reverse("availability"),
        {
            "service": str(salon_a.service.id),
            "date_from": prochain_jour_ouvre(salon_a),
            "date_to": prochain_jour_ouvre(salon_a),
        },
        HTTP_X_TENANT_ID=str(salon_a.tenant.id),
    )

    assert reponse.status_code == 200
    assert "slots" in reponse.data
    # Le salon est ouvert du lundi au samedi de 9 h à 18 h : il y a forcément
    # des créneaux. Une liste vide signalerait que le moteur n'a rien vu.
    assert len(reponse.data["slots"]) > 0


@pytest.mark.django_db
def test_une_prestation_retiree_du_catalogue_reste_deplacable(api_client, salon_a):
    """La seule différence assumée avec la route publique.

    Une cliente ne peut réserver qu'au catalogue. Mais un rendez-vous déjà
    pris sur une prestation retirée depuis doit rester déplaçable — sinon on
    bloque un engagement réel pour une décision de catalogue.
    """
    with as_tenant(salon_a.tenant):
        Service.objects.filter(pk=salon_a.service.pk).update(active=False)

    login(api_client, salon_a.owner)
    parametres = {
        "service": str(salon_a.service.id),
        "date_from": prochain_jour_ouvre(salon_a),
        "date_to": prochain_jour_ouvre(salon_a),
    }

    equipe = api_client.get(
        reverse("availability"), parametres, HTTP_X_TENANT_ID=str(salon_a.tenant.id)
    )
    assert equipe.status_code == 200
    assert len(equipe.data["slots"]) > 0

    # La route publique, elle, continue de refuser : rien ne change pour les
    # clientes.
    publique = api_client.get(
        reverse("public:public-availability"),
        parametres,
        HTTP_X_TENANT_HOST=salon_a.tenant.domains.first().hostname,
    )
    assert publique.status_code == 404


@pytest.mark.django_db
def test_les_disponibilites_de_l_equipe_exigent_une_session(api_client, salon_a):
    reponse = api_client.get(
        reverse("availability"),
        {
            "service": str(salon_a.service.id),
            "date_from": prochain_jour_ouvre(salon_a),
            "date_to": prochain_jour_ouvre(salon_a),
        },
    )
    assert reponse.status_code in (401, 403)


@pytest.mark.django_db
def test_on_ne_lit_pas_les_disponibilites_d_un_autre_salon(
    api_client, salon_a, salon_b
):
    """Le membership commande, pas l'en-tête.

    Réclamer le salon B avec un compte du salon A doit être refusé par le
    middleware, avant même d'atteindre la vue.
    """
    login(api_client, salon_a.owner)

    reponse = api_client.get(
        reverse("availability"),
        {
            "service": str(salon_b.service.id),
            "date_from": prochain_jour_ouvre(salon_b),
            "date_to": prochain_jour_ouvre(salon_b),
        },
        HTTP_X_TENANT_ID=str(salon_b.tenant.id),
    )

    assert reponse.status_code == 403


@pytest.mark.django_db
def test_une_prestataire_peut_lire_les_creneaux(api_client, salon_a):
    """Déplacer est réservé à la réception, mais lire les créneaux ne l'est pas.

    Une prestataire consulte son propre agenda ; lui fermer cette lecture
    rendrait le panneau inutilisable pour elle sans rien protéger — les
    horaires d'ouverture sont publics.
    """
    prestataire = UserFactory()
    MembershipFactory(
        tenant=salon_a.tenant, user=prestataire, role=Membership.Role.STAFF
    )
    login(api_client, prestataire)

    reponse = api_client.get(
        reverse("availability"),
        {
            "service": str(salon_a.service.id),
            "date_from": prochain_jour_ouvre(salon_a),
            "date_to": prochain_jour_ouvre(salon_a),
        },
        HTTP_X_TENANT_ID=str(salon_a.tenant.id),
    )

    assert reponse.status_code == 200


@pytest.mark.django_db
def test_la_route_publique_ne_repond_pas_a_un_appel_du_tableau_de_bord(
    api_client, salon_a
):
    """Le défaut d'origine, figé pour qu'on ne le refasse pas.

    C'est exactement ce que faisait le panneau de déplacement : appeler
    `public/availability` avec l'en-tête du tableau de bord. Cette route
    cherche le salon dans le nom d'hôte et ignore `X-Tenant-Id` — elle ne
    peut structurellement pas répondre depuis l'espace professionnel.
    """
    login(api_client, salon_a.owner)

    reponse = api_client.get(
        reverse("public:public-availability"),
        {
            "service": str(salon_a.service.id),
            "date_from": prochain_jour_ouvre(salon_a),
            "date_to": prochain_jour_ouvre(salon_a),
        },
        HTTP_X_TENANT_ID=str(salon_a.tenant.id),
    )

    assert reponse.status_code == 404
    assert reponse.json()["code"] == "tenant_not_found"
