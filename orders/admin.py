from django.contrib import admin
from django.utils.html import format_html

from .models import (
    Order, OrderItem,
    Payment, PaymentMethod,
    Invoice,
    Shipment
)

# =========================
# Inline Admins
# =========================

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = (
        'sku', 'product_name', 'quantity',
        'unit_price', 'discount', 'subtotal',
        'created_at'
    )
    can_delete = False


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    readonly_fields = (
        'amount', 'currency', 'status',
        'razorpay_order_id', 'razorpay_payment_id',
        'created_at', 'paid_at'
    )
    can_delete = False


class ShipmentInline(admin.TabularInline):
    model = Shipment
    extra = 0


# =========================
# Order Admin
# =========================

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        'order_number',
        'user',
        'status',
        'payment_status',
        'total_amount',
        'created_at'
    )

    list_filter = (
        'status',
        'payment_status',
        'created_at'
    )

    search_fields = (
        'order_number',
        'user__email',
        'user__phone'
    )

    readonly_fields = (
        'id',
        'order_number',
        'user',
        'total_amount',
        'created_at',
        'updated_at'
    )

    fieldsets = (
        ("Order Info", {
            'fields': (
                'order_number',
                'user',
                'shipping_address'
            )
        }),
        ("Status", {
            'fields': (
                'status',
                'payment_status',
                'is_active'
            )
        }),
        ("Amount", {
            'fields': ('total_amount',)
        }),
        ("Timestamps", {
            'fields': ('created_at', 'updated_at')
        }),
    )

    inlines = [OrderItemInline, PaymentInline, ShipmentInline]
    ordering = ('-created_at',)

    def has_delete_permission(self, request, obj=None):
        return False  # Prevent deleting orders in admin


# =========================
# Order Item Admin
# =========================

@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = (
        'order',
        'product_name',
        'sku',
        'quantity',
        'subtotal'
    )

    search_fields = (
        'order__order_number',
        'product_name',
        'sku__sku_code'
    )

    readonly_fields = [field.name for field in OrderItem._meta.fields]


# =========================
# Payment Method Admin
# =========================

@admin.register(PaymentMethod)
class PaymentMethodAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'provider', 'is_active')
    list_filter = ('code', 'is_active')
    search_fields = ('name', 'provider')


# =========================
# Payment Admin
# =========================

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'order',
        'amount',
        'currency',
        'status',
        'created_at'
    )

    list_filter = (
        'status',
        'currency',
        'created_at'
    )

    search_fields = (
        'razorpay_order_id',
        'razorpay_payment_id',
        'order__order_number'
    )

    readonly_fields = (
        'id',
        'razorpay_order_id',
        'razorpay_payment_id',
        'razorpay_signature',
        'provider_payload',
        'created_at',
        'paid_at',
        'verified_at'
    )

    fieldsets = (
        ("Order Info", {
            'fields': ('order', 'payment_method')
        }),
        ("Razorpay Details", {
            'fields': (
                'razorpay_order_id',
                'razorpay_payment_id',
                'razorpay_signature'
            )
        }),
        ("Amount", {
            'fields': ('amount', 'currency')
        }),
        ("Status", {
            'fields': ('status', 'error_code', 'error_description')
        }),
        ("Timestamps", {
            'fields': ('created_at', 'paid_at', 'verified_at')
        }),
    )


# =========================
# Invoice Admin
# =========================

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = (
        'invoice_number',
        'order',
        'user',
        'currency',
        'created_at'
    )

    search_fields = (
        'invoice_number',
        'order__order_number',
        'user__email'
    )

    readonly_fields = (
        'id',
        'invoice_number',
        'created_at'
    )


# =========================
# Shipment Admin
# =========================

@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    list_display = (
        'order',
        'carrier',
        'tracking_number',
        'status',
        'estimated_delivery_date'
    )

    list_filter = ('status', 'carrier')
    search_fields = ('tracking_number', 'order__order_number')
