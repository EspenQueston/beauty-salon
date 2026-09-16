"""Achats faits pendant une reservation.

---------------------------------------------------------------------------
Pourquoi le stock bouge a la reservation et pas a la prestation
---------------------------------------------------------------------------

Parce qu'entre les deux il peut s'ecouler trois semaines. Attendre la
prestation pour decompter la derniere perruque, c'est la vendre deux fois -
et l'une des deux clientes l'apprend en arrivant, apres quatre heures de
trajet.

Une annulation rend le stock. Un rendez-vous honore ne le rend pas : la
marchandise est partie.
"""

from __future__ import annotations

from decimal import Decimal

from django.db.models import F

from .models import Product, Requirement


class StoreError(Exception):
    """Achat refuse. Le message est destine a la cliente, en francais."""


def resolve_items(service, raw_items) -> list[dict]:
    """Valide un panier et renvoie ses lignes, tarifees en base.

    Ni le prix ni le nom ne viennent de la requete : seuls les identifiants
    et les quantites circulent, tout le reste est relu. Sans cela, il
    suffirait de modifier le corps de la requete pour s'offrir une perruque a
    zero.

    Leve `StoreError` avec un message affichable si un article n'est pas
    proposé pour cette prestation, n'est plus vendu, ou n'est plus en stock
    en quantite suffisante.
    """
    if not raw_items:
        return []

    # Articles reellement proposes pour cette prestation. Le queryset est
    # borne au tenant courant par le manager ; on y ajoute la prestation,
    # sinon un article propose ailleurs dans le meme salon passerait.
    offered = {
        str(product.id): product
        for product in Product.objects.filter(
            active=True,
            offers__requirement__service=service,
        ).distinct()
    }

    lines: list[dict] = []
    wanted: dict[str, int] = {}

    for raw in raw_items:
        product_id = str(raw.get("product", "")).strip()
        try:
            quantity = int(raw.get("quantity", 1))
        except (TypeError, ValueError):
            raise StoreError("Quantité invalide.") from None

        if quantity < 1:
            continue
        if quantity > 20:
            raise StoreError("Quantité trop élevée pour une réservation.")

        product = offered.get(product_id)
        if product is None:
            raise StoreError(
                "Un des articles choisis n'est plus proposé pour cette prestation."
            )

        wanted[product_id] = wanted.get(product_id, 0) + quantity

    for product_id, quantity in wanted.items():
        product = offered[product_id]

        if product.stock is not None and product.stock < quantity:
            remaining = max(product.stock, 0)
            raise StoreError(
                f"« {product.name} » : il n'en reste que {remaining}."
                if remaining
                else f"« {product.name} » est en rupture."
            )

        lines.append(
            {
                "product": product,
                "quantity": quantity,
                "unit_price": product.price,
                "total": product.price * quantity,
            }
        )

    return lines


def items_total(lines) -> Decimal:
    return sum((line["total"] for line in lines), Decimal("0"))


def snapshot(lines) -> list[dict]:
    """Instantane des articles vendus, fige au moment de la vente.

    Renommer ou retarifer un article demain ne doit pas reecrire ce qui a ete
    vendu aujourd'hui.
    """
    return [
        {
            "product_id": str(line["product"].id),
            "name": line["product"].name,
            "quantity": line["quantity"],
            "unit_price": str(line["unit_price"]),
            "total": str(line["total"]),
        }
        for line in lines
    ]


def take_stock(lines) -> None:
    """Retire du stock ce qui vient d'etre vendu.

    `F()` plutot qu'une lecture suivie d'une ecriture : deux reservations
    simultanees sur le dernier article doivent decompter deux fois, pas une.
    La verification de disponibilite, elle, reste dans `resolve_items` - elle
    peut etre depassee par une course, et c'est assume : le salon voit alors
    un stock negatif, ce qui est un probleme visible plutot qu'une vente
    silencieusement perdue.
    """
    for line in lines:
        product = line["product"]
        if product.stock is None:
            continue
        Product.objects.filter(pk=product.pk).update(
            stock=F("stock") - line["quantity"]
        )


def give_back_stock(booking) -> None:
    """Rend au stock les articles d'une reservation annulee."""
    for row in booking.items_snapshot or []:
        product_id = row.get("product_id")
        quantity = row.get("quantity") or 0
        if not product_id or quantity <= 0:
            continue
        Product.objects.filter(pk=product_id, stock__isnull=False).update(
            stock=F("stock") + quantity
        )


def missing_mandatory(service, lines, declared_owned) -> list[Requirement]:
    """Exigences indispensables ni apportees ni achetees.

    `declared_owned` est la liste des exigences pour lesquelles la cliente a
    coche « je l'apporte ». On la croit sur parole : lui refuser sa propre
    perruque serait absurde. Ce qu'on refuse, c'est le silence - reserver
    quatre heures sans avoir dit ce qu'on fait des meches.
    """
    bought = {
        requirement_id
        for line in lines
        for requirement_id in line["product"].offers.values_list(
            "requirement_id", flat=True
        )
    }
    owned = {str(value) for value in declared_owned or []}

    return [
        requirement
        for requirement in Requirement.objects.filter(
            service=service, mandatory=True
        )
        if str(requirement.id) not in owned and requirement.id not in bought
    ]
