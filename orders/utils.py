from decimal import Decimal, ROUND_HALF_UP
from django.db.models import Q
from inventory.models import CommodityRate
import uuid
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

DEC2 = Decimal("0.01")


def quantize_money(value: Decimal) -> Decimal:
    return value.quantize(DEC2, rounding=ROUND_HALF_UP)


def get_latest_rate_for_variant(variant):
    """
    Return the latest active CommodityRate for a commodity variant (or None).
    """
    if not variant:
        return None
    return (
        CommodityRate.objects.filter(variant=variant, is_active=True)
        .order_by("-effective_date")
        .first()
    )


def calculate_sku_price(sku):
    """
    Compute unit price for a SKU using your CommodityRate logic or fixed price.
    Returns: (unit_price Decimal, tax_details dict)
    """
    # If SKU uses fixed price, return that price (taxes could be included/excluded depending on your rules)
    if getattr(sku, "sell_by_fixed_price", False) and sku.fixed_price is not None:
        unit_price = Decimal(sku.fixed_price)
        tax_details = {"method": "fixed_price"}
        return quantize_money(unit_price), tax_details

    # Need commodity variant and a latest rate
    variant = getattr(sku, "commodity_variant", None)
    rate = get_latest_rate_for_variant(variant)
    if rate is None:
        raise ValueError("No active commodity rate found for SKU variant")

    # Price logic from your SKU.recalculate_price_from_rate simplified to per-unit price
    commodity_type = variant.commodity.category  # "metal" or "stone"

    # base computations
    if commodity_type == "metal":
        # unit_price is rate.unit_price * weight (weight in grams usually)
        base_value = Decimal(rate.unit_price) * Decimal(sku.weight or 0)
        wastage = (base_value * Decimal(rate.wastage_percent or 0)) / Decimal("100")
        making_charge = Decimal(sku.making_charge or 0)
        subtotal = base_value + wastage + making_charge

        cgst = (subtotal * Decimal(rate.cgst_percent or 0)) / Decimal("100")
        sgst = (subtotal * Decimal(rate.sgst_percent or 0)) / Decimal("100")

        hallmark = Decimal(sku.hallmark_charges or 0)
        delivery = 0 # Decimal(sku.delivery_charges or 0)
        packaging = Decimal(sku.packaging_charges or 0)

        unit_price = subtotal + cgst + sgst + hallmark + delivery + packaging

        tax_details = {
            "method": "commodity_metal",
            "unit_base_value": str(quantize_money(base_value)),
            "wastage_value": str(quantize_money(wastage)),
            "making_charge": str(quantize_money(making_charge)),
            "cgst_percent": str(rate.cgst_percent),
            "sgst_percent": str(rate.sgst_percent),
            "cgst_value": str(quantize_money(cgst)),
            "sgst_value": str(quantize_money(sgst)),
            "hallmark_charges": str(quantize_money(hallmark)),
            "delivery_charges": str(quantize_money(delivery)),
            "packaging_charges": str(quantize_money(packaging)),
        }

    else:
        # stone pricing (ratti multiplier -> carat)
        ratti_multiplier = Decimal(rate.ratti_multiplier or 0)
        carat_weight = Decimal(sku.weight or 0) * ratti_multiplier
        stone_value = carat_weight * Decimal(rate.unit_price)

        gst_total_percent = Decimal(rate.cgst_percent or 0) + Decimal(rate.sgst_percent or 0)
        gst_value = (stone_value * gst_total_percent) / Decimal("100")

        hallmark = Decimal(sku.hallmark_charges or 0)
        delivery = 0 # Decimal(sku.delivery_charges or 0)
        packaging = Decimal(sku.packaging_charges or 0)

        unit_price = stone_value + gst_value + hallmark + delivery + packaging

        tax_details = {
            "method": "commodity_stone",
            "carat_weight": str(carat_weight),
            "stone_value": str(quantize_money(stone_value)),
            "gst_percent_total": str(gst_total_percent),
            "gst_value": str(quantize_money(gst_value)),
            "hallmark_charges": str(quantize_money(hallmark)),
            "delivery_charges": 0, # str(quantize_money(delivery)),
            "packaging_charges": str(quantize_money(packaging)),
        }

    # Add final unit price as string
    unit_price = quantize_money(Decimal(unit_price))
    tax_details["unit_price"] = str(unit_price)
    # print("Unit Price:", unit_price)
    # print("Tax Details:", tax_details)
    return unit_price, tax_details
