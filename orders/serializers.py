import uuid
from rest_framework import serializers

from accounts.models import ShippingAddress
from inventory.models import ProductSKU
from .models import Order, OrderItem, OrderStatus, Invoice
from inventory.serializers import ProductSKUSerializer
from accounts.serializers import UserSerializer, ShippingAddressSerializer
from .utils import calculate_sku_price, quantize_money

# Order Item Serializer
from django.db import transaction
from rest_framework import serializers
from decimal import Decimal
import uuid

class OrderItemSerializer(serializers.ModelSerializer):
    sku = serializers.PrimaryKeyRelatedField(queryset=ProductSKU.objects.all(), write_only=True)
    sku_details = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = OrderItem
        fields = [
            "id",
            "sku",             # write-only PK
            "sku_details",     # read-only nested sku info
            "product_name",
            "quantity",
            "unit_price",
            "discount",
            "subtotal",
            "tax_details",
            "created_at",
        ]
        read_only_fields = ["id", "created_at", "unit_price", "subtotal", "tax_details"]

    def get_sku_details(self, obj):
        sku = getattr(obj, "sku", None)
        if not sku:
            return None
        # return minimal sku info; adapt to your ProductSKUSerializer if needed
        return {
            "id": str(sku.id),
            "sku_code": sku.sku_code,
            "product_name": sku.product.name,
            "stock_qty": sku.stock_qty,
        }

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("Quantity must be at least 1.")
        return value


# class OrderSerializer(serializers.ModelSerializer):
#     user = UserSerializer(read_only=True)
#     items = OrderItemSerializer(many=True)
#     shipping_address = ShippingAddressSerializer(read_only=True)
#     shipping_address_id = serializers.PrimaryKeyRelatedField(
#         queryset=ShippingAddress.objects.all(),
#         write_only=True,
#         source="shipping_address"
#     )

#     class Meta:
#         model = Order
#         fields = [
#             "id",
#             "order_number",
#             "user",
#             "shipping_address",
#             "shipping_address_id",
#             "status",
#             "payment_status",
#             "total_amount",
#             "is_active",
#             "items",
#             "created_at",
#             "updated_at",
#         ]
#         read_only_fields = [
#             "id", "created_at", "updated_at", "order_number",
#             "status", "payment_status", "total_amount"
#         ]

#     def validate(self, attrs):
#         items = attrs.get("items", [])
#         if not items:
#             raise serializers.ValidationError("Order must contain at least one item.")
#         return attrs

#     @transaction.atomic
#     def create(self, validated_data):
#         """
#         Create Order:
#          - Validate stock (with SELECT FOR UPDATE)
#          - Compute backend unit_price, tax_details, subtotal per item
#          - Decrement stock atomically
#          - Save order and order items
#         """
#         request = self.context.get("request")
#         user = request.user

#         items_data = validated_data.pop("items")
#         validated_data["user"] = user
#         validated_data["order_number"] = f"ORD-{uuid.uuid4().hex[:10].upper()}"

#         # create order placeholder with zero amount
#         order = Order.objects.create(**validated_data, total_amount=Decimal("0.00"))

#         total_amount = Decimal("0.00")

#         # Lock all SKUs involved to avoid race conditions.
#         sku_ids = [
#             i["sku"].id if isinstance(i["sku"], ProductSKU) else i["sku"].pk
#             for i in items_data
#         ]

#         # FIXED: remove select_related() from lock query
#         skus_qs = (
#             ProductSKU.objects
#             .filter(pk__in=sku_ids)
#             .select_for_update()
#         )

#         # optional: load related objects AFTER locking
#         skus_qs = skus_qs.select_related("commodity_variant", "product")

#         skus_map = {str(s.id): s for s in skus_qs}


#         # Process each item
#         for item in items_data:
#             sku_obj = item["sku"] if isinstance(item["sku"], ProductSKU) else skus_map.get(str(item["sku"].pk))
#             qty = int(item["quantity"])

#             if sku_obj is None:
#                 raise serializers.ValidationError("Invalid SKU provided.")

#             # STOCK validation
#             if sku_obj.stock_qty < qty:
#                 raise serializers.ValidationError(f"Only {sku_obj.stock_qty} items available for SKU {sku_obj.sku_code}.")

