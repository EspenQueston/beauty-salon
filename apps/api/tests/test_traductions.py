"""Le contenu d'un salon, servi dans la langue demandée.

---------------------------------------------------------------------------
Ce qui est réellement en jeu
---------------------------------------------------------------------------

Le catalogue d'un salon est écrit par la gérante, en français. Une cliente
anglophone qui ouvre le mini-site doit le lire en anglais — sans que la gérante
ait rien fait, et sans que la page ralentisse.

Cinq affirmations, et ce fichier ne teste qu'elles :

  1. **Le français reste le repli.** Pas de traduction, service en panne,
     texte modifié il y a trente secondes : la page rend le texte français.
     Jamais un blanc, jamais une clé. Une case vide se lit comme une panne.

  2. **Une correction humaine n'est jamais écrasée.** Une gérante qui reprend
     une traduction maladroite doit la retrouver le lendemain. Sinon elle
     recommence, conclut que ça ne marche pas, et n'y revient plus.

  3. **Une source modifiée périme sa traduction.** Renommer « Pose de gel » en
     « Pose de gel semi-permanent » doit refaire l'anglais. Sans cela, le
     mini-site anglais affiche indéfiniment l'ancien nom, sans que rien ne le
     signale.

  4. **Le rattrapage est idempotent.** On doit pouvoir le relancer sans
     réfléchir : le second passage ne refait que ce qui a changé.

  5. **Les noms propres ne passent pas par la traduction.** Le nom d'une
     prestataire, d'un quartier, d'une ville n'est pas du texte à traduire.

Aucun de ces tests n'appelle l'API : un traducteur factice tient le rôle. Une
suite qui dépend d'un service extérieur échoue le jour où il tombe, pour une
raison qui n'a rien à voir avec le code.
"""

from __future__ import annotations

import pytest

from apps.catalog.models import Service, ServiceCategory
from apps.staff.models import StaffMember
from apps.translations.models import Origin, Translation, empreinte
from apps.translations.registry import TRADUISIBLES
from apps.translations.services import (
    a_traduire,
    poser_traducteur,
    table_du_salon,
    traduire,
)
from apps.translations.traducteur import Demande, Traducteur, TraducteurFactice, valider
from conftest import as_tenant, salon_host


@pytest.fixture(autouse=True)
def traducteur_factice():
    """Aucun appel réseau, et un résultat qu'on peut affirmer."""
    ancien = poser_traducteur(TraducteurFactice())
    yield
    poser_traducteur(ancien)


@pytest.fixture
def catalogue(tenant_a, salon_a):
    with as_tenant(tenant_a):
        categorie = ServiceCategory.objects.create(
            tenant=tenant_a, name="Tresses et nattes", position=1
        )
        service = Service.objects.create(
            tenant=tenant_a,
            category=categorie,
            name="Pose de gel",
            description="Adaptée à votre visage.",
            price_amount="25000",
            duration_minutes=90,
        )
    return categorie, service


# ---------------------------------------------------------------- 1. le repli


@pytest.mark.django_db
def test_sans_traduction_le_francais_est_servi(tenant_a, catalogue):
    _, service = catalogue
    with as_tenant(tenant_a):
        table = table_du_salon(tenant_a.id, "en")
    assert table == {}, "aucune traduction n'a encore été faite"
    assert service.name == "Pose de gel"


@pytest.mark.django_db
def test_un_traducteur_en_panne_ne_casse_rien(tenant_a, catalogue):
    """Un service indisponible laisse le champ en français, sans lever."""

    class EnPanne(Traducteur):
        def disponible(self) -> bool:
            return True

        def traduire(self, demande: Demande) -> dict[str, str]:
            return {}

    _, service = catalogue
    ancien = poser_traducteur(EnPanne())
    try:
        with as_tenant(tenant_a):
            assert traduire(service, "en") == 0
            assert table_du_salon(tenant_a.id, "en") == {}
    finally:
        poser_traducteur(ancien)


