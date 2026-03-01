from django.urls import path
from .views import (
    CreateRazorpayOrderAPIView,
    DownloadInvoiceAPIView,
    OrderListCreateAPIView,
    OrderAdminUpdateStatusAPIView,
    OrderDetailAPIView,
    VerifyRazorpayPaymentAPIView,
    razorpay_webhook, shipping_estimate_view
)

urlpatterns = [
    # Shipment Check
    path("shipping/estimate/", shipping_estimate_view, name="shipment-estimate-date-rate"),

    # Orders
    path("", OrderListCreateAPIView.as_view(), name="order-list-create"),
    path("<uuid:pk>/", OrderDetailAPIView.as_view(), name="order-detail"),
    path("<uuid:pk>/status/", OrderAdminUpdateStatusAPIView.as_view(), name="order-status-update"),

    # Payment
    path("create/payment/", CreateRazorpayOrderAPIView.as_view(), name="create-razorpay-order"),
    path("verify/payment/", VerifyRazorpayPaymentAPIView.as_view(), name="verify-razorpay-payment"),
    path("webhook/", razorpay_webhook, name="razorpay-webhook"),

    # Invoice Download
    path("invoice/download/", DownloadInvoiceAPIView.as_view(), name="download-invoice"),
]
