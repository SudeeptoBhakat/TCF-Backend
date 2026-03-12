import os
import sys
import django
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

import orders.utils

class MockCommodity:
    def __init__(self, cat):
        self.category = cat

class MockVariant:
    def __init__(self, c):
        self.commodity = c

class MockRate:
    def __init__(self, up, w, c, s, r):
        self.unit_price = Decimal(str(up))
        self.wastage_percent = Decimal(str(w))
        self.cgst_percent = Decimal(str(c))
        self.sgst_percent = Decimal(str(s))
        self.ratti_multiplier = Decimal(str(r))

class MockSKU:
    def __init__(self, variant, weight, mc, hc, pc, dp, f=False, fp=None):
        self.sku_code = 'RING-22K-10G'
        self.commodity_variant = variant
        self.weight = Decimal(str(weight))
        self.making_charge = Decimal(str(mc))
        self.hallmark_charges = Decimal(str(hc))
        self.packaging_charges = Decimal(str(pc))
        self.discount_percent = Decimal(str(dp))
        self.sell_by_fixed_price = f
        self.fixed_price = Decimal(str(fp)) if fp else None

original_get = orders.utils.get_latest_rate_for_variant

metal_variant = MockVariant(MockCommodity('metal'))
rate_metal = MockRate(up=6000, w=5, c=1.5, s=1.5, r=0)

orders.utils.get_latest_rate_for_variant = lambda v: rate_metal

sku_metal = MockSKU(variant=metal_variant, weight=10, mc=2000, hc=53, pc=20, dp=10)

fp, breakdown = orders.utils.calculate_sku_price(sku_metal)

print('================== METAL TEST RESULTS ==================')
print(f'Final Price: {fp}')
print(f'Matches expected (60321): {fp == Decimal("60321.00")}')
import json
print(json.dumps(breakdown, indent=2))

orders.utils.get_latest_rate_for_variant = original_get
