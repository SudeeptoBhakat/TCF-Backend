from django.utils.text import slugify
from django.utils import timezone
from django.utils.html import mark_safe
from django.core.validators import MinValueValidator
from decimal import Decimal, ROUND_HALF_UP
from django.dispatch import receiver
from django.db.models.signals import post_save
from django.db.models import Q
from django.db import models
from django.db import transaction
import uuid
import logging

DEC2 = Decimal("0.01")
from orders.utils import calculate_sku_price, get_latest_rate_for_variant

logger = logging.getLogger(__name__)
def quantize_money(value: Decimal) -> Decimal:
    return value.quantize(DEC2, rounding=ROUND_HALF_UP)

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
    ProductSKU.objects.bulk_update(updated_skus, ['price', 'updated_at'])



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
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)

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

    def clean(self):
        super().clean()
        from django.core.exceptions import ValidationError
        
        if self.sell_by_fixed_price:
            if self.fixed_price is None or self.fixed_price < 0:
                raise ValidationError({"fixed_price": "Fixed price cannot be negative or null."})
        else:
            if not self.commodity_variant:
                raise ValidationError({"commodity_variant": "Missing Commodity Variant"})
            
            weight = Decimal(str(self.weight or 0))
            making_charge = Decimal(str(self.making_charge or 0))
            hallmark = Decimal(str(self.hallmark_charges or 0))
            packaging = Decimal(str(self.packaging_charges or 0))
            
            if weight == 0:
                if making_charge != 0 or hallmark != 0 or packaging != 0:
                    raise ValidationError({"weight": "weight missing"})
            elif weight < 0:
                raise ValidationError({"weight": "Invalid weight"})
                
            from orders.utils import get_latest_rate_for_variant
            rate = get_latest_rate_for_variant(self.commodity_variant)
            if rate is None or rate.unit_price <= 0:
                raise ValidationError({"commodity_variant": "Missing Commodity Rate"})

        if self.discount_percent and (self.discount_percent < 0 or self.discount_percent > 100):
            raise ValidationError({"discount_percent": "max discount = 100%"})

        if self.making_charge and self.making_charge < 0:
            raise ValidationError({"making_charge": "Charges cannot be negative"})
            
        if self.packaging_charges and self.packaging_charges < 0:
            raise ValidationError({"packaging_charges": "Charges cannot be negative"})
            
        if self.hallmark_charges and getattr(self, "hallmark_charges", 0) < 0:
            raise ValidationError({"hallmark_charges": "Charges cannot be negative"})
            
        if getattr(self, "stock_qty", 0) < 0:
            raise ValidationError({"stock_qty": "Stock cannot be negative"})

    def save(self, *args, **kwargs):
        if not kwargs.get("update_fields"):
            if self.sell_by_fixed_price:
                self.price = Decimal(str(self.fixed_price or 0))
            else:
                try:
                    from orders.utils import calculate_sku_price
                    price, _ = calculate_sku_price(self)
                    self.price = price
                except Exception as e:
                    logger.error(f"Error calculating base price for {self.sku_code}: {e}")
                    if self.price is None:
                        self.price = Decimal("0")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.sku_code} - {self.product.name}"
    

    def recalculate_price_from_rate(self, rate: CommodityRate):
        """
        Recalculate SKU price based on commodity rate.
        Supports both metal and stone pricing logic.
        """

        try:

            # ==========================================================
            # 1 VALIDATION
            # ==========================================================

            if self.sell_by_fixed_price:
                logger.info(f"SKU {self.sku_code} uses fixed price. Skipping calculation.")
                return

            if not self.commodity_variant:
                raise ValueError(f"{self.sku_code} has no commodity_variant")

            if not self.weight:
                raise ValueError(f"{self.sku_code} weight missing")

            if not rate:
                raise ValueError(f"{self.sku_code} rate missing")

            commodity_type = self.commodity_variant.commodity.category

            weight = Decimal(self.weight or 0)
            discount_percent = Decimal(self.discount_percent or 0)

            hallmark = Decimal(self.hallmark_charges or 0)
            packaging = Decimal(self.packaging_charges or 0)
            delivery = Decimal("0")

            cgst_percent = Decimal(rate.cgst_percent or Decimal("1.5"))
            sgst_percent = Decimal(rate.sgst_percent or Decimal("1.5"))

            metal_value = Decimal("0")
            stone_value = Decimal("0")
            wastage = Decimal("0")
            making_charge = Decimal(self.making_charge or 0)

            subtotal = Decimal("0")
            cgst = Decimal("0")
            sgst = Decimal("0")

            # ==========================================================
            # 2 METAL CALCULATION
            # ==========================================================

            if commodity_type == "metal":

                gold_rate = Decimal(rate.unit_price)

                metal_value = gold_rate * weight

                wastage_percent = Decimal(rate.wastage_percent or 0)

                wastage = (metal_value * wastage_percent) / Decimal("100")

                subtotal = metal_value + wastage + making_charge

                cgst = (subtotal * cgst_percent) / Decimal("100")
                sgst = (subtotal * sgst_percent) / Decimal("100")

            # ==========================================================
            # 3 STONE CALCULATION
            # ==========================================================

            else:

                ratti_multiplier = Decimal(rate.ratti_multiplier or 0)

                carat_weight = weight * ratti_multiplier

                stone_value = carat_weight * Decimal(rate.unit_price)

                subtotal = stone_value

                cgst = (subtotal * cgst_percent) / Decimal("100")
                sgst = (subtotal * sgst_percent) / Decimal("100")

            # ==========================================================
            # 4 EXTRAS
            # ==========================================================

            extras = hallmark + packaging + delivery

            # ==========================================================
            # 5 BASE PRICE
            # ==========================================================

            base_price = subtotal + cgst + sgst + extras

            # ==========================================================
            # 6 DISCOUNT
            # ==========================================================

            discount_amount = (base_price * discount_percent) / Decimal("100")

            final_price = base_price - discount_amount

            final_price = quantize_money(final_price)

            # ==========================================================
            # 7 SAVE PRICE
            # ==========================================================

            self.price = final_price

            self.save(update_fields=["price", "updated_at"])

            # ==========================================================
            # 8 LOGGING
            # ==========================================================

            logger.info(
                f"""
    PRICE CALCULATION SUCCESS

    SKU : {self.sku_code}
    TYPE : {commodity_type}

    RATE : {rate.unit_price}
    WEIGHT : {weight}

    METAL VALUE : {metal_value}
    STONE VALUE : {stone_value}

    WASTAGE : {wastage}
    MAKING : {making_charge}

    SUBTOTAL : {subtotal}

    CGST : {cgst}
    SGST : {sgst}

    HALLMARK : {hallmark}
    PACKAGING : {packaging}
    DELIVERY : {delivery}

    BASE PRICE : {base_price}

    DISCOUNT % : {discount_percent}
    DISCOUNT AMOUNT : {discount_amount}

    FINAL PRICE : {final_price}
    """
            )

        except Exception as e:

            logger.error(
                f"Price calculation failed for SKU {self.sku_code}: {str(e)}",
                exc_info=True
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
                    with transaction.atomic():
                        logger.debug(f"[post_save Signal-{signal_id}] Processing SKU: {sku.sku_code}")
                        sku.recalculate_price_from_rate(instance)
                        successful_skus.append(sku.sku_code)
                        logger.debug(f"  ✓ Updated {sku.sku_code}: ₹{sku.price}")

                except Exception as sku_err:
                    logger.error(
                        f"[post_save Signal-{signal_id}] Failed to update SKU {sku.sku_code}: {str(sku_err)}. Transaction rolled back.",
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