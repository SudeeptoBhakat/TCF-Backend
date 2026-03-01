import csv
import os
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify
from decimal import Decimal
from datetime import date
from pathlib import Path

# IMPORTANT: Adjust this import path to your models.py file location
from inventory.models import (
    Product, ProductCategory, Commodity, CommodityVariant, 
    CommodityRate, ProductSKU, logger # Assuming logger is defined in models.py or use standard logging
) 

# Helper to safely convert values to Decimal
def safe_decimal(value, default="0.00"):
    if value is None or value == '':
        return Decimal(default)
    try:
        return Decimal(value)
    except Exception:
        return Decimal(default)

# Helper to safely convert value to Boolean
def safe_boolean(value):
    if isinstance(value, str):
        return value.lower() in ('true', '1', 't')
    return bool(value)


class Command(BaseCommand):
    help = 'Loads jewellery products and related data from the provided CSV file.'

    def add_arguments(self, parser):
        parser.add_argument(
            'csv_file', 
            type=str, 
            help='The path to the CSV file (e.g., jewellery_25_seed.csv)'
        )

    def handle(self, *args, **options):
        file_path = options['csv_file']
        
        # Resolve file path
        if not os.path.isabs(file_path):
            file_path = os.path.join(os.getcwd(), file_path) 

        if not Path(file_path).is_file():
            raise CommandError(f'File not found at path: {file_path}')

        self.stdout.write(f'Attempting to load data from: {file_path}')

        # We will track created objects to avoid redundant database hits
        # Storing (commodity_code, variant_code) -> CommodityVariant object
        variant_cache = {} 
        # Storing category_name -> ProductCategory object
        category_cache = {} 

        try:
            with open(file_path, mode='r', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                
                # Use a database transaction for efficiency and atomicity
                with transaction.atomic():
                    for i, row in enumerate(reader):
                        line_num = i + 2 # Add 1 for 0-index, 1 for header row
                        self.stdout.write(f"--- Processing Line {line_num}: {row['product_name'][:30]}...", self.style.NOTICE)

                        # ==========================================================
                        # 1. Commodity and CommodityVariant (Needs to be first)
                        # ==========================================================
                        commodity_code = row['commodity'].lower()
                        variant_code = row['commodity_variant'].lower()
                        unit = row['unit'].lower()
                        cache_key = (commodity_code, variant_code)

                        if cache_key not in variant_cache:
                            
                            # 1a. Get or Create Commodity (e.g., Gold, Silver)
                            commodity_obj, created_c = Commodity.objects.get_or_create(
                                code=commodity_code,
                                defaults={
                                    'name': row['commodity'].capitalize(),
                                }
                            )
                            if created_c:
                                self.stdout.write(f"  > Created Commodity: {commodity_obj.name}")

                            # 1b. Get or Create CommodityVariant (e.g., 22k, 925)
                            variant_obj, created_v = CommodityVariant.objects.get_or_create(
                                commodity=commodity_obj,
                                code=variant_code,
                                defaults={
                                    'name': row['commodity_variant'],
                                    'unit': unit,
                                }
                            )
                            if created_v:
                                self.stdout.write(f"  > Created Variant: {variant_obj.name}")
                            
                            variant_cache[cache_key] = variant_obj
                        else:
                            variant_obj = variant_cache[cache_key]


                        # ==========================================================
                        # 2. ProductCategory
                        # ==========================================================
                        category_name = row['category']
                        if category_name not in category_cache:
                            category_obj, created_cat = ProductCategory.objects.get_or_create(
                                name=category_name,
                                defaults={'slug': slugify(category_name)}
                            )
                            if created_cat:
                                self.stdout.write(f"  > Created Category: {category_obj.name}")
                            category_cache[category_name] = category_obj
                        else:
                            category_obj = category_cache[category_name]
                        

                        # ==========================================================
                        # 3. CommodityRate (Unique by variant & effective_date)
                        # ==========================================================
                        effective_date_val = date.fromisoformat(row['effective_date'])
                        
                        # Use update_or_create to handle potential existing rates for the same day
                        rate_obj, created_r = CommodityRate.objects.update_or_create(
                            variant=variant_obj,
                            effective_date=effective_date_val,
                            defaults={
                                'unit_price': safe_decimal(row['unit_price']),
                                'cgst_percent': safe_decimal(row['cgst_percent']),
                                'sgst_percent': safe_decimal(row['sgst_percent']),
                                'wastage_percent': safe_decimal(row['wastage_percent']),
                                'ratti_multiplier': safe_decimal(row['ratti_multiplier']),
                                'hallmark_charges': safe_decimal(row['hallmark_charges']),
                                'delivery_charges': safe_decimal(row['delivery_charges']),
                                'packaging_charges': safe_decimal(row['packaging_charges']),
                                'is_active': True,
                            }
                        )
                        if created_r:
                            self.stdout.write(f"  > Created CommodityRate for {variant_obj.name} @ {rate_obj.unit_price}")
                        

                        # ==========================================================
                        # 4. Product (The parent record)
                        # ==========================================================
                        product_name_val = row['product_name']
                        product_slug_val = row['slug']
                        
                        product_obj, created_p = Product.objects.get_or_create(
                            slug=product_slug_val,
                            defaults={
                                'name': product_name_val,
                                'category': category_obj,
                                # No description/warranty available in CSV
                            }
                        )
                        if created_p:
                            self.stdout.write(f"  > Created Product: {product_obj.name}")


                        # ==========================================================
                        # 5. ProductSKU (The actual sellable item)
                        # ==========================================================
                        sell_by_fixed_price = safe_boolean(row['sell_by_fixed_price'])
                        
                        sku_defaults = {
                            'product': product_obj,
                            'commodity_variant': variant_obj,
                            'weight': safe_decimal(row['weight'], default="0.000"),
                            'making_charge': safe_decimal(row['making_charge']),
                            'sell_by_fixed_price': sell_by_fixed_price,
                            'stock_qty': 100, # Default stock quantity (Adjust as needed)
                            'is_halmark': True, # Assume if hallmark charges > 0
                            'barcode': row.get('barcode', ''),
                            'price': safe_decimal(row['price_calculated']),
                        }
                        
                        if sell_by_fixed_price:
                            # If fixed price, the calculated price is the fixed price
                            sku_defaults['fixed_price'] = safe_decimal(row['price_calculated'])
                            # For fixed price, price field should match fixed_price
                            sku_defaults['price'] = sku_defaults['fixed_price']
                        
                        sku_obj, created_s = ProductSKU.objects.get_or_create(
                            sku_code=row['sku_code'],
                            defaults=sku_defaults
                        )
                        
                        if created_s:
                            self.stdout.write(self.style.SUCCESS(f"  > Created SKU: {sku_obj.sku_code} @ ₹{sku_obj.price}"))
                        else:
                            self.stdout.write(self.style.WARNING(f"  > SKU {sku_obj.sku_code} already exists. Skipping."))


                self.stdout.write(self.style.SUCCESS('Data loading complete!'))

        except FileNotFoundError:
            raise CommandError(f'The file "{file_path}" does not exist.')
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'An error occurred during import on line {line_num}: {e}'))
            # Re-raise the error to ensure the transaction is rolled back
            raise