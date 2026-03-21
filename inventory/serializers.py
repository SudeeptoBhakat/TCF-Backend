from rest_framework import serializers
from .models import ProductCategory, Product, ProductMedia, ProductSKU, SKUAttributeOption, ProductAttribute, ProductAttributeOption, CommodityVariant, CommodityRate, ProductVideo
from orders.utils import calculate_sku_price

class ProductCategoryListSerilizer(serializers.ModelSerializer):
    children = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()

    class Meta:
        model = ProductCategory
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "image",
            "children"
        ]

    def get_children(self, obj):
        qs = obj.children.filter(is_active=True)
        return ProductCategoryListSerilizer(qs, many=True).data

    def get_image(self, obj):
        if obj.image:
            return obj.image.url
        return None
    

class ProductMediaSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()

    class Meta:
        model = ProductMedia
        fields = ["id", "image", "sort_order"]

    def get_image(self, obj):
        if not obj.media_file:
            return None

        request = self.context.get("request")
        if request:
            return request.build_absolute_uri(obj.media_file.url)

        return obj.media_file.url
    
    
class SKUAttributeOptionSerializer(serializers.ModelSerializer):
    attribute = serializers.SerializerMethodField()
    value = serializers.SerializerMethodField()

    class Meta:
        model = SKUAttributeOption
        fields = ["attribute", "value"]

    def get_attribute(self, obj):
        return obj.attribute_option.attribute.name

    def get_value(self, obj):
        return obj.attribute_option.value


class CommodityVariantSerializer(serializers.ModelSerializer):
    latest_rate = serializers.SerializerMethodField()

    class Meta:
        model = CommodityVariant
        fields = ["id", "name", "code", "unit", "latest_rate"]

    def get_latest_rate(self, obj):
        rate = obj.rates.filter(is_active=True).order_by("-effective_date").first()
        if rate:
            return {
                "unit_price": rate.unit_price,
                "effective_date": rate.effective_date
            }
        return None
    

class ProductSKUSerializer(serializers.ModelSerializer):
    attributes = SKUAttributeOptionSerializer(
        many=True,
        source="sku_attribute_options"
    )
    commodity = CommodityVariantSerializer(source="commodity_variant")
    product_name = serializers.CharField(source='product.name', read_only=True)
    image = serializers.SerializerMethodField()
    pricing_details = serializers.SerializerMethodField()
    
    class Meta:
        model = ProductSKU
        fields = [
            "id",
            "sku_code",
            "barcode",
            "weight",
            "making_charge",
            "price",
            "discount_percent",
            "sell_by_fixed_price",
            "fixed_price",
            "stock_qty",
            "is_halmark",
            "is_bestseller",
            "is_featured",
            "attributes",
            "commodity",
            "product_name",
            "image",
            "pricing_details",
        ]

    def get_image(self, obj):
        # Return the first media image associated with this SKU, 
        # or fall back to the product's first media if SKU has no specific media.
        media = obj.media.first()
        if media and media.media_file:
            return media.media_file.url
        
        # Fallback to product media
        product_media = obj.product.media.first()
        if product_media and product_media.media_file:
            return product_media.media_file.url
        return None

    def get_pricing_details(self, obj):
        try:
            breakdown = obj.get_price_breakdown()
            return {
                "sku": obj.sku_code,
                "price_breakdown": breakdown
            }
        except Exception:
            return {
                "sku": obj.sku_code,
                "price_breakdown": {
                    "method": "fallback",
                    "final_price": float(obj.price or 0)
                }
            }


class ProductVideoSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductVideo
        fields = [
            "id",
            "video_url",
            "platform",
            "is_homepage_featured",
            "is_boosting_video"
        ]

class ProductListSerializer(serializers.ModelSerializer):
    category = serializers.CharField(source="category.name", default=None)
    media = ProductMediaSerializer(many=True)
    skus = ProductSKUSerializer(many=True)
    videos = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "warranty",
            "meta_title",
            "meta_description",
            "category",
            "media",
            "skus",
            "videos",
        ]
        
    def get_videos(self, obj):
        videos = [v for v in obj.videos.all() if v.is_active]
        if videos:
            return ProductVideoSerializer(videos, many=True).data
        
        request = self.context.get("request")
        if request and hasattr(request, "boosting_videos"):
            if request.boosting_videos is not None:
                return ProductVideoSerializer(request.boosting_videos, many=True).data
                
        # Fallback if request is not populated with boosting_videos
        boosting_videos = ProductVideo.objects.filter(is_boosting_video=True, is_active=True)
        return ProductVideoSerializer(boosting_videos, many=True).data

class CommodityRateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CommodityRate
        fields = [
            "unit_price",
            "cgst_percent",
            "sgst_percent",
            "delivery_charges",
            "packaging_charges",
            "ratti_multiplier",
            "wastage_percent",
            "hallmark_charges",
            "effective_date",
            "source",
        ]

class ProductSearchSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for search suggestions.
    - Minimal data for fast loading
    - Only first image, first SKU price
    """
    category = serializers.CharField(source="category.name", read_only=True)
    image = serializers.SerializerMethodField()
    price = serializers.SerializerMethodField()
    discount_percent = serializers.SerializerMethodField()
    has_stock = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "category",
            "image",
            "price",
            "discount_percent",
            "has_stock",
        ]

    def get_image(self, obj):
        """Return first media image for the product."""
        media = obj.media.first()
        if media and media.media_file:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(media.media_file.url)
            return media.media_file.url
        return None

    def get_price(self, obj):
        """Return the first active SKU's price."""
        sku = obj.skus.filter(is_active=True).first()
        if sku:
            return str(sku.price)
        return None

    def get_discount_percent(self, obj):
        """Return the first active SKU's discount percent."""
        sku = obj.skus.filter(is_active=True).first()
        if sku and sku.discount_percent is not None:
            return str(sku.discount_percent)
        return None

    def get_has_stock(self, obj):
        """Check if product has any stock available."""
        return obj.skus.filter(is_active=True, stock_qty__gt=0).exists()