@pytest.mark.django_db
def test_sans_cle_rien_n_est_appele(settings):
    """Pas de clé, pas d'appel : `disponible()` ferme la porte en amont."""
    settings.OPENAI_API_KEY = ""
    assert Traducteur().disponible() is False
    assert Traducteur().traduire(Demande(cible="en", textes={"a": "Bonjour"})) == {}


# --------------------------------------------------- 2. la correction humaine


@pytest.mark.django_db
def test_une_correction_du_salon_survit_au_rattrapage(tenant_a, catalogue):
    _, service = catalogue
    with as_tenant(tenant_a):
        traduire(service, "en")
        traduction = Translation.objects.get(field="name", language="en")
        traduction.text = "Gel nails"
        traduction.origin = Origin.SALON
        traduction.save()

        # Un second passage ne doit pas la reprendre.
        assert a_traduire(service, "en") == {}
        traduire(service, "en")
        assert Translation.objects.get(field="name", language="en").text == "Gel nails"


# ------------------------------------------------------- 3. la source modifiée


@pytest.mark.django_db
def test_modifier_le_francais_perime_la_traduction(tenant_a, catalogue):
    _, service = catalogue
    with as_tenant(tenant_a):
        traduire(service, "en")
        assert a_traduire(service, "en") == {}, "rien à refaire juste après"

        service.name = "Pose de gel semi-permanent"
        service.save()

        manquants = a_traduire(service, "en")
        assert manquants == {"name": "Pose de gel semi-permanent"}

        traduire(service, "en")
        traduction = Translation.objects.get(field="name", language="en")
        assert traduction.text == "[en] Pose de gel semi-permanent"
        assert traduction.source_digest == empreinte("Pose de gel semi-permanent")


# ------------------------------------------------------- 4. le rattrapage


@pytest.mark.django_db
def test_le_second_passage_ne_refait_rien(tenant_a, catalogue):
    _, service = catalogue
    with as_tenant(tenant_a):
        premier = traduire(service, "en")
        second = traduire(service, "en")
    assert premier == 2, "le nom et la description"
    assert second == 0, "rien n'a changé entre les deux"


@pytest.mark.django_db
def test_un_champ_vide_n_est_pas_traduit(tenant_a, salon_a):
    """Un texte vide n'a rien à dire dans aucune langue."""
    with as_tenant(tenant_a):
        categorie = ServiceCategory.objects.create(
            tenant=tenant_a, name="Ongles", position=1
        )
        service = Service.objects.create(
            tenant=tenant_a,
            category=categorie,
            name="Manucure",
            description="",
            price_amount="8000",
            duration_minutes=45,
        )
        assert set(a_traduire(service, "en")) == {"name"}


# ------------------------------------------------------ 5. les noms propres


@pytest.mark.django_db
def test_le_nom_d_une_prestataire_ne_se_traduit_pas(tenant_a, salon_a):
    with as_tenant(tenant_a):
        membre = StaffMember.objects.create(
            tenant=tenant_a,
            name="Grâce Mabiala",
            specialty="Tresses et soin du cheveu",
        )
        manquants = a_traduire(membre, "en")

    assert "name" not in manquants, "un nom de personne n'est pas du texte"
    assert manquants["specialty"] == "Tresses et soin du cheveu"


def test_le_registre_exclut_les_lieux():
    """Ville, adresse et quartiers ne figurent pas au registre.

    Un quartier traduit devient introuvable sur une carte, et une cliente qui
    cherche « Poto-Poto » ne trouve pas « Mud Village ».
    """
    champs_salon = TRADUISIBLES["salons.salonprofile"]
    assert "city" not in champs_salon
    assert "address" not in champs_salon
    assert "service_area" not in champs_salon
    assert "travel.travelzone" not in TRADUISIBLES
    assert "salons.travelzone" not in TRADUISIBLES


