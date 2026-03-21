from decimal import Decimal, ROUND_HALF_UP
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
    from inventory.models import CommodityRate
    return (
        CommodityRate.objects.filter(variant=variant, is_active=True)
        .order_by("-effective_date")
        .first()
    )


def calculate_sku_price(sku, rate=None):
    """
    Compute unit price for a SKU using dynamic commodity pricing or fixed price.
    Returns: (final_price Decimal, price_breakdown dict)
    """
    try:
        breakdown = sku.get_price_breakdown(rate=rate)
        final_price = Decimal(str(breakdown["final_price"]))
        
        return final_price, {
            "sku": sku.sku_code,
            "price_breakdown": breakdown
        }
    except Exception as e:
        logger.error(f"Error calculating base price for {sku.sku_code}: {e}")
        
        final_price = Decimal(str(sku.price or 0))
        return final_price, {
            "sku": sku.sku_code,
            "price_breakdown": {
                "method": "fallback",
                "final_price": float(final_price)
            }
        }
