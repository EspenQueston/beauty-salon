"""Offre Pro : l'historique des conversations de l'assistant, et n8n.

Ce que ces tests tiennent :

  - l'adresse du webhook ne se devine pas, et n'est montree qu'une fois ;
  - un message rejoue par n8n n'apparait qu'une fois ;
  - sans Pro, le webhook se tait ; un salon ne lit jamais le fil d'un autre ;
  - les reponses de l'assistant WhatsApp entrent dans le meme historique.
"""

import json
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.models import Membership
from apps.assistants import historique, whatsapp
from apps.assistants.models import AssistantReglages, ConversationAssistant, MessageAssistant
from conftest import as_tenant
from tests.test_abonnements import ADMIN, medias_temporaires, offres
from tests.test_assistants_pro import (
    evolution_configuree,
    fausse_ia,
    instance_connectee,
    membre,
    salon_pro,
)
from tests.test_offres_pro import au_plan, pro

FIXTURES_PARTAGEES = (
    medias_temporaires,
    offres,
    pro,
    salon_pro,
    fausse_ia,
    evolution_configuree,
    instance_connectee,
)


def _brancher(api_client, salon):
    api_client.force_login(salon.owner)
    reponse = api_client.post("/api/v1/assistant/n8n")
    assert reponse.status_code == 201, reponse.json()
    return reponse.json()["adresse"]


def _chemin(adresse: str) -> str:
    return adresse[adresse.index("/api/v1/") :]


# ---------------------------------------------------------------------------
# Le branchement
# ---------------------------------------------------------------------------


@ADMIN
def test_l_adresse_n_est_montree_qu_une_fois_et_seule_son_empreinte_est_gardee(
    api_client, salon_pro
):
    adresse = _brancher(api_client, salon_pro)
    jeton = adresse.rsplit("/", 1)[-1]

    etat = api_client.get("/api/v1/assistant/n8n").json()
    with as_tenant(salon_pro.tenant):
        reglages = AssistantReglages.objects.get()

    assert "/api/v1/webhooks/n8n/" in adresse
    assert etat["relie"] is True and "adresse" not in etat
    assert jeton not in json.dumps(etat)
    assert reglages.n8n_empreinte == historique.empreinte(jeton)


@ADMIN
def test_regenerer_l_adresse_eteint_l_ancienne(api_client, salon_pro):
    ancienne = _chemin(_brancher(api_client, salon_pro))
    nouvelle = _chemin(_brancher(api_client, salon_pro))
    message = {"contact": "+242061234567", "message": "Bonjour"}

    assert api_client.post(ancienne, message, format="json").status_code == 404
    assert api_client.post(nouvelle, message, format="json").status_code == 200


@ADMIN
def test_seul_le_proprietaire_branche_et_debranche(api_client, salon_pro):
    gerante = membre(salon_pro, Membership.Role.MANAGER)
    api_client.force_login(gerante)

    assert api_client.get("/api/v1/assistant/n8n").status_code == 200
    assert api_client.post("/api/v1/assistant/n8n").status_code == 403
    assert api_client.delete("/api/v1/assistant/n8n").status_code == 403


@ADMIN
def test_le_numero_est_normalise_ou_refuse(api_client, salon_pro):
    api_client.force_login(salon_pro.owner)

    bon = api_client.patch("/api/v1/assistant/n8n", {"numero": "+242 06 123 45 67"}, format="json")
    mauvais = api_client.patch("/api/v1/assistant/n8n", {"numero": "abc"}, format="json")

    assert bon.status_code == 200 and bon.json()["numero"].startswith("+242")
    assert mauvais.status_code == 400


@ADMIN
def test_standard_ne_branche_pas_n8n(api_client, salon_a, pro):
    from tests.test_abonnements import abonnement_de

    abonnement_de(salon_a)
    api_client.force_login(salon_a.owner)

    assert api_client.post("/api/v1/assistant/n8n").status_code == 403
    assert api_client.get("/api/v1/assistant/conversations").status_code == 403


# ---------------------------------------------------------------------------
# Le webhook
# ---------------------------------------------------------------------------


@ADMIN
def test_un_jeton_faux_ou_une_cle_inconnue_recoivent_le_meme_404(api_client, salon_pro):
    chemin = _chemin(_brancher(api_client, salon_pro))
    api_client.logout()
    cle = chemin.split("/")[-2]
    message = {"contact": "+242061234567", "message": "Bonjour"}

    assert (
        api_client.post(f"/api/v1/webhooks/n8n/{cle}/faux", message, format="json").status_code
        == 404
    )
    assert (
        api_client.post("/api/v1/webhooks/n8n/inconnue/faux", message, format="json").status_code
        == 404
    )


