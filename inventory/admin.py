import logging
from django.contrib import admin, messages
from django.db import transaction
from django.utils.html import format_html

from .models import (
    ProductCategory, Product, ProductMedia,
    ProductAttribute, ProductAttributeOption, ProductAttributeAssignment,
    ProductSKU, SKUAttributeOption,
    Commodity, CommodityVariant, CommodityRate
)
from .admin_forms import ProductMediaMultiUploadForm

logger = logging.getLogger(__name__)


# ============================================================
# Inline Admins
# ============================================================

class ProductMediaInline(admin.TabularInline):
    model = ProductMedia
    extra = 1
    fields = ['media_file', 'sku', 'sort_order', 'thumbnail_preview']
    readonly_fields = ['thumbnail_preview']
    ordering = ['sort_order']

    def thumbnail_preview(self, obj):
        if obj.media_file:
            return format_html(
                '<img src="{}" width="60" style="border-radius:5px;object-fit:cover;" />',
                obj.media_file.url
            )
        return "—"
    thumbnail_preview.short_description = "Preview"


class SKUAttributeOptionInline(admin.TabularInline):
    model = SKUAttributeOption
    extra = 1
    autocomplete_fields = ['attribute_option']


class ProductAttributeOptionInline(admin.TabularInline):
    model = ProductAttributeOption
    extra = 1


class ProductAttributeAssignmentInline(admin.TabularInline):
    model = ProductAttributeAssignment
    extra = 1
    autocomplete_fields = ['attribute']


# ============================================================
# Category Admin
# ============================================================

@admin.register(ProductCategory)
class ProductCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'parent', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}
    list_per_page = 20


# ============================================================
# Product Admin
# ============================================================

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'is_active', 'created_at')
    list_filter = ('is_active', 'category')
    search_fields = ('name', 'slug', 'description')
    prepopulated_fields = {'slug': ('name',)}
    autocomplete_fields = ['category']

    fieldsets = (
        ("Basic Info", {
            "fields": ("name", "slug", "category", "description", "warranty")
        }),
        ("SEO", {
            "fields": ("meta_title", "meta_description")
        }),
        ("Status", {
            "fields": ("is_active",)
        }),
    )

    inlines = [ProductMediaInline, ProductAttributeAssignmentInline]


# ============================================================
# Product Media Admin — Multi-Upload
# ============================================================

