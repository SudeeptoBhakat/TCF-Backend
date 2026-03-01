from venv import logger
import requests
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from rest_framework.response import Response
from rest_framework import status, serializers
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.core.cache import cache
from rest_framework.decorators import api_view, permission_classes

from orders.invoice_builder import build_invoice_data, create_invoice_for_payment
from .models import Invoice, Order
from .serializers import InvoiceDownloadSerializer, OrderSerializer
import razorpay
import hmac
import hashlib
import json
from django.conf import settings
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions

from .models import Payment, PaymentMethod, PaymentStatus
from .serializers import (
    CreatePaymentOrderSerializer,
    VerifyPaymentSerializer,
    RazorpayWebhookSerializer
)
from orders.models import Order

SHIPROCKET_AUTH_URL = "https://apiv2.shiprocket.in/v1/external/auth/login"
SHIPROCKET_RATE_URL = "https://apiv2.shiprocket.in/v1/external/courier/serviceability"

TOKEN_CACHE_KEY = "shiprocket_token"
TOKEN_EXPIRY_SECONDS = 60 * 60 * 8  # 8 hours

# Razorpay Client
razorpay_client = razorpay.Client(
    auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
)

def get_shiprocket_token():
    token = cache.get(TOKEN_CACHE_KEY)
    if token:
        print("Using cached token")
        return token

    payload = {
        "email": settings.SHIPROCKET_EMAIL.strip(),
        "password": settings.SHIPROCKET_PASSWORD.strip()
    }

    try:
        response = requests.post(
            SHIPROCKET_AUTH_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=15
        )

        # print("Status Code:", response.status_code)
        # print("Response:", response.text)

        response.raise_for_status()

        token = response.json().get("token")

        if not token:
            raise Exception("Token not found in Shiprocket response")

        cache.set(TOKEN_CACHE_KEY, token, TOKEN_EXPIRY_SECONDS)

        return token

    except requests.exceptions.RequestException as e:
        raise Exception(f"Shiprocket API error: {str(e)}")


def fetch_shipping_rate(pincode, weight, cod=False):
    """
    Calls Shiprocket rate API and returns cheapest courier
    """
    token = get_shiprocket_token()
    # print(token)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    weight_kg = round(weight / 1000, 2)

    if weight_kg < 0.5:
        weight_kg = 0.5

    payload = {
        "pickup_postcode": str(settings.SHIPROCKET_PICKUP_PINCODE),
        "delivery_postcode": str(pincode),
        "weight": float(weight_kg),
        "cod": int(cod)
    }

    response = requests.get(
        SHIPROCKET_RATE_URL,
        headers=headers,
        json=payload
    )
    # print("Status:", response.status_code)
    # print("Response:", response.text)
    # print(response.json())
    if response.status_code != 200:
        raise Exception("Shiprocket rate API failed")

    data = response.json()
    couriers = data.get("data", {}).get("available_courier_companies", [])

    if not couriers:
        return None

    cheapest = min(couriers, key=lambda x: x["rate"])

    return {
        "courier": cheapest["courier_name"],
        "charge": cheapest["rate"],
        "etd": cheapest["estimated_delivery_days"],
        "cod_available": cheapest["cod"]
    }

