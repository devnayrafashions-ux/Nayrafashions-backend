"""
Single place where a *captured* Razorpay payment turns into a confirmed order.

Used by:
  - VerifyPaymentView   (browser callback, after signature check)
  - RazorpayWebhookView (server-to-server, after webhook signature check)
  - expire_abandoned_orders management command (reconciliation)

Because all three go through process_captured_payment(), stock is deducted
once, the email is sent once, and the order is confirmed once, no matter how
many times or in what order they run.
"""
import logging
from decimal import Decimal

from django.core.mail import mail_admins
from django.db import transaction
from django.db.models import Q, Sum

from orders.models import CartItem, Order
from orders.utils import send_order_confirmation_email
from store.models import Product, ProductVariant

from .models import Payment

logger = logging.getLogger(__name__)

FREE_SHIPPING_THRESHOLD = Decimal("2999.00")
SHIPPING_FEE = Decimal("99.00")
EXPECTED_CURRENCY = "INR"


class PaymentRejected(Exception):
    """A payment cannot be applied to an order. Carries an HTTP status."""

    def __init__(self, message, http_status=400):
        super().__init__(message)
        self.message = message
        self.http_status = http_status


def calculate_shipping(subtotal):
    return Decimal("0.00") if subtotal >= FREE_SHIPPING_THRESHOLD else SHIPPING_FEE


def to_paise(amount):
    return int((Decimal(amount) * 100).to_integral_value())


# --------------------------------------------------------------------------
# Inventory
# --------------------------------------------------------------------------
def _find_variant(product, size, color):
    """Exact size+color match, else a size-only match if it is unambiguous."""
    qs = ProductVariant.objects.select_for_update().filter(
        product=product, size=size
    )
    exact = qs.filter(color=color).first()
    if exact:
        return exact
    candidates = list(qs[:2])
    return candidates[0] if len(candidates) == 1 else None


def _deduct_stock(order):
    """
    Deduct stock for every line. Never lets stock go negative; any line that
    cannot be fully covered is returned as a shortfall message so staff can
    refund or restock. The customer HAS paid, so the order is still confirmed.
    """
    shortfalls = []

    for item in order.items.all():
        if not item.product_id:
            shortfalls.append(f"{item.product_name}: product no longer exists")
            continue

        # Re-read under lock for every line, so repeated products are safe.
        product = Product.objects.select_for_update().filter(
            pk=item.product_id
        ).first()
        if not product:
            shortfalls.append(f"{item.product_name}: product no longer exists")
            continue

        if product.variants.exists():
            variant = _find_variant(product, item.size, item.color)
            if not variant:
                shortfalls.append(
                    f"{item.product_name}: variant {item.size}/{item.color} not found"
                )
                continue

            take = min(variant.stock, item.quantity)
            if take < item.quantity:
                shortfalls.append(
                    f"{item.product_name} ({item.size}): wanted "
                    f"{item.quantity}, only {variant.stock} in stock"
                )
            if take:
                variant.stock -= take
                variant.save(update_fields=["stock"])

            product.stock = (
                ProductVariant.objects.filter(product=product)
                .aggregate(total=Sum("stock"))["total"]
                or 0
            )
            product.save(update_fields=["stock"])
        else:
            take = min(product.stock, item.quantity)
            if take < item.quantity:
                shortfalls.append(
                    f"{item.product_name}: wanted {item.quantity}, "
                    f"only {product.stock} in stock"
                )
            if take:
                product.stock -= take
                product.save(update_fields=["stock"])

    return shortfalls


# --------------------------------------------------------------------------
# After-commit side effects (never able to undo a successful payment)
# --------------------------------------------------------------------------
def _after_commit(order_id, shortfalls):
    try:
        order = Order.objects.get(id=order_id)
    except Exception:
        logger.exception("after-commit: cannot load order %s", order_id)
        return

    try:
        send_order_confirmation_email(order)
    except Exception:
        logger.exception("Confirmation email failed for order %s", order_id)

    # Remove just-purchased lines from the server-side cart (best effort).
    try:
        if order.user_id:
            for item in order.items.all():
                if not item.product_id:
                    continue
                qs = CartItem.objects.filter(
                    cart__user_id=order.user_id, product_id=item.product_id
                )
                if item.size:
                    qs = qs.filter(
                        Q(variant__size=item.size) | Q(variant__isnull=True)
                    )
                qs.delete()
    except Exception:
        logger.exception("Cart cleanup failed for order %s", order_id)

    if shortfalls:
        try:
            mail_admins(
                subject=f"[Nayra] STOCK SHORTFALL on paid order {order.order_number}",
                message=(
                    "Customer has paid but stock was insufficient. Restock "
                    "or refund in the Razorpay dashboard.\n\n"
                    + "\n".join(shortfalls)
                ),
                fail_silently=True,
            )
        except Exception:
            logger.exception("Could not notify admins about shortfall")