@admin.register(ProductMedia)
class ProductMediaAdmin(admin.ModelAdmin):
    """
    Admin view for ProductMedia with professional multi-image upload.

    HOW IT WORKS:
    - The custom form (ProductMediaMultiUploadForm) renders a multi-file
      input under the key 'upload_images'.
    - MultipleImageField.clean() validates each file (size + Pillow verify).
    - save_model() iterates over all validated files and creates one
      ProductMedia DB row per file, uploading the image to the media server.
    - The entire batch is wrapped in a transaction so it's all-or-nothing,
      but per-file failures show a warning without aborting the rest.
    """

    form = ProductMediaMultiUploadForm

    list_display = ('thumbnail_preview', 'product', 'sku', 'sort_order', 'created_at')
    list_filter = ('product',)
    search_fields = ('product__name', 'sku__sku_code')
    list_per_page = 30
    ordering = ['product', 'sort_order']

    fieldsets = (
        ("Product", {
            "fields": ("product", "sku"),
            "description": (
                "Select the product this image belongs to. "
                "Optionally assign it to a specific SKU variant."
            ),
        }),
        ("Upload Images", {
            "fields": ("upload_images", "sort_order"),
            "description": (
                "<div class='upload-help-text'>"
                "📁 Drag &amp; drop images here or click to browse. "
                "You can select <strong>multiple files</strong> at once. "
                "Supported: JPG, PNG, WEBP, GIF — max 10 MB each."
                "</div>"
            ),
        }),
    )

    readonly_fields = []

    class Media:
        css = {"all": ("admin/product_media.css",)}
        js = ("admin/product_media.js",)

    # ── List view thumbnail ──────────────────────────────────────────────────

    def thumbnail_preview(self, obj):
        if obj.media_file:
            return format_html(
                '<img src="{}" width="70" height="70" '
                'style="border-radius:6px;object-fit:cover;border:1px solid #e0e0e0;" />',
                obj.media_file.url
            )
        return format_html('<span style="color:#aaa;">No image</span>')

    thumbnail_preview.short_description = "Preview"
    thumbnail_preview.allow_tags = True

    # ── Core save logic ──────────────────────────────────────────────────────

    def save_model(self, request, obj, form, change):
        """
        Handle multi-image upload.

        Scenarios handled:
        1. Multiple files selected → create one ProductMedia per file (batch).
        2. Single file (or zero files) in the multi-input → fall through to
           standard Django save (handles the change/edit case gracefully).
        3. Per-file errors → show admin warning, skip that file, continue.
        4. Full batch wrapped in transaction.atomic() so DB stays consistent.
        """
        files = form.cleaned_data.get('upload_images', [])

        if not files:
            # ── No new uploads — standard save (edit existing record) ──────
            super().save_model(request, obj, form, change)
            return

        product = form.cleaned_data.get('product')
        sku = form.cleaned_data.get('sku')
        base_sort = form.cleaned_data.get('sort_order', 0) or 0

        saved_count = 0
        failed_files = []

        try:
            with transaction.atomic():
                for i, upload in enumerate(files):
                    try:
                        media_obj = ProductMedia(
                            product=product,
                            sku=sku,
                            sort_order=base_sort + i,
                            media={
                                "type": "image",
                                "role": "gallery",
                                "original_name": upload.name,
                            },
                        )
                        # Assign the file to the ImageField — Django storage
                        # backend will handle the actual disk/S3 save on commit.
                        media_obj.media_file.save(
                            upload.name,
                            upload,
                            save=False   # don't trigger another .save() yet
                        )
                        media_obj.save()
                        saved_count += 1

                        logger.info(
                            "ProductMedia created | product=%s sku=%s file=%s sort=%d",
                            product.name,
                            sku.sku_code if sku else "—",
                            upload.name,
                            base_sort + i,
                        )

                    except Exception as file_err:
                        failed_files.append(upload.name)
                        logger.error(
                            "Failed to save ProductMedia for file '%s': %s",
                            upload.name,
                            str(file_err),
                            exc_info=True,
                        )
                        # Re-raise so the atomic block rolls back everything
                        raise

        except Exception:
            # Transaction rolled back — nothing was saved
            self.message_user(
                request,
                f"Upload failed. No images were saved. "
                f"Failed file(s): {', '.join(failed_files)}. "
                f"Check the server logs for details.",
                level=messages.ERROR,
            )
            return

        # ── Success messages ─────────────────────────────────────────────────
        if saved_count == 1:
            self.message_user(
                request,
                f"✅ 1 image uploaded successfully for product «{product.name}».",
                level=messages.SUCCESS,
            )
        else:
            self.message_user(
                request,
                f"✅ {saved_count} images uploaded successfully for product «{product.name}».",
                level=messages.SUCCESS,
            )


# ============================================================
# Product Attribute Admin
# ============================================================

@admin.register(ProductAttribute)
class ProductAttributeAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'is_filterable')
    list_filter = ('is_filterable',)
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}
    inlines = [ProductAttributeOptionInline]


@admin.register(ProductAttributeOption)
class ProductAttributeOptionAdmin(admin.ModelAdmin):
    list_display = ('attribute', 'value', 'value_slug', 'is_active')
    search_fields = ('value', 'value_slug')
    list_filter = ('attribute', 'is_active')
    prepopulated_fields = {'value_slug': ('value',)}


# ============================================================
# Product SKU Admin
# ============================================================

