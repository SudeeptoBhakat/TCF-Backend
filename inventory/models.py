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
from inventory.utils import calculate_sku_price, get_latest_rate_for_variant
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
                
            from inventory.utils import get_latest_rate_for_variant
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
        if not kwargs.get("update_fields") or "price" in kwargs.get("update_fields", []):
            if self.sell_by_fixed_price:
                self.price = Decimal(str(self.fixed_price or 0))
            else:
                if not self.commodity_variant:
                    logger.warning(f"No commodity variant for {self.sku_code}. Skipping price calculation.")
                    if self.price is None:
                        self.price = Decimal("0")
                else:
                    try:
                        from inventory.utils import calculate_sku_price
                        final_price, _ = calculate_sku_price(self)
                        self.price = final_price
                        logger.info(f"Auto-calculated price for {self.sku_code}: {self.price}")
                    except Exception as e:
                        logger.error(f"Failed to calculate price on save for {self.sku_code}: {str(e)}")
                        if self.price is None:
                            self.price = Decimal("0")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.sku_code} - {self.product.name}"
    
    def get_price_breakdown(self, rate=None):
        from decimal import Decimal, ROUND_HALF_UP

        def quantize_money(value: Decimal) -> Decimal:
            return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        if self.sell_by_fixed_price and self.fixed_price is not None:
            final_price = float(quantize_money(Decimal(str(self.fixed_price))))
            return {
                "method": "fixed_price",
                "gold_rate": 0,
                "weight": float(self.weight or 0),
                "metal_value": 0,
                "stone_value": 0,
                "wastage": 0,
                "making_charge": 0,
                "subtotal": final_price,
                "cgst": 0,
                "sgst": 0,
                "hallmark": 0,
                "packaging": 0,
                "delivery": 0,
                "base_price": final_price,
                "discount_percent": 0,
                "discount_amount": 0,
                "final_price": final_price
            }

        variant = self.commodity_variant
        if not variant:
            raise ValueError("Missing Commodity Variant")

        if not rate:
            from inventory.models import CommodityRate
            rate = CommodityRate.objects.filter(variant=variant, is_active=True).order_by("-effective_date").first()
        if not rate or rate.unit_price <= 0:
            raise ValueError("Missing Commodity Rate")

        discount_percent = Decimal(str(self.discount_percent or 0))
        weight = Decimal(str(self.weight or 0))
        hallmark = Decimal(str(self.hallmark_charges or 0))
        packaging = Decimal(str(self.packaging_charges or 0))
        making_charge = Decimal(str(self.making_charge or 0))
        delivery = Decimal("0.00")

        if weight == 0 and making_charge == 0 and hallmark == 0 and packaging == 0:
            return {
                "gold_rate": float(rate.unit_price) if variant.commodity.category == "metal" else 0,
                "weight": 0.0,
                "metal_value": 0.0,
                "stone_value": 0.0,
                "wastage": 0.0,
                "making_charge": 0.0,
                "subtotal": 0.0,
                "cgst": 0.0,
                "sgst": 0.0,
                "hallmark": 0.0,
                "packaging": 0.0,
                "delivery": 0.0,
                "base_price": 0.0,
                "discount_percent": float(discount_percent),
                "discount_amount": 0.0,
                "final_price": 0.0
            }

        commodity_type = variant.commodity.category
        metal_value = Decimal("0")
        stone_value = Decimal("0")
        wastage = Decimal("0")
        subtotal = Decimal("0")

        cgst_percent = Decimal(str(rate.cgst_percent or Decimal("1.5")))
        sgst_percent = Decimal(str(rate.sgst_percent or Decimal("1.5")))

        if commodity_type == "metal":
            gold_rate = Decimal(str(rate.unit_price))
            metal_value = gold_rate * weight
            wastage_percent = Decimal(str(rate.wastage_percent or 0))
            wastage = (metal_value * wastage_percent) / Decimal("100")
            subtotal = metal_value + wastage + making_charge
            cgst = (subtotal * cgst_percent) / Decimal("100")
            sgst = (subtotal * sgst_percent) / Decimal("100")
        else:
            ratti_multiplier = Decimal(str(rate.ratti_multiplier or 0))
            carat_weight = weight * ratti_multiplier
            stone_value = quantize_money(carat_weight * Decimal(str(rate.unit_price)))
            subtotal = stone_value
            cgst = (subtotal * cgst_percent) / Decimal("100")
            sgst = (subtotal * sgst_percent) / Decimal("100")

        extras = hallmark + packaging + delivery
        base_price = subtotal + cgst + sgst + extras

        # Discount is rounded to nearest integer (as per the expected 60321 price)
        discount_amount = ((base_price * discount_percent) / Decimal("100")).quantize(Decimal("1."), rounding=ROUND_HALF_UP)
        final_price = base_price - discount_amount

        return {
            "gold_rate": float(rate.unit_price) if commodity_type == "metal" else 0,
            "weight": float(weight),
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
            "final_price": float(quantize_money(final_price))
        }



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
            skus_to_update = []
            
            from inventory.utils import calculate_sku_price

            for sku in skus:
                try:
                    final_price, _ = calculate_sku_price(sku, rate=instance)
                    sku.price = final_price
                    sku.updated_at = timezone.now()
                    skus_to_update.append(sku)
                    successful_skus.append(sku.sku_code)
                    logger.debug(f"  ✓ Calculated {sku.sku_code}: ₹{sku.price}")
                except Exception as sku_err:
                    logger.error(
                        f"[post_save Signal-{signal_id}] Failed to calculate SKU {sku.sku_code}: {str(sku_err)}",
                        exc_info=True
                    )
                    failed_skus.append((sku.sku_code, str(sku_err)))
            
            if skus_to_update:
                ProductSKU.objects.bulk_update(skus_to_update, ['price', 'updated_at'])

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

# =====================================================================
# PRODUCT VIDEO
# =====================================================================
class ProductVideo(TimestampedModel):
    """
    Video links for products, boosting videos, or homepage featured videos.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="videos"
    )
    
    video_url = models.URLField(max_length=500, help_text="Link to YouTube, Instagram, Facebook, etc.")
    
    PLATFORM_CHOICES = [
        ("youtube", "YouTube"),
        ("instagram", "Instagram"),
        ("facebook", "Facebook"),
        ("vimeo", "Vimeo"),
        ("other", "Other"),
    ]
    platform = models.CharField(max_length=50, choices=PLATFORM_CHOICES, default="youtube")
    
    is_homepage_featured = models.BooleanField(
        default=False,
        help_text="Show this video on the home page."
    )
    is_boosting_video = models.BooleanField(
        default=False,
        help_text="Show this video on products that do not have their own specific videos."
    )
    
    is_active = models.BooleanField(default=True)
    
    class Meta:
        db_table = "product_videos"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["product"]),
            models.Index(fields=["is_homepage_featured"]),
            models.Index(fields=["is_boosting_video"]),
        ]

    def __str__(self):
        if self.product:
            desc = f"Video for {self.product.name}"
        elif self.is_homepage_featured:
            desc = "Homepage Featured Video"
        elif self.is_boosting_video:
            desc = "Boosting Video"
        else:
            desc = "Unassigned Video"
        return f"{self.get_platform_display()} - {desc}"