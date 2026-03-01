from django.utils.text import slugify
from django.utils import timezone
from django.utils.html import mark_safe
from django.core.validators import MinValueValidator
from decimal import Decimal
from django.dispatch import receiver
from django.db.models.signals import post_save
from django.db.models import Q
from django.db import models
from django.db import transaction
import uuid
import logging

logger = logging.getLogger(__name__)


class TimestampedModel(models.Model):
    """
    Abstract base model containing created_at and updated_at timestamps.
    Used across all catalog-related tables.
    """
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class ProductCategory(TimestampedModel):
    """
    Supports multi-level tree structure using parent–child relationship.
    Includes SEO slug, image JSON and active status.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children"
    )

    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=180, unique=True)

    description = models.TextField(blank=True)
    image = models.ImageField(upload_to='products/catagory/', null=True, blank=True)

    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "product_categories"
        indexes = [
            models.Index(fields=["slug"]),
            models.Index(fields=["name"]),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Product(TimestampedModel):
    """
    Core product model containing descriptive, SEO and category associations.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    category = models.ForeignKey(
        ProductCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products"
    )

    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)

    description = models.TextField(blank=True)
    warranty = models.CharField(max_length=255, blank=True)

    # SEO
    meta_title = models.CharField(max_length=255, blank=True)
    meta_description = models.TextField(blank=True)

    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "products"
        indexes = [
            models.Index(fields=["category"]),
            models.Index(fields=["slug"]),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class ProductMedia(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='media')
    sku = models.ForeignKey(
        'ProductSKU',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='media'
    )

    # Real image upload field
    media_file = models.ImageField(upload_to='products/media/', null=True, blank=True)

    media = models.JSONField(null=True, blank=True)
    sort_order = models.IntegerField(default=0)

    class Meta:
        db_table = 'product_media'
        ordering = ['sort_order']

    def thumbnail(self):
        if self.media_file:
            return f"<img src='{self.media_file.url}' width='70' style='border-radius:6px;' />"
        return "No Image"

    thumbnail.allow_tags = True
    thumbnail.short_description = "Preview"
    

class ProductAttribute(TimestampedModel):
    """
    Defines attribute types such as Weight, Purity, Color, Size, etc.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120, unique=True)

    is_filterable = models.BooleanField(default=True)

    class Meta:
        db_table = "product_attributes"

    def __str__(self):
        return self.name


class ProductAttributeOption(TimestampedModel):
    """
    Options for attributes — example:
    Color → Red, Blue
    Purity → 22K, 24K
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    attribute = models.ForeignKey(
        ProductAttribute,
        on_delete=models.CASCADE,
        related_name="options"
    )

    value = models.CharField(max_length=200)
    value_slug = models.SlugField(max_length=200)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "product_attribute_options"
        unique_together = (("attribute", "value_slug"),)

    def __str__(self):
        return f"{self.attribute.name} → {self.value}"


class ProductAttributeAssignment(models.Model):
    """
    Connects Product → Attribute (one attribute per product)
    Example: Product 22K Ring → Assigned attributes: Purity, Weight
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="attribute_assignments"
    )
    attribute = models.ForeignKey(ProductAttribute, on_delete=models.CASCADE)

    class Meta:
        db_table = "product_attribute_assignments"
        unique_together = (("product", "attribute"),)


class Commodity(models.Model):
    """
    Gold / Silver / Diamond category.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    code = models.SlugField(max_length=80, unique=True)
    name = models.CharField(max_length=120)
    category = models.CharField(max_length=50, default="metal")  # metal/stone

    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        db_table = "commodities"

    def __str__(self):
        return self.name


class CommodityVariant(models.Model):
    """
    Example:
    Gold → 22K, 24K
    Diamond → VVS1, VS1
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    commodity = models.ForeignKey(
        Commodity,
        on_delete=models.CASCADE,
        related_name="variants"
    )

    code = models.SlugField(max_length=120)   # 22k, 24k, vvs1
    name = models.CharField(max_length=150)

    unit = models.CharField(max_length=20, default="gram")  # gram/carat
    metadata = models.JSONField(null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        db_table = "commodity_variants"
        unique_together = (("commodity", "code"),)

    def __str__(self):
        return f"{self.commodity.name} - {self.name}"


class CommodityRate(models.Model):
    """
    Daily or periodic commodity pricing.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    variant = models.ForeignKey(
        CommodityVariant,
        on_delete=models.CASCADE,
        related_name="rates"
    )
    unit_price = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0.0001"))]
    )
    cgst_percent = models.DecimalField(max_digits=12, decimal_places=2, default=1.5)
    sgst_percent = models.DecimalField(max_digits=12, decimal_places=2, default=1.5)
    ratti_multiplier = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    wastage_percent = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    source = models.CharField(max_length=200, blank=True)
    effective_date = models.DateField()

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        db_table = "commodity_rates"
        unique_together = (("variant", "effective_date"),)
        indexes = [
            models.Index(fields=["effective_date"]),
            models.Index(fields=["variant"]),
        ]

    def __str__(self):
        return f"{self.variant} - {self.unit_price} on {self.effective_date}"