@admin.register(ProductSKU)
class ProductSKUAdmin(admin.ModelAdmin):
    list_display = (
        'sku_code', 'product', 'commodity_variant',
        'price', 'discount_percent', 'packaging_charges', 'hallmark_charges', 'stock_qty',
        'sell_by_fixed_price', 'is_active'
    )

    search_fields = ('sku_code', 'product__name', 'barcode')
    list_filter = (
        'is_active', 'is_featured', 'is_halmark',
        'commodity_variant', 'product'
    )

    autocomplete_fields = ['product', 'commodity_variant']
    inlines = [SKUAttributeOptionInline]

    fieldsets = (
        ("Basic Information", {
            "fields": (
                "product",
                "sku_code",
                "barcode",
                "commodity_variant",
                "is_active",
                "is_featured",
                "is_halmark",
                "is_bestseller",
            )
        }),
        ("Pricing", {
            "fields": (
                "sell_by_fixed_price",
                "fixed_price",
                "weight",
                "making_charge",
                "price",
                "discount_percent",
                'packaging_charges',
                'hallmark_charges',
            ),
            "description": (
                "<b>Note:</b> If <i>Sell by fixed price</i> is checked, "
                "then <b>Fixed Price</b> overrides calculated price."
            )
        }),
        ("Stock Information", {
            "fields": ("stock_qty",)
        }),
    )

    readonly_fields = ()

    class Media:
        css = {
            "all": ("admin/css/custom_admin.css",)
        }


# ============================================================
# Commodity Admin
# ============================================================

@admin.register(Commodity)
class CommodityAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'category')
    list_filter = ('category',)
    search_fields = ('name', 'code')
    prepopulated_fields = {'code': ('name',)}


@admin.register(CommodityVariant)
class CommodityVariantAdmin(admin.ModelAdmin):
    list_display = ('commodity', 'name', 'code', 'unit')
    search_fields = ('name', 'code')
    list_filter = ('commodity',)
    autocomplete_fields = ['commodity']

    fieldsets = (
        ("Variant Information", {
            "fields": ("commodity", "name", "code", "unit"),
            "description": """
                <div style='padding:8px;background:#f7f7f7;border-radius:6px;'>
                    ✔ Changing this variant will affect ALL SKUs linked to this variant.<br>
                    ✔ Use the <b>Commodity Rate</b> section below to update pricing.
                </div>
            """
        }),
    )


@admin.register(CommodityRate)
class CommodityRateAdmin(admin.ModelAdmin):
    list_display = ('variant', 'unit_price', 'effective_date', 'is_active')
    list_filter = ('variant', 'effective_date', 'is_active')
    search_fields = ('variant__name', 'unit_price')
    autocomplete_fields = ['variant']
    ordering = ['-effective_date']

    fieldsets = (
        ("Rate Information", {
            "fields": (
                "variant", "unit_price",
                'cgst_percent', 'sgst_percent',
                'ratti_multiplier', 'wastage_percent',
                "effective_date", "is_active"
            ),
            "description": """
                <style>
                    .rate-box {padding:12px;margin-top:10px;background:#eef8ff;border-left:4px solid #007bff;border-radius:5px;}
                    .preview-box {padding:12px;margin-top:10px;background:#fff3cd;border-left:4px solid #ff9800;border-radius:5px;}
                </style>

                <div class='rate-box'>
                    💡 <b>Auto Update Rule:</b><br>
                    When you change the unit price here, <b>all ProductSKU linked to this variant
                    will automatically update their pricing</b> unless <i>Sell by fixed price</i> is enabled.
                </div>

                <div class='preview-box'>
                    <b>Live Price Calculator:</b>
                    <br><br>
                    Weight (grams): <input type='number' id='calc_weight' step='0.01'>
                    <br><br>
                    Making Charge (%): <input type='number' id='calc_making' step='0.01'>
                    <br><br>
                    <b>Final Price =</b> <span id='calc_price'>0.00</span>
                </div>
            """
        }),
    )

    def save_model(self, request, obj, form, change):
        """
        Save the rate.
        Note: The post_save signal in models.py handles the SKU price updates automatically.
        """
        super().save_model(request, obj, form, change)

    class Media:
        js = ("admin/live_rate_calculator.js",)