# --------------------------------------------- la forme de la réponse du modèle


@pytest.mark.parametrize(
    ("brut", "attendu"),
    [
        ('{"name": "Gel nails"}', {"name": "Gel nails"}),
        # Une enveloppe ``` est tolérée : plusieurs modèles en ajoutent une.
        ('```json\n{"name": "Gel nails"}\n```', {"name": "Gel nails"}),
        # Une phrase autour de l'objet aussi.
        ('Voici :\n{"name": "Gel nails"}\nVoilà.', {"name": "Gel nails"}),
        # Une clé qu'on n'a pas demandée est écartée.
        ('{"name": "Gel nails", "inconnu": "x"}', {"name": "Gel nails"}),
        # Une valeur vide est écartée : perdre le texte est pire que ne pas
        # le traduire.
        ('{"name": "   "}', {}),
        # Une valeur qui n'est pas du texte aussi.
        ('{"name": 12}', {}),
        ("pas du json du tout", {}),
        ("[]", {}),
    ],
)
def test_la_reponse_du_modele_est_verifiee(brut, attendu):
    assert valider(brut, {"name": "Pose de gel"}) == attendu

# ------------------------------------------- l ecran, de bout en bout


def _prestation(reponse: dict, parmi: str) -> dict:
    """La prestation dont le nom contient `parmi`, quelle que soit sa place.

    Le salon d essai porte deja un catalogue : chercher par position rendrait
    le test dependant d un ordre que personne ne garantit.
    """
    for categorie in reponse["categories"]:
        for prestation in categorie["services"]:
            if parmi in prestation["name"]:
                return prestation
    raise AssertionError(f"prestation introuvable : {parmi}")


@pytest.mark.django_db
def test_l_api_publique_sert_la_langue_demandee(api_client, tenant_a, catalogue):
    """Le parametre de langue remplace les champs traduits, et eux seuls."""
    _, service = catalogue
    with as_tenant(tenant_a):
        traduire(service, "en")

    entetes = {"HTTP_X_TENANT_HOST": salon_host(tenant_a.slug)}

    francais = api_client.get("/api/v1/public/salon", **entetes).json()
    assert _prestation(francais, "Pose de gel")["name"] == "Pose de gel"

    anglais = api_client.get("/api/v1/public/salon", {"lang": "en"}, **entetes).json()
    traduite = _prestation(anglais, "Pose de gel")
    assert traduite["name"] == "[en] Pose de gel"
    assert traduite["description"] == "[en] Adaptée à votre visage."

    # Ce qui ne se traduit pas ne bouge pas.
    assert anglais["name"] == francais["name"], "le nom du salon est une marque"
    assert anglais["currency"] == francais["currency"]


@pytest.mark.django_db
def test_une_langue_inconnue_rend_le_francais(api_client, tenant_a, catalogue):
    """Une langue non servie n est pas une erreur : elle rend la source."""
    _, service = catalogue
    with as_tenant(tenant_a):
        traduire(service, "en")

    reponse = api_client.get(
        "/api/v1/public/salon",
        {"lang": "xx"},
        HTTP_X_TENANT_HOST=salon_host(tenant_a.slug),
    ).json()
    assert _prestation(reponse, "Pose de gel")["name"] == "Pose de gel"


@pytest.mark.django_db
def test_accept_language_sert_de_repli(api_client, tenant_a, catalogue):
    """Sans parametre de langue, l en-tete du client decide."""
    _, service = catalogue
    with as_tenant(tenant_a):
        traduire(service, "en")

    reponse = api_client.get(
        "/api/v1/public/salon",
        HTTP_X_TENANT_HOST=salon_host(tenant_a.slug),
        HTTP_ACCEPT_LANGUAGE="en-GB,en;q=0.9",
    ).json()
    assert _prestation(reponse, "Pose de gel")["name"] == "[en] Pose de gel"
