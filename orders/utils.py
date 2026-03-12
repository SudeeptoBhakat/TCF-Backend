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
    Compute unit price for a SKU using dynamic commodity pricing or fixed price.
    Returns: (final_price Decimal, price_breakdown dict)
    """
    if getattr(sku, "sell_by_fixed_price", False) and getattr(sku, "fixed_price", None) is not None:
        final_price = quantize_money(Decimal(sku.fixed_price))
        price_breakdown = {
            "sku": sku.sku_code,
            "price_breakdown": {
                "method": "fixed_price",
                "final_price": str(final_price),
                "base_price": str(final_price),
                "discount_percent": "0",
                "discount_amount": "0.00"
            }
        }
        return final_price, price_breakdown

    variant = getattr(sku, "commodity_variant", None)
    rate = get_latest_rate_for_variant(variant)
    if rate is None:
        raise ValueError(f"No active commodity rate found for SKU variant. SKU: {sku.sku_code}")

    commodity_type = variant.commodity.category  # "metal" or "stone"
    discount_percent = Decimal(getattr(sku, "discount_percent", 0) or 0)
    
    metal_value = Decimal("0")
    stone_value = Decimal("0")
    wastage = Decimal("0")
    making_charge = Decimal("0")
    subtotal = Decimal("0")
    
    hallmark = Decimal(sku.hallmark_charges or 0)
    packaging = Decimal(sku.packaging_charges or 0)
    delivery = Decimal("0.00")
    
    cgst_percent = Decimal(rate.cgst_percent or Decimal("1.5"))
    sgst_percent = Decimal(rate.sgst_percent or Decimal("1.5"))

    if commodity_type == "metal":
        gold_rate = Decimal(rate.unit_price)
        weight = Decimal(sku.weight or 0)
        
        metal_value = gold_rate * weight
        wastage_percent = Decimal(rate.wastage_percent or 0)
        wastage = (metal_value * wastage_percent) / Decimal("100")
        making_charge = Decimal(sku.making_charge or 0)
        
        subtotal = metal_value + wastage + making_charge
        
        cgst = (subtotal * cgst_percent) / Decimal("100")
        sgst = (subtotal * sgst_percent) / Decimal("100")
    else:
        ratti_multiplier = Decimal(rate.ratti_multiplier or 0)
        carat_weight = Decimal(sku.weight or 0) * ratti_multiplier
        stone_value = carat_weight * Decimal(rate.unit_price)
        
        subtotal = stone_value
        cgst = (subtotal * cgst_percent) / Decimal("100")
        sgst = (subtotal * sgst_percent) / Decimal("100")

    extras = hallmark + packaging + delivery
    
    base_price = subtotal + cgst + sgst + extras
    
    discount_amount = (base_price * discount_percent) / Decimal("100")
    
    final_price = base_price - discount_amount
    
    final_price_quantized = quantize_money(final_price)
    print("DEBUG PRICE CALCULATION")
    print("rate:", rate.unit_price)
    print("weight:", sku.weight)
    print("metal_value:", metal_value)
    print("wastage:", wastage)
    print("making_charge:", making_charge)
    print("subtotal:", subtotal)
    print("cgst:", cgst)
    print("sgst:", sgst)
    print("extras:", extras)
    print("base_price:", base_price)
    price_breakdown_dict = {
        "gold_rate": float(rate.unit_price) if commodity_type == "metal" else 0,
        "weight": float(sku.weight or 0),
        
        "metal_value": float(quantize_money(metal_value)) if commodity_type == "metal" else 0,
        "stone_value": float(quantize_money(stone_value)) if commodity_type == "stone" else 0,
        "wastage": float(quantize_money(wastage)),
        "making_charge": float(quantize_money(making_charge)),
        
        "subtotal": float(quantize_money(subtotal)),
        
        "cgst": float(quantize_money(cgst)),
        "sgst": float(quantize_money(sgst)),
        
        "hallmark": float(quantize_money(hallmark)),
        "packaging": float(quantize_money(packaging)),
        "delivery": float(quantize_money(delivery)),
        
        "base_price": float(quantize_money(base_price)),
        
        "discount_percent": float(discount_percent),
        "discount_amount": float(quantize_money(discount_amount)),
        
        "final_price": float(final_price_quantized)
    }

    response = {
        "sku": sku.sku_code,
        "price_breakdown": price_breakdown_dict
    }
    print("DEBUG: ", response)
    
    return final_price_quantized, response
