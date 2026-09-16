"""Combien demander a la reservation.

---------------------------------------------------------------------------
Le defaut de la version precedente
---------------------------------------------------------------------------

L'acompte etait un montant fixe par prestation, recopie tel quel. Il ne
suivait ni les options, ni la boutique, ni les frais de deplacement :

    prestation seule    450 → acompte 150   (33 %)
    + options            530 → acompte 150   (28 %)
    + boutique           690 → acompte 150   (22 %)

Autrement dit : **plus le panier grossissait, moins il protegeait** - alors
qu'un rendez-vous a 690 qui ne vient pas coute davantage qu'un a 450.

---------------------------------------------------------------------------
La regle
---------------------------------------------------------------------------

Elle distingue deux natures de montant, parce qu'une annulation ne leur fait
pas la meme chose.

**Le temps** - prestation et options. Un creneau libere peut etre repris ; le
salon ne perd pas tout. Il est donc reserve a un pourcentage, que le salon
choisit.

**La marchandise** - les articles de la boutique. Des meches achetees pour
une cliente precise ne se revendent pas toujours, et le salon les a deja
payees. Elles se reglent en entier.

**Le deplacement** n'entre pas dans l'acompte. Le trajet n'a pas eu lieu :
le facturer d'avance ferait payer un service non rendu, et se retournerait
contre le salon au premier litige.

    acompte = max(
        plancher de la prestation,
        (prestation + options) × taux
    ) + marchandise

---------------------------------------------------------------------------
Ce qui protege la cliente
---------------------------------------------------------------------------

Trois garde-fous, parce qu'un acompte mal borne se retourne contre celle qui
paie :

  1. **Jamais plus que le total.** Un arrondi ou un mauvais reglage ne peut
     pas produire un acompte superieur a ce qui est du.
  2. **Zero reste zero.** Un salon qui ne demande pas d'acompte n'en demande
     pas : le taux ne s'applique qu'a ceux qui en ont declare un.
  3. **Arrondi vers le bas**, a l'unite monetaire. Sur des monnaies sans
     centimes d'usage courant - XAF, CDF - un acompte a 137,4 n'a pas de
     sens, et arrondir vers le haut ferait payer plus que la regle annoncee.
"""

from __future__ import annotations

from decimal import ROUND_DOWN, Decimal

# Monnaies dont l'usage courant ignore les centimes. Un acompte de 137,40 XAF
# ne se paie pas : il n'existe pas de piece pour cela.
WHOLE_UNIT_CURRENCIES = {"XAF", "XOF", "CDF"}


def compute_deposit(
    *,
    service_amount: Decimal,
    options_amount: Decimal = Decimal("0"),
    items_amount: Decimal = Decimal("0"),
    travel_amount: Decimal = Decimal("0"),
    requires_deposit: bool = False,
    rate: int = 0,
    minimum: Decimal = Decimal("0"),
    covers_items: bool = True,
    currency: str = "XAF",
) -> Decimal:
    """Acompte demande pour un rendez-vous.

    `requires_deposit` vient de la prestation et ne dit que oui ou non.
    `rate` et `minimum` viennent de la fiche du salon et disent combien.

    Cette separation est le correctif d'une incoherence : la prestation
    portait un montant qui servait a la fois d'interrupteur et de plancher, si
    bien que le mini-site annoncait ce montant-la pendant que la reservation
    en reclamait un autre, calcule au pourcentage.
    """
    total = service_amount + options_amount + items_amount + travel_amount

    # Un salon qui ne demande rien ne demande rien.
    #
    # Le taux **module** les acomptes, il n'en cree pas. Une coupe de vingt
    # minutes doit rester libre quand le salon active 30 % sur son catalogue -
    # sinon activer un taux ferait apparaitre des demandes sur des prestations
    # ou personne n'en voulait, et la cliente les decouvrirait a la
    # reservation.
    if not requires_deposit:
        return Decimal("0")

    time_part = service_amount + options_amount
    from_rate = time_part * Decimal(rate) / Decimal(100) if rate > 0 else Decimal("0")

    # Le plancher porte sur le temps seulement : la marchandise s'ajoute
    # ensuite, sinon un plancher eleve la ferait payer deux fois.
    due = max(minimum, from_rate)

    if covers_items:
        due += items_amount

    due = _round_down(due, currency)

    # Jamais plus que ce qui est du : un acompte superieur au total serait
    # une avance, pas un acompte.
    return min(due, total)


def compute_for(booking_service, profile, *, options_amount, items_amount, travel_amount, currency):
    """Raccourci depuis les objets du domaine, pour les appelants."""
    return compute_deposit(
        service_amount=booking_service.price_amount,
        options_amount=options_amount,
        items_amount=items_amount,
        travel_amount=travel_amount,
        requires_deposit=bool(getattr(booking_service, "requires_deposit", False)),
        rate=getattr(profile, "deposit_rate", 0) or 0,
        minimum=getattr(profile, "deposit_minimum", None) or Decimal("0"),
        covers_items=getattr(profile, "deposit_covers_items", True),
        currency=currency,
    )


def _round_down(amount: Decimal, currency: str) -> Decimal:
    step = Decimal("1") if currency.upper() in WHOLE_UNIT_CURRENCIES else Decimal("0.01")
    return amount.quantize(step, rounding=ROUND_DOWN)


def explain(
    *,
    service_amount: Decimal,
    options_amount: Decimal,
    items_amount: Decimal,
    minimum: Decimal,
    rate: int,
    covers_items: bool,
) -> list[dict]:
    """Le detail, ligne par ligne, pour l'afficher a la cliente.

    Un acompte dont on ne comprend pas la provenance se conteste. Le detail
    coute trois lignes et evite l'appel telephonique.
    """
    lines: list[dict] = []
    time_part = service_amount + options_amount
    from_rate = time_part * Decimal(rate) / Decimal(100) if rate > 0 else Decimal("0")

    if rate > 0 and from_rate >= minimum:
        lines.append(
            {
                "label": f"{rate} % de la prestation",
                "amount": str(from_rate),
            }
        )
    elif minimum > 0:
        lines.append({"label": "Acompte minimum du salon", "amount": str(minimum)})

    if covers_items and items_amount > 0:
        lines.append({"label": "Fournitures, réglées en entier", "amount": str(items_amount)})

    return lines