@api_view(["GET"])
@permission_classes([AllowAny])
def shipping_estimate_view(request):
    pincode = request.query_params.get("pincode")
    weight = float(request.query_params.get("weight", 0.5))
    cod = request.query_params.get("cod", "false") == "true"
    # print(weight)
    if not pincode or len(pincode) != 6:
        return Response(
            {"success": False, "message": "Invalid pincode"},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        result = fetch_shipping_rate(pincode, weight, cod)

        if not result:
            return Response(
                {"success": False, "message": "Delivery not available"},
                status=status.HTTP_200_OK
            )

        return Response({
            "success": True,
            "data": result
        })

    except Exception as e:
        return Response(
            {"success": False, "message": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


class OrderListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        orders = Order.objects.filter(user=request.user).order_by("-created_at")
        serializer = OrderSerializer(orders, many=True)
        return Response(serializer.data)

    def post(self, request):
        print(request.data)
        serializer = OrderSerializer(data=request.data, context={"request": request})
        if serializer.is_valid():
            try:
                order = serializer.save()
            except serializers.ValidationError as e:
                return Response({"error": e.detail}, status=status.HTTP_400_BAD_REQUEST)
            return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class OrderDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        order = get_object_or_404(Order, pk=pk, user=request.user)
        serializer = OrderSerializer(order)
        return Response(serializer.data)

    def put(self, request, pk):
        order = get_object_or_404(Order, pk=pk, user=request.user)
        serializer = OrderSerializer(order, data=request.data, context={"request": request})
        if serializer.is_valid():
            try:
                order = serializer.save()
            except serializers.ValidationError as e:
                return Response({"error": e.detail}, status=status.HTTP_400_BAD_REQUEST)
            return Response(OrderSerializer(order).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        """
        Soft delete: mark inactive and restore stock if order is cancellable.
        """
        order = get_object_or_404(Order, pk=pk, user=request.user)
        # allow deletion only in pending/processing depending on your policy
        if order.status not in [OrderStatus.PENDING, OrderStatus.PROCESSING]:
            return Response({"error": "Cannot delete order in current status"}, status=status.HTTP_400_BAD_REQUEST)

        # restore stock & mark inactive
        from .models import OrderItem, OrderStatus
        with transaction.atomic():
            for item in order.items.select_related("sku").all():
                sku = item.sku
                sku.stock_qty = sku.stock_qty + item.quantity
                sku.save(update_fields=["stock_qty", "updated_at"])
            order.is_active = False
            order.status = OrderStatus.CANCELLED
            order.save(update_fields=["is_active", "status", "updated_at"])

        return Response({"message": "Order cancelled and stock restored."}, status=status.HTTP_200_OK)


class OrderAdminUpdateStatusAPIView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        """
        Admin endpoint to change order status (e.g. mark as PAID, SHIPPED).
        Body: {"status": "paid"}
        """
        order = get_object_or_404(Order, pk=pk)
        new_status = request.data.get("status")
        if new_status not in [c[0] for c in Order.Status.field.choices] if hasattr(Order, "Status") else None:
            # fallback - accept known constants
            # You can validate more strictly here
            pass

        # You can add additional business rules here
        order.status = new_status
        order.save(update_fields=["status", "updated_at"])
        return Response({"message": "Status updated", "status": order.status})


# Create Razorpay Order
class CreateRazorpayOrderAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = CreatePaymentOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        order_id = serializer.validated_data["order_id"]

        # fetch actual order from DB
        try:
            order = Order.objects.get(id=order_id, user=request.user)
        except Order.DoesNotExist:
            return Response(
                {"error": "Order not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        # Get amount from the order's total_amount
        amount = order.total_amount
        amount_in_paisa = int(amount * 100)

        # Create Razorpay Order
        razorpay_order = razorpay_client.order.create({
            "amount": amount_in_paisa,
            "currency": "INR",
            "payment_capture": 1
        })

        # Create Payment record locally
        payment = Payment.objects.create(
            order=order,
            amount=amount,
            razorpay_order_id=razorpay_order["id"],
            currency="INR",
            status=PaymentStatus.INITIATED,
            provider_payload=razorpay_order,
            payment_method=PaymentMethod.objects.filter(code="razorpay").first()
        )

        return Response({
            "success": True,
            "razorpay_order_id": razorpay_order["id"],
            "razorpay_key": settings.RAZORPAY_KEY_ID,
            "amount": amount_in_paisa,
            "currency": "INR",
            "payment_uuid": str(payment.id)
        })
        

# Verify Razorpay Payment
class VerifyRazorpayPaymentAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = VerifyPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        r_order_id = serializer.validated_data["razorpay_order_id"]
        r_payment_id = serializer.validated_data["razorpay_payment_id"]
        r_signature = serializer.validated_data["razorpay_signature"]
        # print("Hello this is Verify Payment")
        try:
            payment = Payment.objects.get(razorpay_order_id=r_order_id)
        except Payment.DoesNotExist:
            return Response(
                {"error": "Payment record not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        # Signature Verification
        generated_signature = hmac.new(
            settings.RAZORPAY_KEY_SECRET.encode(),
            f"{r_order_id}|{r_payment_id}".encode(),
            hashlib.sha256
        ).hexdigest()

        if generated_signature != r_signature:
            payment.status = PaymentStatus.FAILED
            payment.error_description = "Signature mismatch"
            payment.save()

            return Response(
                {"success": False, "message": "Invalid signature"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Fetch payment details from Razorpay for verification
        razorpay_payment_data = razorpay_client.payment.fetch(r_payment_id)

        # Update Payment
        payment.razorpay_payment_id = r_payment_id
        payment.razorpay_signature = r_signature
        payment.provider_payload = razorpay_payment_data
        payment.status = PaymentStatus.SUCCESS
        payment.paid_at = timezone.now()
        payment.verified_at = timezone.now()
        payment.save()

        # Update Order status
        payment.order.status = "paid"
        payment.order.save()
        invoice = create_invoice_for_payment(payment, payment.order, payment.order.user)

        return Response({
            "success": True,
            "message": "Payment verified successfully",
            "order_id": payment.order.id
        })


# Razorpay Webhook Handler
@csrf_exempt
def razorpay_webhook(request):
    if request.method != "POST":
        return Response({"detail": "Method not allowed"}, status=405)

    payload = request.body.decode("utf-8")
    received_signature = request.headers.get("X-Razorpay-Signature")

    # Verify Webhook Signature
    expected_signature = hmac.new(
        settings.RAZORPAY_WEBHOOK_SECRET.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()

    if expected_signature != received_signature:
        return Response({"error": "Invalid webhook signature"}, status=400)

    event = json.loads(payload)
    event_type = event.get("event")

    # Handle Success/Failure/Refund Events
    if event_type in ["payment.captured", "order.paid", "payment.authorized"]:
        r_payment_id = event["payload"]["payment"]["entity"]["id"]

        try:
            payment = Payment.objects.get(razorpay_payment_id=r_payment_id)
        except Payment.DoesNotExist:
            return Response({"detail": "Payment not found"}, status=404)

        payment.status = PaymentStatus.SUCCESS
        payment.provider_payload = event
        payment.verified_at = timezone.now()
        payment.save()

        payment.order.status = "PAID"
        payment.order.save()

    elif event_type == "payment.failed":
        r_payment_id = event["payload"]["payment"]["entity"]["id"]

        try:
            payment = Payment.objects.get(razorpay_payment_id=r_payment_id)
        except Payment.DoesNotExist:
            return Response({"detail": "Payment not found"}, status=404)

        err = event["payload"]["payment"]["entity"]["error_code"]

        payment.status = PaymentStatus.FAILED
        payment.error_code = err
        payment.error_description = event
        payment.save()

    return Response({"status": "Webhook processed"}, status=200)



class DownloadInvoiceAPIView(APIView):
    """
    Download invoice using ORDER ID (not invoice ID)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        order_id = request.query_params.get("order_id")

        if not order_id:
            return Response(
                {"detail": "order_id is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Fetch order & ownership check
            order = get_object_or_404(
                Order,
                id=order_id,
                user=user,
                is_active=True
            )

            # Check payment status
            # if order.payment_status != PaymentStatus.Success:
            #     return Response(
            #         {"detail": "Order payment is not completed"},
            #         status=status.HTTP_403_FORBIDDEN
            #     )

            # Fetch invoice
            invoice = Invoice.objects.select_related(
                "order", "payment", "user"
            ).filter(order=order).first()

            if not invoice:
                return Response(
                    {"detail": "Invoice not generated for this order"},
                    status=status.HTTP_404_NOT_FOUND
                )

            # Validate payment integrity
            payment = invoice.payment
            if not payment:
                return Response(
                    {"detail": "Payment record missing for invoice"},
                    status=status.HTTP_409_CONFLICT
                )

            if payment.amount != order.total_amount:
                logger.error(
                    f"Payment mismatch | Order {order.id} | "
                    f"Order amount: {order.total_amount} | "
                    f"Paid amount: {payment.amount}"
                )
                return Response(
                    {"detail": "Payment amount mismatch"},
                    status=status.HTTP_409_CONFLICT
                )

            # Serialize & return invoice
            serializer = InvoiceDownloadSerializer(invoice)
            return Response(serializer.data, status=status.HTTP_200_OK)

        except Exception as e:
            logger.exception("Invoice download failed")
            return Response(
                {"detail": "Something went wrong while fetching invoice"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
