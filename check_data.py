import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from inventory.models import ProductSKU

print("Checking for missing Product references in ProductSKU...")
skus_without_product = list(ProductSKU.objects.filter(product__isnull=True))
print(f"Found {len(skus_without_product)} SKUs without a Product.")
for sku in skus_without_product:
    print(f"SKU Code: {sku.sku_code}, ID: {sku.id}")

print("Checking for missing CommodityVariant references in ProductSKU...")
skus_without_variant = list(ProductSKU.objects.filter(commodity_variant__isnull=True))
print(f"Found {len(skus_without_variant)} SKUs without a CommodityVariant.")
for sku in skus_without_variant:
    print(f"SKU Code: {sku.sku_code}, ID: {sku.id}")

print("Validation complete.")
