"""Localized public receipt labels without altering the immutable booking snapshot.

Snapshots are the salon's historical record. Only the response shown to the
customer is translated, and only while its source name still matches the
catalogue item that produced it.
"""

from __future__ import annotations

from apps.catalog.models import ServiceOption
from apps.store.models import Product

from .services import table_du_salon


def public_booking_labels(booking, language: str) -> dict:
    result = {
        "service_name": booking.service_name,
        "options_snapshot": booking.options_snapshot,
        "items_snapshot": booking.items_snapshot,
    }
    if language != "en":
        return result

    table = table_du_salon(booking.tenant_id, language)
    if not table:
        return result

    def translated(obj, field: str, source: str) -> str:
        if getattr(obj, field) != source:
            return source
        return table.get((obj._meta.label_lower, str(obj.pk), field), source)

    result["service_name"] = translated(
        booking.service, "name", booking.service_name
    )

    if booking.options_snapshot:
        names = {item["name"] for item in booking.options_snapshot}
        options = {
            option.name: option
            for option in ServiceOption.objects.filter(
                tenant_id=booking.tenant_id, service_id=booking.service_id, name__in=names
            )
        }
        result["options_snapshot"] = [
            {
                **item,
                "name": translated(options[item["name"]], "name", item["name"])
                if item["name"] in options
                else item["name"],
            }
            for item in booking.options_snapshot
        ]

    if booking.items_snapshot:
        names = {item["name"] for item in booking.items_snapshot}
        products = {
            product.name: product
            for product in Product.objects.filter(
                tenant_id=booking.tenant_id, name__in=names
            )
        }
        result["items_snapshot"] = [
            {
                **item,
                "name": translated(products[item["name"]], "name", item["name"])
                if item["name"] in products
                else item["name"],
            }
            for item in booking.items_snapshot
        ]

    return result
