import logging
from django.contrib import admin, messages
from django.db import transaction
from django.utils.html import format_html

from .models import (
    ProductCategory, Product, ProductMedia,
    ProductAttribute, ProductAttributeOption, ProductAttributeAssignment,
    ProductSKU, SKUAttributeOption,
    Commodity, CommodityVariant, CommodityRate, ProductVideo
)
from .admin_forms import ProductMediaMultiUploadForm, ProductCategoryForm

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
    form = ProductCategoryForm
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
        ("Product Assignment", {
            "fields": ("product", "sku"),
            "description": "Select the product and (optional) SKU for the images below.",
        }),
        ("Upload Images", {
            "fields": ("upload_images",),
            "description": "Click 'Choose Files' to select one or multiple images.",
        }),
        ("Replace Existing Image", {
            "fields": ("media_file",),
            "classes": ("collapse",),
            "description": "Use this only when replacing an existing image.",
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
        Three scenarios:

        A. ADD with upload_images files  → one ProductMedia row per file.
           Each file is written to MEDIA_ROOT via ImageField.save() then the
           DB row is committed. All wrapped in transaction.atomic().

        B. ADD with no files (edge case) → standard single-record Django save.

        C. CHANGE (edit existing record) → standard save; existing media_file
           is preserved / replaced via the ClearableFileInput widget.
        """
        files = form.cleaned_data.get('upload_images', [])

        if not files:
            # Scenario B or C — no multi-upload; normal Django admin save
            super().save_model(request, obj, form, change)
            return

        # Scenario A — batch multi-upload (add view)
        product = form.cleaned_data.get('product')
        sku = form.cleaned_data.get('sku')
        base_sort = form.cleaned_data.get('sort_order', 0) or 0
        saved_count = 0

        try:
            with transaction.atomic():
                for i, upload in enumerate(files):
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
                    # Step 1: write the file to MEDIA_ROOT/products/media/
                    #         save=False → don't call media_obj.save() yet
                    media_obj.media_file.save(upload.name, upload, save=False)

                    # Step 2: commit the DB row (media_file path already set)
                    media_obj.save()
                    saved_count += 1

                    logger.info(
                        "ProductMedia created | product=%s sku=%s file=%s sort=%d",
                        product.name,
                        sku.sku_code if sku else "none",
                        upload.name,
                        base_sort + i,
                    )

        except Exception as exc:
            logger.error(
                "Batch upload failed after %d file(s) — rolled back: %s",
                saved_count, str(exc), exc_info=True,
            )
            self.message_user(
                request,
                f"Upload failed — no images were saved. Error: {exc}",
                level=messages.ERROR,
            )
            return

        noun = "image" if saved_count == 1 else "images"
        self.message_user(
            request,
            f"\u2705 {saved_count} {noun} uploaded successfully for \u00ab{product.name}\u00bb.",
            level=messages.SUCCESS,
        )
        # The batch save is complete — do NOT call super().save_model()
        # because obj was never assigned a media_file and would create an empty row.


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


# ============================================================
# Product Video Admin
# ============================================================

@admin.register(ProductVideo)
class ProductVideoAdmin(admin.ModelAdmin):
    list_display = (
        'platform_icon', 'product', 'is_homepage_featured', 
        'is_boosting_video', 'is_active', 'created_at'
    )
    list_filter = ('platform', 'is_homepage_featured', 'is_boosting_video', 'is_active')
    search_fields = ('product__name', 'video_url')
    autocomplete_fields = ['product']
    
    fieldsets = (
        ("Video Source", {
            "fields": ("video_url", "platform"),
            "description": "Provide a link to the video (YouTube, Instagram, etc.). Do not upload video files directly."
        }),
        ("Placement Options", {
            "fields": ("product", "is_homepage_featured", "is_boosting_video"),
            "description": """
                <ul>
                <li><b>Product:</b> Show video only on this specific product's page.</li>
                <li><b>Is boosting video:</b> Show this video as a fallback on products that don't have their own video.</li>
                <li><b>Is homepage featured:</b> Pin this video to the homepage featuring section.</li>
                </ul>
            """
        }),
        ("Status", {
            "fields": ("is_active",)
        }),
    )

    def platform_icon(self, obj):
        return format_html(
            f'<b>{obj.get_platform_display()}</b>'
        )
    platform_icon.short_description = "Platform"