# ---------------------------------------------------------
# SIGNAL → Auto Update SKU Prices When Commodity Rate Changes
# ---------------------------------------------------------
@receiver(post_save, sender=CommodityRate)
def update_sku_prices_after_rate_change(sender, instance, created, **kwargs):

    if not instance.is_active:
        return

    skus = ProductSKU.objects.filter(
        commodity_variant=instance.variant,
        sell_by_fixed_price=False,
        is_active=True
    )

    updated_skus = []
    for sku in skus:
        sku.recalculate_price_from_rate(instance)
        updated_skus.append(sku)

    # prevent 1000 queries → turn into 1 query
    ProductSKU.objects.bulk_update(updated_skus, ['price', 'discount_price', 'updated_at'])



class ProductSKU(TimestampedModel):
    """
    SKU model representing specific sellable units.
    Supports dynamic pricing based on commodity rate.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="skus"
    )

    sku_code = models.CharField(max_length=120, unique=True)
    barcode = models.CharField(max_length=120, blank=True)

    commodity_variant = models.ForeignKey(
        CommodityVariant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="skus"
    )

    weight = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    making_charge = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    packaging_charges = models.DecimalField(max_digits=12, decimal_places=2, default=0, null=True, blank=True)
    hallmark_charges = models.DecimalField(max_digits=12, decimal_places=2, default=0, null=True, blank=True)

    price = models.DecimalField(max_digits=12, decimal_places=2)
    discount_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    sell_by_fixed_price = models.BooleanField(default=False)
    fixed_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    stock_qty = models.IntegerField(default=0, validators=[MinValueValidator(0)])

    is_halmark = models.BooleanField(default=False)
    is_bestseller = models.BooleanField(default=False)
    is_featured = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "product_skus"
        indexes = [
            models.Index(fields=["product"]),
            models.Index(fields=["sku_code"]),
            models.Index(fields=["stock_qty"]),
            models.Index(fields=["commodity_variant"]),
            models.Index(fields=["sell_by_fixed_price"]),
        ]

    def __str__(self):
        return f"{self.sku_code} - {self.product.name}"

    def recalculate_price_from_rate(self, rate: CommodityRate):
        """
        CORE FIX: Dynamically recalculate SKU price from commodity rate.
        Handles both metal and stone pricing with full GST support.
        """
        method_name = "recalculate_price_from_rate"
        
        try:
            # ====================================================================
            # 1. VALIDATION CHECKS
            # ====================================================================
            if self.sell_by_fixed_price:
                logger.debug(f"SKU {self.sku_code}: sell_by_fixed_price=True, skipping recalculation")
                return

            if not self.commodity_variant:
                raise ValueError(f"SKU {self.sku_code}: No commodity_variant assigned. Cannot calculate price.")

            if not self.weight or self.weight <= 0:
                raise ValueError(f"SKU {self.sku_code}: Invalid weight ({self.weight}). Cannot calculate price.")

            if not rate:
                raise ValueError(f"SKU {self.sku_code}: No CommodityRate provided.")

            if rate.unit_price <= 0:
                raise ValueError(f"SKU {self.sku_code}: Rate unit_price is invalid ({rate.unit_price})")

            # ====================================================================
            # 2. DETERMINE COMMODITY TYPE & LOG START
            # ====================================================================
            commodity_type = self.commodity_variant.commodity.category
            
            logger.info(
                f"[{method_name}] SKU: {self.sku_code} | Type: {commodity_type} | "
                f"Weight: {self.weight}g | Rate: ₹{rate.unit_price} | "
                f"Date: {rate.effective_date}"
            )

            base_price = Decimal("0")
            calculation_log = {}

            # ====================================================================
            # 3. METAL PRICING (GOLD, SILVER)
            # ====================================================================
            if commodity_type == "metal":
                try:
                    # Base metal value
                    gold_value = rate.unit_price * self.weight

                    # Wastage
                    wastage_value = (gold_value * rate.wastage_percent) / Decimal("100")

                    # Making charge
                    making_charge_val = Decimal(self.making_charge or 0)

                    # Subtotal = gold_value + wastage + making_charge
                    subtotal = gold_value + wastage_value + making_charge_val
                    print(gold_value, '+', wastage_value, '+', making_charge_val)
                    # GST CALCULATION (CRITICAL FIX)
                    cgst_value = (subtotal * rate.cgst_percent) / Decimal("100")
                    sgst_value = (subtotal * rate.sgst_percent) / Decimal("100")
                    gst_total = cgst_value + sgst_value

                    # Additional charges
                    hallmark = 53 * Decimal(self.hallmark_charges or 0)
                    delivery = 0 # Decimal(self.delivery_charges or 0)
                    packaging = Decimal(self.packaging_charges or 0)

                    # FINAL PRICE FOR METAL
                    final_price = subtotal + gst_total + hallmark + delivery + packaging
                    print(subtotal, '+', gst_total, '+', hallmark, '+', delivery, '+', packaging)

                    base_price = final_price
                except Exception as metal_err:
                    logger.error(f"  ✗ Metal pricing calculation failed: {metal_err}", exc_info=True)
                    raise

            # ====================================================================
            # 4. STONE PRICING (DIAMOND, RUBY, etc.)
            # ====================================================================
            else:
                try:
                    # Ratti to Carat conversion
                    carat_weight = self.weight * rate.ratti_multiplier

                    # Stone value
                    stone_value = carat_weight * rate.unit_price

                    # GST CALCULATION (CRITICAL FIX)
                    gst_percent_total = rate.cgst_percent + rate.sgst_percent
                    gst_value = (stone_value * gst_percent_total) / Decimal("100")
                    
                    
                    # Additional charges
                    hallmark = Decimal(self.hallmark_charges or 0)
                    delivery = 0 # Decimal(rate.delivery_charges or 0)
                    packaging = Decimal(self.packaging_charges or 0)
                    
                    # FINAL PRICE FOR STONE
                    final_price = stone_value + gst_value + hallmark + delivery + packaging
                    
                    base_price = final_price

                except Exception as stone_err:
                    logger.error(f"  ✗ Stone pricing calculation failed: {stone_err}", exc_info=True)
                    raise

            # ====================================================================
            # 5. SAVE WITH ATOMIC TRANSACTION
            # ====================================================================
            # Quantize to 2 decimal places
            self.price = base_price.quantize(Decimal("0.01"))
            
            logger.info(f"  ✓ Saving SKU {self.sku_code}: Price = ₹{self.price}")
            self.save(update_fields=["price", "updated_at"])
            
            logger.info(f"  ✓ Price update SUCCESS for {self.sku_code} | Calculation: {calculation_log}")

        except Exception as e:
            logger.error(
                f"  ✗ CRITICAL ERROR in recalculate_price_from_rate for SKU {self.sku_code}: {str(e)}",
                exc_info=True,
                extra={"sku_code": self.sku_code, "rate_id": rate.id if rate else None}
            )
            raise

    def decrement_stock(self, qty: int):
        """Safely decrement stock with locking."""
        if qty <= 0:
            raise ValueError("Quantity must be > 0")

        with transaction.atomic():
            obj = ProductSKU.objects.select_for_update().get(pk=self.pk)

            if obj.stock_qty < qty:
                raise ValueError(f"Insufficient stock. Available: {obj.stock_qty}, Requested: {qty}")

            obj.stock_qty -= qty
            obj.save(update_fields=["stock_qty", "updated_at"])
            logger.info(f"Stock decremented for {obj.sku_code}: -{qty} units")


class SKUAttributeOption(models.Model):
    """
    Connects a SKU to its attribute options.
    """
    sku = models.ForeignKey(
        ProductSKU, on_delete=models.CASCADE, related_name="sku_attribute_options"
    )
    attribute_option = models.ForeignKey(
        ProductAttributeOption, on_delete=models.RESTRICT
    )

    class Meta:
        db_table = "sku_attribute_options"
        unique_together = (("sku", "attribute_option"),)


# =====================================================================
# SIGNAL: Auto-update SKU prices when CommodityRate changes
# =====================================================================
@receiver(post_save, sender=CommodityRate)
def update_sku_prices_after_rate_change(sender, instance, created, **kwargs):
    """
    SIGNAL HANDLER: Automatically recalculates SKU prices when a rate is saved.
    
    Triggered when:
    - New CommodityRate is created
    - Existing CommodityRate is updated
    
    Key Features:
    - Only processes active rates
    - Atomic transaction ensures consistency
    - Comprehensive error logging
    - Skips fixed-price SKUs
    """
    signal_id = str(instance.id)[:8]
    
    try:
        logger.info(f"[post_save Signal-{signal_id}] CommodityRate update initiated")
        logger.info(f"  Variant: {instance.variant} | Unit Price: {instance.unit_price} | Active: {instance.is_active}")

        # Only process active rates
        if not instance.is_active:
            logger.info(f"[post_save Signal-{signal_id}] Rate is inactive. Skipping SKU updates.")
            return

        # Fetch all eligible SKUs
        skus = ProductSKU.objects.filter(
            Q(commodity_variant=instance.variant),
            Q(sell_by_fixed_price=False),
            Q(is_active=True)
        ).select_related('product', 'commodity_variant__commodity')

        if not skus.exists():
            logger.warning(f"[post_save Signal-{signal_id}] No eligible SKUs found for variant {instance.variant}")
            return

        sku_count = skus.count()
        logger.info(f"[post_save Signal-{signal_id}] Found {sku_count} SKUs to update")

        # Update all SKUs atomically
        with transaction.atomic():
            failed_skus = []
            successful_skus = []

            for sku in skus:
                try:
                    logger.debug(f"[post_save Signal-{signal_id}] Processing SKU: {sku.sku_code}")
                    sku.recalculate_price_from_rate(instance)
                    successful_skus.append(sku.sku_code)
                    logger.debug(f"  ✓ Updated {sku.sku_code}: ₹{sku.price}")

                except Exception as sku_err:
                    logger.error(
                        f"[post_save Signal-{signal_id}] Failed to update SKU {sku.sku_code}: {str(sku_err)}",
                        exc_info=True
                    )
                    failed_skus.append((sku.sku_code, str(sku_err)))

        logger.info(
            f"[post_save Signal-{signal_id}] ✓ Signal complete | "
            f"Success: {len(successful_skus)} | Failed: {len(failed_skus)}"
        )

        if failed_skus:
            logger.warning(f"[post_save Signal-{signal_id}] Failed SKUs: {failed_skus}")

    except Exception as e:
        logger.error(
            f"[post_save Signal-{signal_id}] ✗ CRITICAL SIGNAL FAILURE: {str(e)}",
            exc_info=True,
            extra={"rate_id": instance.id, "variant_id": instance.variant_id}
        )