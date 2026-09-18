"""Changer la devise d'un salon, et convertir ce qui doit l'etre.

---------------------------------------------------------------------------
Ce qui est converti, et ce qui ne l'est surtout pas
---------------------------------------------------------------------------

**Converti : le catalogue.** Les prix que le salon affiche et facturera
demain - prestations, options, articles de boutique, forfaits de
deplacement, plancher d'acompte. Ce sont des intentions tarifaires : « je
vends cette pose 25 000 francs » devient « je la vends 293 yuans ».

**Jamais converti : l'histoire.** Les rendez-vous passes et les ecritures
comptables sont des constats, pas des intentions. Une pose encaissee 25 000
francs en mars a bien rapporte 25 000 francs ; la recalculer en yuans
reecrirait le livre de comptes d'un salon, ce qu'aucun logiciel n'a le droit
de faire.

C'est pour cela que `Booking.currency` et `Transaction.currency` existent :
chaque ligne garde son etiquette, et les ecrans affichent chacune dans la
devise ou elle a ete passee. Sans ces colonnes, cette fonctionnalite aurait
ete un falsificateur de comptabilite.

---------------------------------------------------------------------------
L'arrondi
---------------------------------------------------------------------------

Vers le haut, au pas de la devise d'arrivee - francs entiers pour le CFA,
centimes pour le yuan. Vers le haut et non vers le bas comme l'acompte : on
convertit un prix de vente, et rogner systematiquement quelques centimes sur
chaque ligne d'un catalogue reviendrait a baisser ses tarifs a son insu.

Un prix a zero reste a zero : « offert » n'a pas de taux de change.

---------------------------------------------------------------------------
Si le taux manque
---------------------------------------------------------------------------

Rien n'est touche. Voir `devises.TauxIndisponible` : convertir une grille
entiere a un taux devine est irrattrapable.
"""

from __future__ import annotations

import logging
from decimal import ROUND_UP, Decimal

from django.db import transaction

from apps.scheduling.services.deposit import WHOLE_UNIT_CURRENCIES

from .devises import taux

logger = logging.getLogger(__name__)


class DeviseRefusee(Exception):
    """Message destine a l'utilisatrice, en francais."""


def pas_de(devise: str) -> Decimal:
    """Plus petite unite de la devise : le franc CFA n'a pas de centimes."""
    return (
        Decimal("1") if devise.upper() in WHOLE_UNIT_CURRENCIES else Decimal("0.01")
    )


def convertir_montant(montant: Decimal, facteur: Decimal, vers: str) -> Decimal:
    """Un montant, converti puis arrondi au pas de la devise d'arrivee."""
    if not montant:
        return montant
    return (montant * facteur).quantize(pas_de(vers), rounding=ROUND_UP)


def apercu(tenant, vers: str) -> dict:
    """Ce que le basculement ferait, sans rien ecrire.

    L'ecran l'affiche avant de demander confirmation : un salon doit voir le
    taux retenu et ce que devient son prix phare avant d'accepter que tout
    son catalogue change.
    """
    vers = vers.upper()
    _verifier(tenant, vers)

    facteur = taux(tenant.currency, vers)
    lignes = _compter(tenant)

    return {
        "de": tenant.currency,
        "vers": vers,
        "taux": str(facteur),
        # L'inverse est le chiffre que les gens ont en tete : « un yuan vaut
        # 85 francs » se verifie, « un franc vaut 0,0117 yuan » non.
        "inverse": str((Decimal(1) / facteur).quantize(Decimal("0.0001"))),
        "lignes": lignes,
        "exemple": _exemple(tenant, facteur, vers),
    }


@transaction.atomic
def convertir(tenant, vers: str) -> dict:
    """Bascule la devise du salon et convertit son catalogue.

    Tout ou rien : la devise du salon et les prix changent dans la meme
    transaction. Un salon dont la devise aurait bascule sans ses prix
    afficherait 25 000 yuans pour une pose - quatre-vingt-cinq fois son
    tarif.
    """
    from apps.catalog.models import Service, ServiceOption
    from apps.salons.models import SalonProfile, TravelZone
    from apps.store.models import Product

    vers = vers.upper()
    _verifier(tenant, vers)

    depuis = tenant.currency
    facteur = taux(depuis, vers)

    converties = {
        "prestations": _convertir_colonne(Service, "price_amount", facteur, vers),
        "options": _convertir_colonne(ServiceOption, "price_delta", facteur, vers),
        "articles": _convertir_colonne(Product, "price", facteur, vers),
        "zones": _convertir_colonne(TravelZone, "fee_amount", facteur, vers),
        "plancher_acompte": _convertir_colonne(
            SalonProfile, "deposit_minimum", facteur, vers
        ),
    }

    tenant.currency = vers
    tenant.save(update_fields=["currency", "updated_at"])

    logger.info(
        "Salon %s : devise %s -> %s au taux %s, %s lignes converties.",
        tenant.slug,
        depuis,
        vers,
        facteur,
        sum(converties.values()),
    )

    return {"de": depuis, "vers": vers, "taux": str(facteur), "lignes": converties}


# ---------------------------------------------------------------------------
# Details
# ---------------------------------------------------------------------------


def _verifier(tenant, vers: str) -> None:
    from apps.tenants.models import Tenant

    connues = {code for code, _ in Tenant.Currency.choices}
    if vers not in connues:
        raise DeviseRefusee(f"Devise inconnue : {vers}.")
    if vers == tenant.currency:
        raise DeviseRefusee("Ce salon est déjà dans cette devise.")


def _convertir_colonne(modele, colonne: str, facteur: Decimal, vers: str) -> int:
    """Convertit une colonne de montants, ligne a ligne.

    Ligne a ligne et non par un `UPDATE` global : l'arrondi depend de la
    valeur, et PostgreSQL n'appliquerait pas le meme que Python sur les
    demis. Les volumes en jeu - quelques dizaines de lignes par salon - ne
    justifient pas de s'en priver.
    """
    touchees = 0
    for ligne in modele.objects.all():
        avant = getattr(ligne, colonne) or Decimal("0")
        if not avant:
            continue
        setattr(ligne, colonne, convertir_montant(avant, facteur, vers))
        ligne.save(update_fields=[colonne, "updated_at"])
        touchees += 1
    return touchees


def _compter(tenant) -> dict:
    from apps.catalog.models import Service, ServiceOption
    from apps.salons.models import TravelZone
    from apps.store.models import Product

    return {
        "prestations": Service.objects.exclude(price_amount=0).count(),
        "options": ServiceOption.objects.exclude(price_delta=0).count(),
        "articles": Product.objects.exclude(price=0).count(),
        "zones": TravelZone.objects.exclude(fee_amount=0).count(),
    }


def _exemple(tenant, facteur: Decimal, vers: str) -> dict | None:
    """La prestation la plus chere, avant et apres.

    Un exemple concret vaut mieux qu'un taux : c'est en voyant « 25 000 F
    devient 294 ¥ » qu'on repere une erreur de devise, pas en lisant
    « 0,0117 ».
    """
    from apps.catalog.models import Service

    phare = Service.objects.exclude(price_amount=0).order_by("-price_amount").first()
    if phare is None:
        return None
    return {
        "nom": phare.name,
        "avant": str(phare.price_amount),
        "apres": str(convertir_montant(phare.price_amount, facteur, vers)),
    }
