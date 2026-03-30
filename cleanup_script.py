import os
import sys
import django
import logging

try:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()
except Exception as e:
    print(f"Error setting up Django: {e}")
    print("Please make sure you are running this from your activated virtual environment.")
    sys.exit(1)

from inventory.models import ProductSKU
from django.db import transaction

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger('db_cleanup')

def cleanup_invalid_skus(action="log"):
    """
    Finds and handles ProductSKUs with missing relationships.
    action: "log" or "delete"
    """
    invalid_product_skus = ProductSKU.objects.filter(product__isnull=True)
    invalid_variant_skus = ProductSKU.objects.filter(commodity_variant__isnull=True, sell_by_fixed_price=False)
    
    logger.info(f"Found {invalid_product_skus.count()} SKUs with missing product.")
    for sku in invalid_product_skus:
        logger.info(f" - SKU: {sku.sku_code}, PK: {sku.pk}")
        
    logger.info(f"Found {invalid_variant_skus.count()} Non-fixed-price SKUs with missing commodity variant.")
    for sku in invalid_variant_skus:
        logger.info(f" - SKU: {sku.sku_code}, PK: {sku.pk}")
        
    if action == "delete":
        logger.warning("Starting deletion of invalid records...")
        with transaction.atomic():
            if invalid_product_skus.exists():
                deleted_prod_count, _ = invalid_product_skus.delete()
                logger.info(f"Deleted {deleted_prod_count} SKUs with missing products.")
                
            if invalid_variant_skus.exists():
                deleted_var_count, _ = invalid_variant_skus.delete()
                logger.info(f"Deleted {deleted_var_count} SKUs with missing commodity variants.")
        logger.info("Cleanup completed.")
    else:
        logger.info("Run with action='delete' to permanently remove these records.")

if __name__ == '__main__':
    # Change "log" to "delete" if you want to permanently remove invalid records
    cleanup_invalid_skus(action="log")