#             # compute price and tax via helper (ensures consistent logic)
#             try:
#                 unit_price, tax_details = calculate_sku_price(sku_obj)
#             except Exception as e:
#                 raise serializers.ValidationError(f"Price calculation failed for SKU {sku_obj.sku_code}: {str(e)}")

#             # discount handling: use sku.discount_price if available or 0
#             discount = getattr(sku_obj, "discount_price", None) or Decimal("0.00")
#             if discount is None:
#                 discount = Decimal("0.00")
#             # ensure discount <= unit_price
#             unit_price = Decimal(unit_price)
#             discount = Decimal(discount)
#             if discount > unit_price:
#                 discount = Decimal("0.00")

#             item_subtotal = quantize_money((unit_price - discount) * qty)

#             # Decrement stock
#             sku_obj.stock_qty = sku_obj.stock_qty - qty
#             sku_obj.save(update_fields=["stock_qty", "updated_at"])

#             # Create order item (snapshot)
#             product_name = item.get("product_name") or sku_obj.product.name
#             OrderItem.objects.create(
#                 order=order,
#                 sku=sku_obj,
#                 product_name=product_name,
#                 quantity=qty,
#                 unit_price=quantize_money(unit_price),
#                 discount=quantize_money(discount),
#                 subtotal=item_subtotal,
#                 tax_details=tax_details,
#             )

#             total_amount += item_subtotal

#         order.total_amount = quantize_money(total_amount)
#         order.save(update_fields=["total_amount", "updated_at"])

#         return order

#     def update(self, instance, validated_data):
#         """
#         Allow update only in PENDING status (owner).
#         Replace items safely: restore stock of old items, then re-validate and apply new items.
#         """
#         request = self.context.get("request")
#         user = request.user

#         if instance.user_id != user.id:
#             raise serializers.ValidationError("You cannot modify this order.")

#         if instance.status != OrderStatus.PENDING:
#             raise serializers.ValidationError("Only pending orders can be modified.")

#         items_data = validated_data.pop("items", None)
#         if items_data is None:
#             # only update non-item fields
#             for attr, value in validated_data.items():
#                 setattr(instance, attr, value)
#             instance.save()
#             return instance

#         # BEGIN atomic replace: restore old stock, then apply new
#         with transaction.atomic():
#             # restore stock from existing items
#             for old in instance.items.select_related("sku").all():
#                 sku = old.sku
#                 sku.stock_qty = sku.stock_qty + old.quantity
#                 sku.save(update_fields=["stock_qty", "updated_at"])

#             # delete old items
#             instance.items.all().delete()

#             # re-create with same logic as create (but without creating new order)
#             total_amount = Decimal("0.00")
#             sku_ids = [
#                 i["sku"].id if isinstance(i["sku"], ProductSKU) else i["sku"].pk
#                 for i in items_data
#             ]

#             # FIXED: remove select_related() from lock query
#             skus_qs = (
#                 ProductSKU.objects
#                 .filter(pk__in=sku_ids)
#                 .select_for_update()
#             )

#             # optional: load related objects AFTER locking
#             skus_qs = skus_qs.select_related("commodity_variant", "product")

#             skus_map = {str(s.id): s for s in skus_qs}


#             for item in items_data:
#                 sku_obj = item["sku"] if isinstance(item["sku"], ProductSKU) else skus_map.get(str(item["sku"].pk))
#                 qty = int(item["quantity"])

#                 if sku_obj is None:
#                     raise serializers.ValidationError("Invalid SKU provided.")

#                 if sku_obj.stock_qty < qty:
#                     raise serializers.ValidationError(f"Only {sku_obj.stock_qty} items available for SKU {sku_obj.sku_code}.")

#                 unit_price, tax_details = calculate_sku_price(sku_obj)
#                 discount = getattr(sku_obj, "discount_price", None) or Decimal("0.00")
#                 if discount > unit_price:
#                     discount = Decimal("0.00")

#                 item_subtotal = quantize_money((Decimal(unit_price) - Decimal(discount)) * qty)

#                 # decrement stock
#                 sku_obj.stock_qty = sku_obj.stock_qty - qty
#                 sku_obj.save(update_fields=["stock_qty", "updated_at"])

