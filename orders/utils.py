from decimal import Decimal, ROUND_HALF_UP
from django.db.models import Q
import uuid
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

DEC2 = Decimal("0.01")


def quantize_money(value: Decimal) -> Decimal:
    return value.quantize(DEC2, rounding=ROUND_HALF_UP)

from inventory.utils import calculate_sku_price, get_latest_rate_for_variant
