"""Les paiements encaisses mais non appliques : les signaler, sans les perdre.

Audit du 16/10/2026 (C-02, C-03, C-11). Avant, un succes du prestataire
arrive trop tard, ou un montant qui ne concordait pas, finissait dans un
journal technique : le salon avait paye, l'abonnement n'avait pas suivi, et
personne ne le savait.

Desormais chaque cas ouvre un dossier `PaiementARegulariser` dans
l'administration, et l'equipe plateforme est prevenue dans sa cloche. Rien
n'est applique automatiquement : c'est une decision (prolonger a la main,
rembourser chez le prestataire).

A appeler hors de toute transaction qui va etre annulee : le dossier doit
survivre au refus qu'il documente.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from django.db import IntegrityError, transaction

logger = logging.getLogger(__name__)

MOTIFS = {
    "succes_apres_expiration": "Paiement réussi chez le prestataire après l'expiration locale",
    "montant_invalide": "Montant ou devise différents de la demande",
    "association_invalide": "Transaction non associée à ce paiement",
    "deja_traitee": "Demande déjà traitée (refusée ou approuvée) au moment du succès",
    "paye_non_applique": "Rapprochement : payé chez le prestataire, non appliqué ici",
    "applique_sans_paiement": "Rapprochement : appliqué ici, non payé chez le prestataire",
}


def signaler(
    prestataire: str,
    intention,
    motif: str,
    *,
    transaction_id: str = "",
    montant=None,
    devise: str = "",
    detail: str = "",
) -> bool:
    """Ouvre le dossier (une fois par intention et motif). Rend True s'il est neuf."""
    from apps.accounts import journal
    from apps.audit.models import AuditLog

    from .models import PaiementARegulariser

    try:
        montant = Decimal(str(montant)) if montant not in (None, "") else None
    except Exception:  # noqa: BLE001 - un montant illisible ne bloque pas le dossier
        montant = None
    try:
        with transaction.atomic():
            dossier, neuf = PaiementARegulariser.objects.get_or_create(
                prestataire=prestataire,
                intention=str(intention.pk),
                motif=motif,
                defaults={
                    "tenant_id": intention.tenant_id,
                    "demande_id": intention.demande_id,
                    "transaction_id": (transaction_id or "")[:100],
                    "montant": montant,
                    "devise": (devise or "")[:3],
                    "detail": detail[:2000],
                },
            )
            if neuf:
                AuditLog.objects.create(
                    tenant_id=intention.tenant_id,
                    action=AuditLog.Action.PAYMENT_TO_RECONCILE,
                    resource_type="paiement_a_regulariser",
                    resource_id=str(dossier.pk),
                    metadata={
                        "prestataire": prestataire,
                        "motif": motif,
                        "intention": str(intention.pk),
                        "transaction": transaction_id,
                        "montant": str(montant) if montant is not None else "",
                        "devise": devise,
                    },
                )
    except IntegrityError:
        return False
    except Exception:  # noqa: BLE001 - signaler ne doit jamais faire echouer l'appelant
        logger.exception("Paiement à régulariser non enregistré (%s, %s).", prestataire, motif)
        return False
    if neuf:
        journal.alerter_plateforme(
            f"Paiement {prestataire.upper()} à régulariser",
            f"{MOTIFS.get(motif, motif)} — {montant or ''} {devise} — "
            f"transaction {transaction_id or '?'}.",
        )
    return neuf
