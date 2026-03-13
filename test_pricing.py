import os
import sys
import django
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from inventory.models import ProductSKU, CommodityVariant, Commodity, CommodityRate
from orders.utils import calculate_sku_price

# We will create mock objects using actual Django models but not save them to DB to avoid DB constraints.
# Or better, we can monkey-patch get_price_breakdown onto MockSKU if we want to keep it simple, 
# but testing with actual ProductSKU is better.

class MockCommodity:
    category = 'metal'

class MockVariant:
    commodity = MockCommodity()

class MockRate:
    unit_price = Decimal("6000")
    wastage_percent = Decimal("5")
    cgst_percent = Decimal("1.5")
    sgst_percent = Decimal("1.5")
    ratti_multiplier = Decimal("0")

class MockSKU:
    sku_code = 'RING-22K-10G'
    commodity_variant = MockVariant()
    weight = Decimal("10")
    making_charge = Decimal("2000")
    hallmark_charges = Decimal("53")
    packaging_charges = Decimal("20")
    discount_percent = Decimal("10")
    sell_by_fixed_price = False
    fixed_price = None
    price = Decimal("0")

# Attach the method from ProductSKU to MockSKU
MockSKU.get_price_breakdown = ProductSKU.get_price_breakdown

sku_metal = MockSKU()

# Now call the wrapper or the method directly
# We also need to patch get_price_breakdown since it might fetch rates or we can pass rate.
# Wait, get_price_breakdown fetches rate using CommodityRate.objects.filter if not passed.
breakdown = sku_metal.get_price_breakdown(rate=MockRate())

print('================== METAL TEST RESULTS ==================')
print(f'Final Price: {breakdown["final_price"]}')
print(f'Matches expected (60321): {breakdown["final_price"] == 60321.00}')
import json
print(json.dumps(breakdown, indent=2))

