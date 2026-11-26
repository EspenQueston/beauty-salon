"""Une seule liste de devises sans centimes (audit du 16/10/2026, C-07).

Parrainage, acomptes, conversions et SASPAY lisaient chacun la leur, et elles
divergeaient : une remise pouvait produire « 5 900,50 GNF », que SASPAY
refusait. Ces tests tiennent l'unicite, et l'accord avec le frontend.
"""

import re
from decimal import Decimal
from pathlib import Path

import pytest

from apps.billing import saspay
from apps.billing.models import DEVISES_ABONNEMENT
from apps.common.devises import SANS_DECIMALES, arrondir, pas
from apps.parrainage import services as parrainage
from apps.scheduling.services import deposit
from apps.tenants.models import Tenant
from apps.tenants.services import conversion

# Exposant 0 dans ISO 4217, parmi les devises qu'on pourrait croiser ici.
ISO_SANS_SUBDIVISION = {"BIF", "DJF", "GNF", "JPY", "KMF", "KRW", "RWF", "UGX", "XAF", "XOF"}


def test_chaque_devise_sans_subdivision_de_la_plateforme_est_dans_la_liste():
    plateforme = {code for code, _ in DEVISES_ABONNEMENT} | set(Tenant.Currency.values)
    assert (plateforme & ISO_SANS_SUBDIVISION) <= SANS_DECIMALES


@pytest.mark.parametrize("devise", sorted(SANS_DECIMALES))
def test_tous_les_modules_arrondissent_pareil(devise):
    assert pas(devise) == Decimal("1")
    assert parrainage.arrondir(Decimal("5900.50"), devise) == Decimal("5901")
    assert deposit._round_down(Decimal("137.90"), devise) == Decimal("137")
    assert conversion.pas_de(devise) == Decimal("1")
    assert devise in saspay.SANS_DECIMALES


def test_une_devise_a_centimes_garde_ses_centimes():
    assert arrondir(Decimal("14.755"), "USD") == Decimal("14.76")
    assert parrainage.arrondir(Decimal("14.755"), "USD") == Decimal("14.76")
    assert deposit._round_down(Decimal("14.759"), "USD") == Decimal("14.75")


def test_le_frontend_tient_la_meme_liste():
    source = (Path(__file__).resolve().parents[2] / "web" / "lib" / "format.ts").read_text(
        encoding="utf-8"
    )
    trouve = re.search(r"ZERO_DECIMAL = new Set\(\[([^\]]+)\]\)", source)
    assert trouve, "ZERO_DECIMAL introuvable dans apps/web/lib/format.ts"
    web = set(re.findall(r'"([A-Z]{3})"', trouve.group(1)))
    assert SANS_DECIMALES <= web
