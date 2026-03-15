from datetime import datetime
import uuid
from django.db import transaction
from orders.models import Invoice
import logging
from django.db import transaction
from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)

COMPANY_NAME    = "The Cultural Feed"
COMPANY_ADDRESS = "West Bengal, India"
GSTIN           = "19ABCDE1234F1Z5"
WEBSITE         = "www.theculturalfeed.com"
PHONE           = "+91-XXXXXXXXXX"
EMAIL           = "support@theculturalfeed.com"


def generate_invoice_number():
    return f"INV-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"


def _build_item_row(item):
    """
    Build a rich item row from the OrderItem record.
    Falls back gracefully if tax_details is missing or partial.
    """
    tax_details = item.tax_details or {}
    pb = tax_details.get("price_breakdown", {})

    # Pull jewellery-specific fields from stored price breakdown
    purity        = tax_details.get("purity", "")      # e.g. "22K"
    gold_rate     = pb.get("gold_rate", 0)             # rate per gram
    net_weight    = pb.get("weight", 0)                # net weight in grams
    gross_weight  = net_weight                         # same as net unless wastage tracked separately
    making_charge = pb.get("making_charge", 0)         # labour/making charges
    wastage       = pb.get("wastage", 0)
    stone_value   = pb.get("stone_value", 0)
    hallmark      = pb.get("hallmark", 0)
    packaging     = pb.get("packaging", 0)
    cgst          = pb.get("cgst", 0)
    sgst          = pb.get("sgst", 0)
    gst_total     = round(float(cgst) + float(sgst), 2)

    # Additional Cost = stone_value + hallmark + packaging + wastage
    additional    = round(float(stone_value) + float(hallmark) + float(packaging) + float(wastage), 2)

    # GST percent string (e.g. "3%")
    method = pb.get("method", "commodity")
    gst_percent_str = "3%" if method != "fixed_price" else "—"

    return {
        "product":        item.product_name,
        "sku_code":       getattr(item.sku, "sku_code", "") if item.sku else "",
        "quantity":       item.quantity,
        "purity":         purity,
        "gold_rate":      float(gold_rate),
        "net_weight":     float(net_weight),
        "gross_weight":   float(gross_weight),
        "making_charge":  float(making_charge),
        "additional":     additional,
        "gst_percent":    gst_percent_str,
        "gst_amount":     gst_total,
        "unit_price":     str(item.unit_price),
        "subtotal":       str(item.subtotal),
        "discount":       str(item.discount or "0.00"),
        # Raw breakdown for summary aggregation
        "_cgst":          float(cgst),
        "_sgst":          float(sgst),
        "_making_charge": float(making_charge),
        "_metal_value":   float(pb.get("metal_value", 0)),
        "_discount_amount": float(pb.get("discount_amount", 0)),
        "_gross_weight":  float(gross_weight),
    }


def build_invoice_data(order, payment, invoice_number):
    """
    Builds enriched invoice_data dict that includes all jewellery fields
    required for the Vyapar-style PDF template.
    """
    user    = order.user
    address = order.shipping_address

    items = []
    for item in order.items.select_related("sku__commodity_variant__commodity").all():
        try:
            row = _build_item_row(item)
            items.append(row)
        except Exception as e:
            logger.warning(f"Failed to build item row for {item.product_name}: {e}")
            # Fallback minimal row
            items.append({
                "product":       item.product_name,
                "sku_code":      "",
                "quantity":      item.quantity,
                "purity":        "",
                "gold_rate":     0,
                "net_weight":    0,
                "gross_weight":  0,
                "making_charge": 0,
                "additional":    0,
                "gst_percent":   "—",
                "gst_amount":    0,
                "unit_price":    str(item.unit_price),
                "subtotal":      str(item.subtotal),
                "discount":      str(item.discount or "0.00"),
                "_cgst":          0,
                "_sgst":          0,
                "_making_charge": 0,
                "_metal_value":   0,
                "_discount_amount": 0,
                "_gross_weight":  0,
            })

    # Build aggregate summary
    total_making_charges = round(sum(i["_making_charge"] for i in items), 2)
    total_gross_weight   = round(sum(i["_gross_weight"] for i in items), 2)
    total_discount       = round(sum(i["_discount_amount"] for i in items), 2)
    subtotal_with_gst    = float(order.total_amount) + total_discount  # before discount

    return {
        # ── Company ──────────────────────────────────
        "company_name":    COMPANY_NAME,
        "company_address": COMPANY_ADDRESS,
        "gstin":           GSTIN,
        "website":         WEBSITE,
        "phone":           PHONE,
        "email":           EMAIL,

        # ── Invoice Meta ─────────────────────────────
        "invoice_number":  invoice_number,
        "order_id":        str(order.id),
        "order_number":    order.order_number,
        "payment_id":      str(payment.id),
        "razorpay_payment_id": payment.razorpay_payment_id or "",
        "currency":        payment.currency or "INR",
        "paid_at":         payment.paid_at.isoformat() if payment.paid_at else None,

        # ── Customer ─────────────────────────────────
        "user": {
            "id":    str(user.id),
            "name":  user.full_name,
            "email": user.email,
            "phone": user.phone or "",
        },

        # ── Shipping Address ─────────────────────────
        "shipping_address": None if not address else {
            "label":         address.label or "",
            "full_name":     address.full_name,
            "phone":         address.phone or "",
            "address_line1": address.address_line1,
            "address_line2": address.address_line2 or "",
            "city":          address.city,
            "pincode":       address.pincode,
            "state":         address.state,
            "country":       address.country,
        },

        # ── Items (enriched jewellery data) ──────────
        "items": items,

        # ── Aggregated Summary ───────────────────────
        "summary": {
            "subtotal_with_gst":   round(subtotal_with_gst, 2),
            "total_making_charges": total_making_charges,
            "total_gross_weight":  total_gross_weight,
            "total_discount":       total_discount,
            "total_amount":         float(order.total_amount),
        },

        # ── Payment ──────────────────────────────────
        "total_amount": str(order.total_amount),
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
        logger.error("Invoice JSON serialization failed", exc_info=True)
        raise ValidationError("Invoice data contains non-serializable values")

    except Exception as e:
        logger.error("Invoice creation failed", exc_info=True)
        raise