@ADMIN
def test_un_lot_s_ecrit_et_un_message_rejoue_n_apparait_qu_une_fois(api_client, salon_pro):
    chemin = _chemin(_brancher(api_client, salon_pro))
    api_client.logout()
    lot = {
        "messages": [
            {
                "contact": "242061234567@s.whatsapp.net",
                "nom": "Awa",
                "direction": "in",
                "message": "Vous êtes ouverts demain ?",
                "timestamp": 1789999000,  # 13:56:40 UTC, avant la reponse
                "id": "wamid.1",
            },
            {
                "contact": "+242 06 123 45 67",
                "role": "assistant",
                "text": "Oui, de 9 h à 19 h.",
                "horodatage": "2026-09-21T14:00:05Z",
                "id": "wamid.2",
            },
        ]
    }

    premier = api_client.post(chemin, lot, format="json")
    rejoue = api_client.post(chemin, lot, format="json")

    assert premier.json() == {"ok": True, "recus": 2, "doublons": 0}
    assert rejoue.json() == {"ok": True, "recus": 0, "doublons": 2}
    with as_tenant(salon_pro.tenant):
        fil = ConversationAssistant.objects.get()
        directions = list(fil.messages.values_list("direction", flat=True))
    assert fil.contact == "+242061234567" and fil.nom == "Awa"
    assert fil.nombre_messages == 2 and fil.dernier_apercu == "Oui, de 9 h à 19 h."
    assert directions == ["entrant", "sortant"]


@ADMIN
@pytest.mark.parametrize(
    "charge",
    [
        {"message": "Sans contact"},
        {"contact": "+242061234567"},
        {"contact": "+242061234567", "message": "x", "direction": "ailleurs"},
        {"contact": "+242061234567", "message": "x", "horodatage": "hier"},
        {"messages": []},
        {"messages": [{"contact": "+1", "message": "x"}] * 51},
    ],
)
def test_un_message_invalide_est_refuse(api_client, salon_pro, charge):
    chemin = _chemin(_brancher(api_client, salon_pro))

    reponse = api_client.post(chemin, charge, format="json")

    assert reponse.status_code == 400
    assert reponse.json()["code"] == "message_invalide"


@ADMIN
def test_sans_pro_le_webhook_se_tait(api_client, salon_pro):
    chemin = _chemin(_brancher(api_client, salon_pro))
    au_plan(salon_pro, "monthly", fin=timezone.now() + timedelta(days=20))

    reponse = api_client.post(
        chemin, {"contact": "+242061234567", "message": "Bonjour"}, format="json"
    )

    assert reponse.status_code == 404


# ---------------------------------------------------------------------------
# La lecture de l'historique
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_le_salon_lit_ses_fils_et_jamais_ceux_d_un_autre(api_client, salon_pro, salon_b):
    with as_tenant(salon_pro.tenant):
        historique.consigner(
            salon_pro.tenant.id,
            canal="n8n",
            contact="+242061234567",
            nom="Awa",
            direction="entrant",
            texte="Bonjour",
        )
        mien = ConversationAssistant.objects.get()
    with as_tenant(salon_b.tenant):
        historique.consigner(
            salon_b.tenant.id,
            canal="n8n",
            contact="+242069999999",
            direction="entrant",
            texte="Chez l'autre salon",
        )
        autre = ConversationAssistant.objects.get()
    api_client.force_login(salon_pro.owner)

    liste = api_client.get("/api/v1/assistant/conversations").json()["conversations"]
    trouve = api_client.get("/api/v1/assistant/conversations?q=awa").json()["conversations"]
    fil = api_client.get(f"/api/v1/assistant/conversations/{mien.id}")
    etranger = api_client.get(f"/api/v1/assistant/conversations/{autre.id}")

    assert [c["id"] for c in liste] == [str(mien.id)]
    assert len(trouve) == 1
    assert fil.status_code == 200 and fil.json()["messages"][0]["texte"] == "Bonjour"
    assert etranger.status_code == 404


@pytest.mark.django_db
def test_l_equipe_ne_lit_pas_les_conversations(api_client, salon_pro):
    api_client.force_login(membre(salon_pro, Membership.Role.STAFF))

    assert api_client.get("/api/v1/assistant/conversations").status_code == 403


@pytest.mark.django_db
def test_les_echanges_whatsapp_entrent_dans_l_historique(
    salon_pro, instance_connectee, fausse_ia, evolution_configuree
):
    jid = "242060000001@s.whatsapp.net"
    with as_tenant(salon_pro.tenant):
        whatsapp.repondre(salon_pro.tenant, jid, "Bonjour")
        fil = ConversationAssistant.objects.get()
        messages = list(MessageAssistant.objects.values_list("direction", "texte"))

    assert fil.canal == "whatsapp" and fil.contact == "+242060000001"
    assert messages == [("entrant", "Bonjour"), ("sortant", "Réponse de test.")]
