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
        tax_details = {"method": "fixed_price", "grand_total": str(unit_price)}
        return quantize_money(unit_price), tax_details

    # Need commodity variant and a latest rate
    variant = getattr(sku, "commodity_variant", None)
    rate = get_latest_rate_for_variant(variant)
    if rate is None:
        raise ValueError("No active commodity rate found for SKU variant")

    commodity_type = variant.commodity.category  # "metal" or "stone"
    
    # Check if there's a discount price
    discount_price_val = getattr(sku, "discount_price", None)
    if discount_price_val is not None and discount_price_val > 0:
        has_discount = True
        final_price_target = Decimal(discount_price_val)
    else:
        has_discount = False
        final_price_target = Decimal("0")
    
    unit_price = Decimal("0")

    # base computations
    if commodity_type == "metal":
        gold_rate = Decimal(rate.unit_price)
        weight = Decimal(sku.weight or 0)
        
        # unit_price is rate.unit_price * weight (weight in grams usually)
        base_value = gold_rate * weight
        wastage = (base_value * Decimal(rate.wastage_percent or 0)) / Decimal("100")
        making_charge = Decimal(sku.making_charge or 0)
        
        original_subtotal = base_value + wastage + making_charge

        hallmark = Decimal(sku.hallmark_charges or 0)
        delivery = Decimal("0.00") # Decimal(sku.delivery_charges or 0)
        packaging = Decimal(sku.packaging_charges or 0)
        extras = hallmark + delivery + packaging

        cgst_percent = Decimal(rate.cgst_percent or 0)
        sgst_percent = Decimal(rate.sgst_percent or 0)
        total_gst_percent = cgst_percent + sgst_percent

        if has_discount:
            # Reverse calculate from the discounted final price
            # Final = Taxable + (Taxable * GST%) + Extras
            # Taxable = (Final - Extras) / (1 + GST%)
            taxable_value = (final_price_target - extras) / (Decimal("1") + (total_gst_percent / Decimal("100")))
            discount_amount = original_subtotal - taxable_value
            subtotal = taxable_value
            cgst = (subtotal * cgst_percent) / Decimal("100")
            sgst = (subtotal * sgst_percent) / Decimal("100")
            unit_price = final_price_target
        else:
            subtotal = original_subtotal
            discount_amount = Decimal("0")
            cgst = (subtotal * cgst_percent) / Decimal("100")
            sgst = (subtotal * sgst_percent) / Decimal("100")
            unit_price = subtotal + cgst + sgst + extras

        # Rounding
        grand_total = unit_price.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        round_off = grand_total - unit_price

        tax_details = {
            "method": "commodity_metal",
            "gold_rate": str(quantize_money(gold_rate)),
            "weight": str(weight),
            "unit_base_value": str(quantize_money(base_value)),
            "wastage_value": str(quantize_money(wastage)),
            "making_charge": str(quantize_money(making_charge)),
            "discount_amount": str(quantize_money(discount_amount)),
            "subtotal": str(quantize_money(subtotal)),
            "cgst_percent": str(cgst_percent),
            "sgst_percent": str(sgst_percent),
            "cgst_value": str(quantize_money(cgst)),
            "sgst_value": str(quantize_money(sgst)),
            "hallmark_charges": str(quantize_money(hallmark)),
            "delivery_charges": str(quantize_money(delivery)),
            "packaging_charges": str(quantize_money(packaging)),
            "round_off": str(quantize_money(round_off)),
            "grand_total": str(grand_total),
            "unit_price": str(quantize_money(unit_price))
        }

    else:
        # stone pricing (ratti multiplier -> carat)
        ratti_multiplier = Decimal(rate.ratti_multiplier or 0)
        carat_weight = Decimal(sku.weight or 0) * ratti_multiplier
        original_stone_value = carat_weight * Decimal(rate.unit_price)
        
        hallmark = Decimal(sku.hallmark_charges or 0)
        delivery = Decimal("0.00") # Decimal(sku.delivery_charges or 0)
        packaging = Decimal(sku.packaging_charges or 0)
        extras = hallmark + delivery + packaging

        cgst_percent = Decimal(rate.cgst_percent or 0)
        sgst_percent = Decimal(rate.sgst_percent or 0)
        gst_total_percent = cgst_percent + sgst_percent

        if has_discount:
            taxable_value = (final_price_target - extras) / (Decimal("1") + (gst_total_percent / Decimal("100")))
            discount_amount = original_stone_value - taxable_value
            stone_value = taxable_value
            cgst = (stone_value * cgst_percent) / Decimal("100")
            sgst = (stone_value * sgst_percent) / Decimal("100")
            unit_price = final_price_target
        else:
            stone_value = original_stone_value
            discount_amount = Decimal("0")
            cgst = (stone_value * cgst_percent) / Decimal("100")
            sgst = (stone_value * sgst_percent) / Decimal("100")
            unit_price = stone_value + cgst + sgst + extras

        # Rounding
        grand_total = unit_price.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        round_off = grand_total - unit_price

        tax_details = {
            "method": "commodity_stone",
            "carat_weight": str(carat_weight),
            "unit_base_value": str(quantize_money(original_stone_value)),
            "stone_value": str(quantize_money(stone_value)),
            "discount_amount": str(quantize_money(discount_amount)),
            "gst_percent_total": str(gst_total_percent),
            "cgst_percent": str(cgst_percent),
            "sgst_percent": str(sgst_percent),
            "cgst_value": str(quantize_money(cgst)),
            "sgst_value": str(quantize_money(sgst)),
            "hallmark_charges": str(quantize_money(hallmark)),
            "delivery_charges": str(quantize_money(delivery)),
            "packaging_charges": str(quantize_money(packaging)),
            "round_off": str(quantize_money(round_off)),
            "grand_total": str(grand_total),
            "unit_price": str(quantize_money(unit_price))
        }

    return quantize_money(unit_price), tax_details
