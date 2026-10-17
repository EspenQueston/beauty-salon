"""Les devises dont les montants s'ecrivent en unites entieres.

Une seule liste pour toute la plateforme : parrainage, acomptes, conversions
de devise et paiements SASPAY lisaient chacun la leur, et elles divergeaient
(audit du 16/10/2026, C-07) — une remise pouvait alors produire « 5 900,50
GNF », que SASPAY refusait.

  - GNF, RWF, UGX, XAF, XOF : sans subdivision (ISO 4217, exposant 0) ;
  - CDF : deux decimales en theorie, aucune en pratique — personne ne paie
    50 centimes a Kinshasa, et aucun Mobile Money ne les debite.

Le frontend tient la meme liste (`apps/web/lib/format.ts`, `ZERO_DECIMAL`) ;
un test verifie que les deux concordent.
"""

from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

SANS_DECIMALES = frozenset({"CDF", "GNF", "RWF", "UGX", "XAF", "XOF"})


def sans_decimales(devise: str) -> bool:
    return (devise or "").upper() in SANS_DECIMALES


def pas(devise: str) -> Decimal:
    """Le plus petit montant payable : 1 sans centimes, 0,01 sinon."""
    return Decimal("1") if sans_decimales(devise) else Decimal("0.01")


def arrondir(montant: Decimal, devise: str, *, vers_le_bas: bool = False) -> Decimal:
    return montant.quantize(pas(devise), rounding=ROUND_DOWN if vers_le_bas else ROUND_HALF_UP)
