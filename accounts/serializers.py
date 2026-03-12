# accounts/serializers.py
from rest_framework import serializers
from .models import User, Cart, CartItem, Wishlist, ShippingAddress, ProductReview
from inventory.models import ProductSKU, CommodityRate
from inventory.serializers import ProductSKUSerializer, CommodityRateSerializer
from orders.utils import calculate_sku_price

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "email", "full_name", "phone", "auth_provider", "is_verified")
        read_only_fields = ("id", "auth_provider", "is_verified")

class ShippingAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShippingAddress
        fields = "__all__"
        read_only_fields = ("id", "user", "created_at", "updated_at")

class UserUpdateSerializer(serializers.ModelSerializer):
    """
    If user updates phone or email → Must verify via OTP.
    Other fields can update normally.
    """
    class Meta:
        model = User
        fields = ("full_name", "email", "phone")

    def validate(self, attrs):
        user = self.instance

        # Email changed
        if "email" in attrs and attrs["email"] != user.email:
            attrs["is_verified"] = False   # Mark unverified
            # Trigger OTP (You will handle in view)
        
        # Phone changed
        if "phone" in attrs and attrs["phone"] != user.phone:
            attrs["is_verified"] = False
            # Trigger OTP

        return attrs

class ForgotPasswordSerializer(serializers.Serializer):
    email_or_phone = serializers.CharField()

class VerifyOTPSerializer(serializers.Serializer):
    email_or_phone = serializers.CharField()
    otp = serializers.CharField(max_length=10)

class ResetPasswordSerializer(serializers.Serializer):
    reset_token = serializers.CharField()
    new_password = serializers.CharField(min_length=6)

class CartItemSerializer(serializers.ModelSerializer):
    sku = ProductSKUSerializer(read_only=True)
    sku_id = serializers.PrimaryKeyRelatedField(
        queryset=ProductSKU.objects.all(), source='sku', write_only=True
    )
    subtotal = serializers.SerializerMethodField()
    commodity_rate = serializers.SerializerMethodField()   # NEW FIELD
    product_id = serializers.SerializerMethodField()
    product_slug = serializers.SerializerMethodField()
    pricing_details = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = [
            'id', 'sku', 'sku_id', 'quantity',
            'price_snapshot', 'subtotal', 'commodity_rate', 'product_id', 'product_slug', 'pricing_details'
        ]
        read_only_fields = ['price_snapshot']
    
    def get_product_id(self, obj):
        if obj.sku and obj.sku.product:
            return str(obj.sku.product.id)
        return None

    def get_pricing_details(self, obj):
        if not obj.sku:
            return None
        try:
            _, tax_details = calculate_sku_price(obj.sku)
            return tax_details
        except Exception:
            return {
                "method": "fallback",
                "unit_price": str(obj.sku.price),
                "discount_percent": str(obj.sku.discount_percent) if obj.sku.discount_percent is not None else "0"
            }

    def get_product_slug(self, obj):
        if obj.sku and obj.sku.product:
            return obj.sku.product.slug
        return None

    def get_subtotal(self, obj):
        return obj.quantity * obj.price_snapshot

    def get_commodity_rate(self, obj):
        """Return the latest active commodity rate for the SKU's variant."""
        variant = getattr(obj.sku, "variant", None)
        if not variant:
            return None

        latest_rate = (
            CommodityRate.objects
            .filter(variant=variant, is_active=True)
            .order_by("-effective_date")
            .first()
        )
        if not latest_rate:
            return None

        return CommodityRateSerializer(latest_rate).data



class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    grand_total = serializers.SerializerMethodField()
    total_items = serializers.SerializerMethodField()
    total_price = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = [
            'id',
            'items',
            'total_price',
            'grand_total',
            'total_items',
        ]

    def get_total_price(self, obj):
        return sum(i.quantity * i.price_snapshot for i in obj.items.all())

    def get_grand_total(self, obj):
        # Same as total price (taxes already included in price_snapshot)
        return self.get_total_price(obj)

    def get_total_items(self, obj):
        return sum(i.quantity for i in obj.items.all())


class WishlistSerializer(serializers.ModelSerializer):
    sku = ProductSKUSerializer(read_only=True)
    sku_id = serializers.PrimaryKeyRelatedField(
        queryset=ProductSKU.objects.all(), source='sku', write_only=True
    )

    class Meta:
        model = Wishlist
        fields = ['id', 'sku', 'sku_id', 'created_at']

# Reviwes and Comment 
class ProductReviewSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.get_full_name", read_only=True)
    user_id = serializers.UUIDField(source="user.id", read_only=True)

    class Meta:
        model = ProductReview
        fields = [
            "id",
            "sku",
            "user_id",
            "user_name",
            "rating",
            "comment",
            "is_verified_purchase",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "user_id",
            "user_name",
            "is_verified_purchase",
            "created_at",
        ]

    def validate_rating(self, value):
        if value < 1 or value > 5:
            raise serializers.ValidationError("Rating must be between 1 and 5")
        return value

    def create(self, validated_data):
        request = self.context["request"]
        validated_data["user"] = request.user
        return super().create(validated_data)