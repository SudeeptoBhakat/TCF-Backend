from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _
from .models import User, AuthProvider, ProductReview


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    # Fields to display in the list view
    list_display = (
        "id",
        "full_name",
        "email",
        "phone",
        "auth_provider",
        "is_verified",
        "is_active",
        "is_staff",
        "created_at",
    )
    list_filter = ("auth_provider", "is_verified", "is_active", "is_staff", "created_at")
    search_fields = ("email", "phone", "full_name")
    ordering = ("-created_at",)

    readonly_fields = ("created_at", "updated_at")

    # How the fields are grouped in the admin detail page
    fieldsets = (
        (_("Personal Info"), {"fields": ("full_name", "email", "phone", "auth_provider")}),
        (_("Permissions"), {"fields": ("is_active", "is_verified", "is_staff", "is_superuser", "groups", "user_permissions")}),
        (_("Important Dates"), {"fields": ("last_login", "created_at", "updated_at")}),
    )

    # Fields shown while adding a new user via admin
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("full_name", "email", "phone", "password1", "password2", "auth_provider", "is_active", "is_staff"),
            },
        ),
    )

    # Customization for readability
    def get_fieldsets(self, request, obj=None):
        """Return fieldsets for add or change view"""
        if not obj:
            return self.add_fieldsets
        return super().get_fieldsets(request, obj)

from django.contrib import admin
from django.utils.html import format_html

from .models import (
    Cart,
    CartItem,
    Wishlist,
    ShippingAddress,
)


# -----------------------------------
# Shipping Address Admin
# -----------------------------------
@admin.register(ShippingAddress)
class ShippingAddressAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "label",
        "full_name",
        "phone",
        "city",
        "state",
        "pincode",
        "is_default",
        "is_active",
        "created_at",
    )
    list_filter = ("is_default", "is_active", "country", "state", "city")
    search_fields = (
        "user__email",
        "user__phone",
        "full_name",
        "phone",
        "city",
        "pincode",
    )
    readonly_fields = ("id", "created_at", "updated_at")
    ordering = ("-created_at",)
    autocomplete_fields = ("user",)

    fieldsets = (
        ("User", {"fields": ("user", "label", "is_default", "is_active")}),
        ("Contact", {"fields": ("full_name", "phone")}),
        ("Address", {
            "fields": (
                "address_line1",
                "address_line2",
                "city",
                "state",
                "pincode",
                "country",
            )
        }),
        ("System", {"fields": ("id", "created_at", "updated_at")}),
    )


# -----------------------------------
# Wishlist Admin
# -----------------------------------
@admin.register(Wishlist)
class WishlistAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "sku",
        "product_name",
        "is_active",
        "created_at",
    )
    list_filter = ("is_active", "created_at")
    search_fields = (
        "user__email",
        "user__phone",
        "sku__sku_code",
        "sku__product__name",
    )
    readonly_fields = ("id", "created_at")
    autocomplete_fields = ("user", "sku")
    ordering = ("-created_at",)

    def product_name(self, obj):
        return obj.sku.product.name if obj.sku and obj.sku.product else "-"
    product_name.short_description = "Product"


# -----------------------------------
# Cart Item Inline
# -----------------------------------
class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    readonly_fields = ("id", "price_snapshot", "created_at")
    autocomplete_fields = ("sku",)
    fields = (
        "sku",
        "quantity",
        "price_snapshot",
        "created_at",
    )


# -----------------------------------
# Cart Admin
# -----------------------------------
@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "item_count",
        "total_value",
        "is_active",
        "created_at",
        "updated_at",
    )
    list_filter = ("is_active", "created_at")
    search_fields = (
        "user__email",
        "user__phone",
    )
    readonly_fields = ("id", "created_at", "updated_at")
    autocomplete_fields = ("user",)
    inlines = (CartItemInline,)
    ordering = ("-updated_at",)

    def item_count(self, obj):
        return obj.items.count()
    item_count.short_description = "Items"

    def total_value(self, obj):
        total = sum(
            (item.price_snapshot * item.quantity)
            for item in obj.items.all()
        )
        return f"₹ {total:.2f}"
    total_value.short_description = "Cart Total"


# -----------------------------------
# Cart Item Admin (Optional Standalone)
# -----------------------------------
@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "cart",
        "sku",
        "product_name",
        "quantity",
        "price_snapshot",
        "created_at",
    )
    list_filter = ("created_at",)
    search_fields = (
        "cart__user__email",
        "cart__user__phone",
        "sku__sku_code",
        "sku__product__name",
    )
    readonly_fields = ("id", "created_at")
    autocomplete_fields = ("cart", "sku")
    ordering = ("-created_at",)

    def product_name(self, obj):
        return obj.sku.product.name if obj.sku and obj.sku.product else "-"
    product_name.short_description = "Product"


# Product Reviews
@admin.register(ProductReview)
class ProductReviewAdmin(admin.ModelAdmin):
    """
    Admin configuration for Product Reviews
    """

    # ========= LIST VIEW =========
    list_display = (
        "id",
        "sku",
        "user",
        "rating",
        "is_verified_purchase",
        "is_active",
        "created_at",
    )

    list_filter = (
        "is_verified_purchase",
        "is_active",
        "rating",
        "created_at",
    )

    search_fields = (
        "sku__sku_code",
        "sku__product__name",
        "user__email",
        "user__username",
        "comment",
    )

    ordering = ("-created_at",)

    # ========= EDIT VIEW =========
    readonly_fields = (
        "id",
        "sku",
        "user",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        ("Review Information", {
            "fields": (
                "sku",
                "user",
                "rating",
                "comment",
            )
        }),
        ("Moderation", {
            "fields": (
                "is_verified_purchase",
                "is_active",
            )
        }),
        ("Timestamps", {
            "fields": (
                "created_at",
                "updated_at",
            )
        }),
    )

    # ========= ADMIN ACTIONS =========
    actions = [
        "approve_reviews",
        "unapprove_reviews",
        "disable_reviews",
        "enable_reviews",
    ]

    def approve_reviews(self, request, queryset):
        updated = queryset.update(is_verified_purchase=True)
        self.message_user(
            request,
            f"{updated} review(s) approved successfully."
        )
    approve_reviews.short_description = "Approve selected reviews"

    def unapprove_reviews(self, request, queryset):
        updated = queryset.update(is_verified_purchase=False)
        self.message_user(
            request,
            f"{updated} review(s) unapproved."
        )
    unapprove_reviews.short_description = "Unapprove selected reviews"

    def disable_reviews(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(
            request,
            f"{updated} review(s) disabled."
        )
    disable_reviews.short_description = "Disable selected reviews"

    def enable_reviews(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(
            request,
            f"{updated} review(s) enabled."
        )
    enable_reviews.short_description = "Enable selected reviews"
