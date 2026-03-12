from django.contrib import admin
from .models import (
    ProductCategory, Product, ProductMedia,
    ProductAttribute, ProductAttributeOption, ProductAttributeAssignment,
    ProductSKU, SKUAttributeOption,
    Commodity, CommodityVariant, CommodityRate
)
from .admin_forms import ProductMediaMultiUploadForm
from .widgets import MultiFileInput

# ------------------------------------------------
# Inline Admins
# ------------------------------------------------

class ProductMediaInline(admin.TabularInline):
    model = ProductMedia
    extra = 1
    fields = ['media', 'sku', 'sort_order']
    ordering = ['sort_order']


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


# ------------------------------------------------
# Category Admin
# ------------------------------------------------

@admin.register(ProductCategory)
class ProductCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'parent', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}
    list_per_page = 20


# ------------------------------------------------
# Product Admin
# ------------------------------------------------

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


# ------------------------------------------------
# Product Media Admin
# ------------------------------------------------
@admin.register(ProductMedia)
class ProductMediaAdmin(admin.ModelAdmin):
    form = ProductMediaMultiUploadForm

    list_display = ('thumbnail', 'product', 'sku', 'sort_order')
    list_filter = ('product', 'sku')
    search_fields = ('product__name',)

    # Enable multiple file selection
    # def get_form(self, request, obj=None, **kwargs):
    #     form = super().get_form(request, obj, **kwargs)
    #     if 'upload_files' in form.base_fields:
    #         form.base_fields['upload_files'].widget.attrs.update({'multiple': True})
    #     return form

    # # FORCE MULTIPART ENCODING
    # def render_change_form(self, request, context, *args, **kwargs):
    #     if "adminform" in context:
    #         context["adminform"].form.enctype = "multipart/form-data"
    #     return super().render_change_form(request, context, *args, **kwargs)

    # # CRITICAL — Django admin won't create multipart form unless you override this
    # def add_view(self, request, form_url="", extra_context=None):
    #     request.META['CONTENT_TYPE'] = "multipart/form-data"
    #     return super().add_view(request, form_url, extra_context)

    # def change_view(self, request, object_id, form_url="", extra_context=None):
    #     request.META['CONTENT_TYPE'] = "multipart/form-data"
    #     return super().change_view(request, object_id, form_url, extra_context)
    
    # def get_changeform_initial_data(self, request):
    #     request._upload_handlers = None  # force file upload handlers
    #     return super().get_changeform_initial_data(request)

    # def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
    #     request.META['CONTENT_TYPE'] = "multipart/form-data"
    #     return super().changeform_view(request, object_id, form_url, extra_context)

    class Media:
        css = {"all": ("admin/product_media.css",)}
        js = ("admin/product_media.js",)

    # Save multiple uploaded files
    def save_model(self, request, obj, form, change):
        files = request.FILES.getlist('upload_files')

        if files:
            base_sort = form.cleaned_data.get('sort_order', 0)
            for i, f in enumerate(files):
                ProductMedia.objects.create(
                    product=form.cleaned_data['product'],
                    sku=form.cleaned_data['sku'],
                    media_file=f,
                    sort_order=base_sort + i,
                    media={"type": "image", "role": "gallery"}
                )
            return

        super().save_model(request, obj, form, change)


# ------------------------------------------------
# Product Attribute Admin
# ------------------------------------------------

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


# ------------------------------------------------
# Product SKU Admin
# ------------------------------------------------

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

    # ----- Form Layout -----
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

    # Make admin cleaner
    readonly_fields = ()

    class Media:
        """Optional: Slight UI improvement for admin spacing."""
        css = {
            "all": ("admin/css/custom_admin.css",)
        }


# ------------------------------------------------
# Commodity Admin
# ------------------------------------------------

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

    # Live preview help text
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
            "fields": ("variant", "unit_price", 'cgst_percent', 'sgst_percent', 'ratti_multiplier','wastage_percent', "effective_date", "is_active"),
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
