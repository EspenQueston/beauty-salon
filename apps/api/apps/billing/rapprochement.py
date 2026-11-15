"""Rapprochement quotidien : ce que disent les prestataires, ce qui est applique ici.

Audit du 16/10/2026, C-11. Sans lui, un paiement encaisse mais non applique
(ou l'inverse) restait invisible. Chaque jour, pour les paiements des
derniers jours deja clos chez nous, le prestataire est interroge par les
memes verifications serveur que la confirmation — les points documentes,
rien de devine :

  - SASPAY : `GET /checkout-sessions/{id}/status/` ;
  - KKIAPAY : `POST /api/v1/transactions/status`.

Deux ecarts ouvrent un dossier « a regulariser » (voir regularisation.py) :

  - **paye_non_applique** : expire ici, mais regle chez le prestataire ;
  - **applique_sans_paiement** : confirme ici, mais pas regle chez lui.

Les paiements encore en attente ne sont pas concernes : l'entretien des dix
minutes s'en occupe. Lecture seule chez le prestataire ; rien n'est applique
ni annule automatiquement.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from . import kkiapay, regularisation, saspay
from .models import KkiapayIntent, SaspayIntent
from .services import PaiementRefuse

logger = logging.getLogger(__name__)

JOURS = 7
PLAFOND = 300


def _saspay(depuis) -> dict:
    compte = {"verifies": 0, "ecarts": 0, "injoignable": False}
    if not saspay.disponible():
        return compte
    intentions = (
        SaspayIntent.objects.filter(
            sandbox=settings.SASPAY_SANDBOX,
            statut__in=("expire", "confirme"),
            updated_at__gte=depuis,
        )
        .exclude(session_id="")
        .order_by("-updated_at")[:PLAFOND]
    )
    for i in intentions:
        try:
            etat = saspay._verifier(f"/checkout-sessions/{i.session_id}/status/", i.sandbox)
        except PaiementRefuse:
            compte["injoignable"] = True
            break
        compte["verifies"] += 1
        paye = etat.get("status") == "PAID" and etat.get("transaction_status") == "SUCCESS"
        motif = None
        if i.statut == "expire" and paye:
            motif = "paye_non_applique"
        elif i.statut == "confirme" and not paye:
            motif = "applique_sans_paiement"
        if motif and regularisation.signaler(
            "saspay",
            i,
            motif,
            transaction_id=str(etat.get("transaction_id") or i.transaction_id or ""),
            detail=f"Statut SASPAY : {etat.get('status')} / {etat.get('transaction_status')}.",
        ):
            compte["ecarts"] += 1
    return compte


def _kkiapay(depuis) -> dict:
    compte = {"verifies": 0, "ecarts": 0, "injoignable": False}
    if not kkiapay.disponible():
        return compte
    intentions = KkiapayIntent.objects.filter(
        sandbox=settings.KKIAPAY_SANDBOX,
        statut__in=("expire", "confirme"),
        updated_at__gte=depuis,
    ).order_by("-updated_at")[:PLAFOND]
    for i in intentions:
        transaction_id = i.transaction_id or i.transaction_annoncee
        if not transaction_id:
            continue  # rien d'annonce : rien a demander a KKIAPAY
        try:
            resultat = kkiapay.verifier_transaction(transaction_id, i.sandbox)
        except PaiementRefuse:
            compte["injoignable"] = True
            break
        compte["verifies"] += 1
        paye = resultat.get("status") == "SUCCESS" and resultat.get("partnerId") == str(i.pk)
        motif = None
        if i.statut == "expire" and paye:
            motif = "paye_non_applique"
        elif i.statut == "confirme" and not paye:
            motif = "applique_sans_paiement"
        if motif and regularisation.signaler(
            "kkiapay",
            i,
            motif,
            transaction_id=transaction_id,
            montant=resultat.get("amount"),
            devise=str(resultat.get("currency") or "XOF"),
            detail=f"Statut KKIAPAY : {resultat.get('status')}.",
        ):
            compte["ecarts"] += 1
    return compte


def rapprocher(jours: int = JOURS) -> dict:
    depuis = timezone.now() - timedelta(days=jours)
    resultat = {"saspay": _saspay(depuis), "kkiapay": _kkiapay(depuis)}
    logger.info("Rapprochement des paiements : %s", resultat)
    return resultat
