import hashlib
import hmac
import json
import logging
import time
import uuid
from decimal import Decimal

import razorpay
from razorpay.errors import SignatureVerificationError

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction

from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from orders.models import Order, OrderItem
from store.models import Product, ProductVariant

from .models import Payment
from .services import (
    PaymentRejected,
    calculate_shipping,
    process_captured_payment,
    to_paise,
)

logger = logging.getLogger(__name__)

MAX_LINES = 50
FIELD_LIMITS = {
    "full_name": 200,
    "email": 254,
    "phone": 15,
    "address_line1": 255,
    "address_line2": 255,
    "city": 100,
    "state": 100,
    "pincode": 10,
}
REQUIRED_FIELDS = [
    "full_name", "email", "phone", "address_line1", "city", "state", "pincode",
]


def get_razorpay_client():
    return razorpay.Client(
        auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
    )


def _text(data, key):
    value = data.get(key)
    return "" if value is None else str(value).strip()


class CheckoutError(Exception):
    pass


def _validate_items(items):
    """Price everything from the database. Returns (lines, subtotal)."""
    if not isinstance(items, list) or not items:
        raise CheckoutError("Your cart is empty.")
    if len(items) > MAX_LINES:
        raise CheckoutError("Too many items in one order.")

    lines = []
    subtotal = Decimal("0.00")

    for item in items:
        if not isinstance(item, dict):
            raise CheckoutError("Invalid cart item.")

        size = _text(item, "size")
        color = _text(item, "color")
        variant_id = item.get("variant_id")

        try:
            quantity = int(item.get("quantity", 1))
            if quantity < 1:
                raise ValueError
        except (TypeError, ValueError):
            raise CheckoutError("Invalid item quantity.")

        product = Product.objects.filter(
            id=item.get("product_id"), is_active=True
        ).select_related("category").first()
        if not product:
            raise CheckoutError("A product is unavailable.")

        variant = None
        if variant_id:
            variant = ProductVariant.objects.filter(
                id=variant_id, product=product
            ).first()
        elif size:
            variant = ProductVariant.objects.filter(
                product=product, size=size, color=color
            ).first()

        if product.variants.exists():
            if not variant:
                raise CheckoutError(
                    f"Please select a valid size for {product.name}."
                )
            if variant.stock < quantity:
                raise CheckoutError(
                    f"Only {variant.stock} item(s) remain for "
                    f"{product.name}, size {variant.size}."
                )
            # The variant row is the source of truth for size and color.
            size = variant.size
            color = variant.color
        elif product.stock < quantity:
            raise CheckoutError(f"Insufficient stock for {product.name}.")

        price = Decimal(str(product.price))
        subtotal += price * quantity
        lines.append({
            "product": product,
            "quantity": quantity,
            "price": price,
            "size": size,
            "color": color,
        })

    return lines, subtotal


