from datetime import datetime
import uuid
from django.db import transaction
from orders.models import Invoice
import logging
from django.db import transaction
from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)

def generate_invoice_number():
    return f"INV-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"


def build_invoice_data(order, payment, invoice_number):
    user = order.user
    address = order.shipping_address

    return {
        "invoice_number": invoice_number,

        # IDs MUST be strings in JSON
        "order_id": str(order.id),
        "payment_id": str(payment.id),

        "razorpay_payment_id": payment.razorpay_payment_id,

        "user": {
            "id": str(user.id),
            "name": user.full_name,
            "email": user.email,
            "phone": user.phone,
        },

        "shipping_address": None if not address else {
            "label": address.label,
            "full_name": address.full_name,
            "phone": address.phone,
            "address_line1": address.address_line1,
            "address_line2": address.address_line2,
            "city": address.city,
            "pincode": address.pincode,
            "state": address.state,
            "country": address.country,
        },

        "items": [
            {
                "product": item.product_name,
                "quantity": item.quantity,
                "unit_price": str(item.unit_price),
                "subtotal": str(item.subtotal),
            }
            for item in order.items.all()
        ],

        "total_amount": str(order.total_amount),

        "paid_at": payment.paid_at.isoformat() if payment.paid_at else None,
    }



def create_invoice_for_payment(payment, order, user):
    """
    Create invoice only once for a successful payment.
    Safe against duplicates & JSON serialization issues.
    """

    existing_invoice = Invoice.objects.filter(order=order).first()
    if existing_invoice:
        return existing_invoice

    invoice_number = generate_invoice_number()

    try:
        with transaction.atomic():
            invoice_data = build_invoice_data(
                order=order,
                payment=payment,
                invoice_number=invoice_number
            )

            invoice = Invoice.objects.create(
                invoice_number=invoice_number,
                order=order,
                payment=payment,
                user_id=user.id,
                invoice_data=invoice_data,
                currency=payment.currency or "INR",
            )

            return invoice

    except TypeError as e:
        logger.error(
            "Invoice JSON serialization failed",
            exc_info=True
        )
        raise ValidationError(
            "Invoice data contains non-serializable values"
        )

    except Exception as e:
        logger.error(
            "Invoice creation failed",
            exc_info=True
        )
        raise