#                 # create OrderItem
#                 product_name = item.get("product_name") or sku_obj.product.name
#                 OrderItem.objects.create(
#                     order=instance,
#                     sku=sku_obj,
#                     product_name=product_name,
#                     quantity=qty,
#                     unit_price=quantize_money(unit_price),
#                     discount=quantize_money(discount),
#                     subtotal=item_subtotal,
#                     tax_details=tax_details,
#                 )

#                 total_amount += item_subtotal

#             instance.total_amount = quantize_money(total_amount)
#             instance.save(update_fields=["total_amount", "updated_at"])

#         return instance

class OrderSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    items = OrderItemSerializer(many=True)
    shipping_address = ShippingAddressSerializer(read_only=True)
    shipping_address_id = serializers.PrimaryKeyRelatedField(
        queryset=ShippingAddress.objects.all(),
        write_only=True,
        source="shipping_address"
    )

    class Meta:
        model = Order
        fields = [
            "id",
            "order_number",
            "user",
            "shipping_address",
            "shipping_address_id",
            "status",
            "payment_status",
            "total_amount",
            "is_active",
            "items",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id", "created_at", "updated_at", "order_number",
            "status", "payment_status", "total_amount"
        ]

    def validate(self, attrs):
        items = attrs.get("items", [])
        if not items:
            raise serializers.ValidationError("Order must contain at least one item.")
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        """
        Create Order:
         - Validate stock (with SELECT FOR UPDATE)
         - Compute backend unit_price, tax_details, subtotal per item
         - Decrement stock atomically
         - Save order and order items
        """
        request = self.context.get("request")
        user = request.user

        items_data = validated_data.pop("items")
        validated_data["user"] = user
        validated_data["order_number"] = f"ORD-{uuid.uuid4().hex[:10].upper()}"

        # create order placeholder with zero amount
        order = Order.objects.create(**validated_data, total_amount=Decimal("0.00"))
        # print(order)
        total_amount = Decimal("0.00")

        # Lock all SKUs involved to avoid race conditions.
        sku_ids = [
            i["sku"].id if isinstance(i["sku"], ProductSKU) else i["sku"].pk
            for i in items_data
        ]
        # print(sku_ids)
        # FIX: select_related() BEFORE select_for_update()
        # Only include non-nullable relations before lock
        skus_qs = (
            ProductSKU.objects
            .filter(pk__in=sku_ids)
            .select_related("product")  # Non-nullable, safe to include
            .select_for_update()
        )

        # Load nullable relations AFTER locking using prefetch_related
        skus_qs = skus_qs.prefetch_related("commodity_variant__commodity")

        skus_map = {str(s.id): s for s in skus_qs}

        # Process each item
        for item in items_data:
            sku_obj = item["sku"] if isinstance(item["sku"], ProductSKU) else skus_map.get(str(item["sku"].pk))
            qty = int(item["quantity"])

            if sku_obj is None:
                raise serializers.ValidationError("Invalid SKU provided.")

            # STOCK validation
            if sku_obj.stock_qty < qty:
                raise serializers.ValidationError(f"Only {sku_obj.stock_qty} items available for SKU {sku_obj.sku_code}.")

            # compute price and tax via helper (ensures consistent logic)
            try:
                final_price, tax_details = calculate_sku_price(sku_obj)
            except Exception as e:
                raise serializers.ValidationError(f"Price calculation failed for SKU {sku_obj.sku_code}: {str(e)}")

            # get values from breakdown
            pb = tax_details.get("price_breakdown", {})
            unit_price = Decimal(str(pb.get("base_price", final_price)))
            discount = Decimal(str(pb.get("discount_amount", "0.00")))

            item_subtotal = final_price * qty
            print(item_subtotal)
            # Decrement stock
            sku_obj.stock_qty = sku_obj.stock_qty - qty
            sku_obj.save(update_fields=["stock_qty", "updated_at"])

            # Create order item (snapshot)
            product_name = item.get("product_name") or sku_obj.product.name
            OrderItem.objects.create(
                order=order,
                sku=sku_obj,
                product_name=product_name,
                quantity=qty,
                unit_price=quantize_money(unit_price),
                discount=quantize_money(discount),
                subtotal=item_subtotal,
                tax_details=tax_details,
            )

            total_amount += item_subtotal

        order.total_amount = quantize_money(total_amount)
        order.save(update_fields=["total_amount", "updated_at"])
        # print("Order: ", order)
        return order

    def update(self, instance, validated_data):
        """
        Allow update only in PENDING status (owner).
        Replace items safely: restore stock of old items, then re-validate and apply new items.
        """
        request = self.context.get("request")
        user = request.user

        if instance.user_id != user.id:
            raise serializers.ValidationError("You cannot modify this order.")

        if instance.status != OrderStatus.PENDING:
            raise serializers.ValidationError("Only pending orders can be modified.")

        items_data = validated_data.pop("items", None)
        if items_data is None:
            # only update non-item fields
            for attr, value in validated_data.items():
                setattr(instance, attr, value)
            instance.save()
            return instance

        # BEGIN atomic replace: restore old stock, then apply new
        with transaction.atomic():
            # restore stock from existing items
            for old in instance.items.select_related("sku").all():
                sku = old.sku
                sku.stock_qty = sku.stock_qty + old.quantity
                sku.save(update_fields=["stock_qty", "updated_at"])

            # delete old items
            instance.items.all().delete()

            # re-create with same logic as create (but without creating new order)
            total_amount = Decimal("0.00")
            sku_ids = [
                i["sku"].id if isinstance(i["sku"], ProductSKU) else i["sku"].pk
                for i in items_data
            ]

            # FIX: select_related() BEFORE select_for_update()
            skus_qs = (
                ProductSKU.objects
                .filter(pk__in=sku_ids)
                .select_related("product")  # Non-nullable, safe to include
                .select_for_update()
            )

            # Load nullable relations AFTER locking
            skus_qs = skus_qs.prefetch_related("commodity_variant__commodity")

            skus_map = {str(s.id): s for s in skus_qs}

            for item in items_data:
                sku_obj = item["sku"] if isinstance(item["sku"], ProductSKU) else skus_map.get(str(item["sku"].pk))
                qty = int(item["quantity"])

                if sku_obj is None:
                    raise serializers.ValidationError("Invalid SKU provided.")

                if sku_obj.stock_qty < qty:
                    raise serializers.ValidationError(f"Only {sku_obj.stock_qty} items available for SKU {sku_obj.sku_code}.")

                final_price, tax_details = calculate_sku_price(sku_obj)
                pb = tax_details.get("price_breakdown", {})
                unit_price = Decimal(str(pb.get("base_price", final_price)))
                discount = Decimal(str(pb.get("discount_amount", "0.00")))

                item_subtotal = final_price * qty

                # decrement stock
                sku_obj.stock_qty = sku_obj.stock_qty - qty
                sku_obj.save(update_fields=["stock_qty", "updated_at"])

                # create OrderItem
                product_name = item.get("product_name") or sku_obj.product.name
                OrderItem.objects.create(
                    order=instance,
                    sku=sku_obj,
                    product_name=product_name,
                    quantity=qty,
                    unit_price=quantize_money(unit_price),
                    discount=quantize_money(discount),
                    subtotal=item_subtotal,
                    tax_details=tax_details,
                )

                total_amount += item_subtotal

            instance.total_amount = quantize_money(total_amount)
            instance.save(update_fields=["total_amount", "updated_at"])

        return instance
    

class CreatePaymentOrderSerializer(serializers.Serializer):
    order_id = serializers.UUIDField()


class VerifyPaymentSerializer(serializers.Serializer):
    razorpay_order_id = serializers.CharField()
    razorpay_payment_id = serializers.CharField()
    razorpay_signature = serializers.CharField()


class RazorpayWebhookSerializer(serializers.Serializer):
    payload = serializers.JSONField()
    signature = serializers.CharField()


class InvoiceDownloadSerializer(serializers.ModelSerializer):
    order_id = serializers.UUIDField(source="order.id", read_only=True)
    payment_id = serializers.UUIDField(source="payment.id", read_only=True)

    class Meta:
        model = Invoice
        fields = [
            "id",
            "invoice_number",
            "order_id",
            "payment_id",
            "currency",
            "invoice_data",
            "created_at",
        ]
        read_only_fields = fields