class CreatePaymentView(APIView):
    """
    Creates a PENDING order + Payment(status=created) and a Razorpay order.
    These rows are internal records. They only become customer-visible once
    the payment is verified (see orders.views.OrderListCreateView).
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        data = request.data

        cleaned = {}
        for field in REQUIRED_FIELDS + ["address_line2"]:
            cleaned[field] = _text(data, field)

        for field in REQUIRED_FIELDS:
            if not cleaned[field]:
                return Response(
                    {"error": f"{field.replace('_', ' ').title()} is required."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        for field, limit in FIELD_LIMITS.items():
            if len(cleaned[field]) > limit:
                return Response(
                    {"error": f"{field.replace('_', ' ').title()} is too long."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        try:
            validate_email(cleaned["email"])
        except ValidationError:
            return Response(
                {"error": "Please enter a valid email address."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            lines, subtotal = _validate_items(data.get("items"))
        except CheckoutError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        shipping = calculate_shipping(subtotal)
        total = subtotal + shipping
        amount_paise = to_paise(total)

        # Network call kept OUTSIDE any DB transaction.
        try:
            rz_order = get_razorpay_client().order.create({
                "amount": amount_paise,
                "currency": "INR",
                "receipt": f"nf-{uuid.uuid4().hex[:24]}",
            })
        except Exception:
            logger.exception("Razorpay order creation failed")
            return Response(
                {"error": "Payment gateway is unavailable. Please try again."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        try:
            with transaction.atomic():
                order = Order.objects.create(
                    user=request.user,
                    status="pending",
                    full_name=cleaned["full_name"],
                    email=cleaned["email"],
                    phone=cleaned["phone"],
                    address_line1=cleaned["address_line1"],
                    address_line2=cleaned["address_line2"],
                    city=cleaned["city"],
                    state=cleaned["state"],
                    pincode=cleaned["pincode"],
                    notes=_text(data, "notes"),
                    subtotal=subtotal,
                    shipping_charge=shipping,
                    total=total,
                    razorpay_order_id=rz_order["id"],
                )

                for line in lines:
                    product = line["product"]
                    OrderItem.objects.create(
                        order=order,
                        product=product,
                        product_name=product.name,
                        product_price=line["price"],
                        quantity=line["quantity"],
                        size=line["size"],
                        color=line["color"],
                        product_type=(
                            product.category.product_type
                            if product.category_id else ""
                        ),
                    )

                Payment.objects.create(
                    order=order,
                    razorpay_order_id=rz_order["id"],
                    amount=total,
                    status="created",
                )
        except Exception:
            logger.exception("Failed to save checkout order")
            return Response(
                {"error": "Unable to create your order. Please try again."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {
                "order_id": order.id,
                "order_number": order.order_number,
                "razorpay_order_id": rz_order["id"],
                "amount": amount_paise,
                "currency": "INR",
                "key": settings.RAZORPAY_KEY_ID,
                "subtotal": str(subtotal),
                "shipping_charge": str(shipping),
                "total": str(total),
            },
            status=status.HTTP_201_CREATED,
        )


class VerifyPaymentView(APIView):
    """
    Response contract for the frontend:
      200 -> confirmed (or already confirmed). Clear cart, go to My Orders.
      202 -> payment authorized but not captured yet. Do NOT clear cart; tell
             the user it is being confirmed (webhook will finish it).
      4xx/5xx -> not confirmed. Do NOT clear cart or redirect.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        payment_id = request.data.get("razorpay_payment_id")
        razorpay_order_id = request.data.get("razorpay_order_id")
        signature = request.data.get("razorpay_signature")

        if not all([payment_id, razorpay_order_id, signature]):
            return Response(
                {"error": "Missing Razorpay payment details."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        client = get_razorpay_client()

        # 1) Cryptographic signature check (needs the key secret).
        try:
            client.utility.verify_payment_signature({
                "razorpay_order_id": razorpay_order_id,
                "razorpay_payment_id": payment_id,
                "razorpay_signature": signature,
            })
        except SignatureVerificationError:
            logger.warning("Bad Razorpay signature for order %s", razorpay_order_id)
            return Response(
                {"error": "Payment signature verification failed."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception:
            logger.exception("Signature check error")
            return Response(
                {"error": "Payment verification failed."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 2) Ask Razorpay for the real payment state. A fresh payment can be
        #    'authorized' for a moment before auto-capture, so retry briefly.
        try:
            rz_payment = None
            for attempt in range(3):
                rz_payment = client.payment.fetch(payment_id)
                if rz_payment.get("status") != "authorized":
                    break
                if attempt < 2:
                    time.sleep(1)
        except Exception:
            logger.exception("Could not fetch payment %s", payment_id)
            return Response(
                {"error": "Could not reach the payment gateway. Please retry."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if rz_payment.get("order_id") != razorpay_order_id:
            return Response(
                {"error": "Payment does not match this order."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        pay_status = rz_payment.get("status")
        if pay_status == "authorized":
            return Response(
                {
                    "status": "authorized",
                    "detail": (
                        "Your payment is being confirmed. Your order will "
                        "appear in My Orders shortly."
                    ),
                },
                status=status.HTTP_202_ACCEPTED,
            )
        if pay_status != "captured":
            return Response(
                {"error": f"Payment was not successful ({pay_status})."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 3) Apply it (shared, idempotent, locked).
        try:
            order, newly_confirmed = process_captured_payment(
                rz_payment, user=request.user, signature=signature
            )
        except PaymentRejected as exc:
            return Response({"error": exc.message}, status=exc.http_status)
        except Exception:
            logger.exception("Error processing captured payment %s", payment_id)
            return Response(
                {
                    "error": (
                        "Payment was received, but order processing needs "
                        "attention. Contact support with your payment ID."
                    ),
                    "payment_id": payment_id,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response({
            "status": (
                "Payment verified successfully."
                if newly_confirmed else "Payment already verified."
            ),
            "order_id": order.id,
            "order_number": order.order_number,
        })


class RazorpayWebhookView(APIView):
    """
    Server-to-server confirmation. Covers the case where the customer pays
    but closes the tab / loses network before the browser callback runs.
    URL: POST /api/payments/webhook/
    """
    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    throttle_classes = []

    def post(self, request):
        secret = getattr(settings, "RAZORPAY_WEBHOOK_SECRET", "")
        if not secret:
            logger.error("RAZORPAY_WEBHOOK_SECRET is not configured")
            return Response(status=status.HTTP_503_SERVICE_UNAVAILABLE)

        body = request.body
        received = request.headers.get("X-Razorpay-Signature", "")
        expected = hmac.new(
            secret.encode("utf-8"), body, hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(expected, received):
            logger.warning("Webhook with invalid signature rejected")
            return Response(status=status.HTTP_400_BAD_REQUEST)

        try:
            payload = json.loads(body)
        except ValueError:
            return Response(status=status.HTTP_400_BAD_REQUEST)

        event = payload.get("event", "")
        entity = (
            payload.get("payload", {}).get("payment", {}).get("entity", {})
        )

        if event == "payment.captured":
            try:
                process_captured_payment(entity)
            except PaymentRejected as exc:
                # Acknowledge so Razorpay stops retrying; it is logged.
                logger.warning(
                    "Webhook payment %s not applied: %s",
                    entity.get("id"), exc.message,
                )
            except Exception:
                logger.exception("Webhook processing failed")
                # 500 makes Razorpay retry later.
                return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        elif event == "payment.failed":
            # The customer may retry on the same Razorpay order, so only
            # note the failure. A later success still confirms the order.
            Payment.objects.filter(
                razorpay_order_id=entity.get("order_id") or "",
                status="created",
            ).update(status="failed")

        return Response({"status": "ok"})