# --------------------------------------------------------------------------
# Main entry point
# --------------------------------------------------------------------------
def process_captured_payment(rz_payment, user=None, signature=""):
    """
    rz_payment: Razorpay payment entity (dict) fetched from Razorpay or taken
                from a signature-verified webhook.
    user:       when given, the order must belong to this user.

    Returns (order, newly_confirmed: bool). Raises PaymentRejected.
    """
    rz_order_id = rz_payment.get("order_id") or ""
    rz_payment_id = rz_payment.get("id") or ""

    if not rz_order_id or not rz_payment_id:
        raise PaymentRejected("Incomplete payment details.", 400)

    if rz_payment.get("status") != "captured":
        raise PaymentRejected("Payment has not been captured.", 400)

    with transaction.atomic():
        orders = Order.objects.select_for_update().filter(
            razorpay_order_id=rz_order_id
        )
        if user is not None:
            orders = orders.filter(user=user)
        order = orders.first()

        if not order:
            raise PaymentRejected("Order not found.", 404)

        payment = Payment.objects.select_for_update().filter(
            order=order, razorpay_order_id=rz_order_id
        ).first()
        if not payment:
            raise PaymentRejected("Payment record not found.", 404)

        # ---- Idempotency: already processed -> do nothing at all ----------
        if payment.status in ("paid", "refunded"):
            if (
                payment.razorpay_payment_id
                and payment.razorpay_payment_id != rz_payment_id
            ):
                logger.critical(
                    "DUPLICATE PAYMENT: order %s already paid with %s, "
                    "second captured payment %s needs a refund.",
                    order.order_number,
                    payment.razorpay_payment_id,
                    rz_payment_id,
                )
            return order, False

        # A payment id may belong to one order only.
        if Payment.objects.filter(razorpay_payment_id=rz_payment_id).exclude(
            pk=payment.pk
        ).exists():
            raise PaymentRejected("This payment has already been used.", 409)

        # Pending, or cancelled by the abandoned-checkout job (late payment).
        if order.status not in ("pending", "cancelled"):
            raise PaymentRejected("This order cannot be processed again.", 409)

        # ---- Currency and amount must match what the SERVER expected ------
        if (rz_payment.get("currency") or "").upper() != EXPECTED_CURRENCY:
            logger.critical(
                "Currency mismatch on order %s payment %s",
                order.order_number, rz_payment_id,
            )
            raise PaymentRejected("Payment currency does not match.", 400)

        try:
            paid_paise = int(rz_payment.get("amount", -1))
        except (TypeError, ValueError):
            paid_paise = -1

        if paid_paise != to_paise(order.total) or payment.amount != order.total:
            logger.critical(
                "Amount mismatch on order %s payment %s: paid=%s expected=%s",
                order.order_number, rz_payment_id,
                paid_paise, to_paise(order.total),
            )
            raise PaymentRejected(
                "Paid amount does not match the order total.", 400
            )

        # ---- Everything checks out: stock, payment, order -----------------
        shortfalls = _deduct_stock(order)
        if shortfalls:
            logger.critical(
                "Stock shortfall on PAID order %s: %s",
                order.order_number, "; ".join(shortfalls),
            )

        payment.razorpay_payment_id = rz_payment_id
        if signature:
            payment.razorpay_signature = signature
        payment.status = "paid"
        payment.save(
            update_fields=["razorpay_payment_id", "razorpay_signature", "status"]
        )

        order.status = "confirmed"
        order.save(update_fields=["status", "updated_at"])

        order_id = order.id
        transaction.on_commit(lambda: _after_commit(order_id, shortfalls))

    return order, True
