"""
Closes checkouts that were never paid.

For each pending order older than --minutes:
  * ask Razorpay whether a payment was captured; if yes, confirm the order
    through the normal path (recovers "paid but tab closed" cases);
  * if a payment is still 'authorized', leave it alone;
  * otherwise mark Payment=failed and Order=cancelled. Rows are kept for
    reconciliation; nothing is deleted. No stock was reserved, so nothing
    needs releasing.

Run every 10-15 minutes (cron / Render cron job / Railway cron):
    python manage.py expire_abandoned_orders
Preview only:
    python manage.py expire_abandoned_orders --dry-run
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from orders.models import Order
from payments.models import Payment
from payments.services import PaymentRejected, process_captured_payment
from payments.views import get_razorpay_client


class Command(BaseCommand):
    help = "Cancel unpaid, abandoned checkouts and recover late payments."

    def add_arguments(self, parser):
        parser.add_argument("--minutes", type=int, default=60)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        cutoff = timezone.now() - timedelta(minutes=opts["minutes"])
        dry = opts["dry_run"]
        client = get_razorpay_client()

        stale = Order.objects.filter(
            status="pending",
            created_at__lt=cutoff,
            payment__status__in=["created", "failed"],
        )

        recovered = cancelled = skipped = 0

        for order in stale.iterator():
            rz_id = order.razorpay_order_id
            payments = []

            if rz_id:
                try:
                    payments = client.order.payments(rz_id).get("items", [])
                except Exception as exc:
                    self.stderr.write(f"{order.order_number}: Razorpay error {exc}")
                    skipped += 1
                    continue

            captured = next(
                (p for p in payments if p.get("status") == "captured"), None
            )
            if captured:
                if dry:
                    self.stdout.write(f"{order.order_number}: would recover payment")
                else:
                    try:
                        process_captured_payment(captured)
                        recovered += 1
                    except PaymentRejected as exc:
                        self.stderr.write(f"{order.order_number}: {exc.message}")
                        skipped += 1
                continue

            if any(p.get("status") == "authorized" for p in payments):
                skipped += 1
                continue

            if dry:
                self.stdout.write(f"{order.order_number}: would cancel")
                cancelled += 1
                continue

            with transaction.atomic():
                locked = Order.objects.select_for_update().get(pk=order.pk)
                pay = Payment.objects.select_for_update().filter(order=locked).first()
                if (
                    locked.status == "pending"
                    and pay and pay.status in ("created", "failed")
                ):
                    pay.status = "failed"
                    pay.save(update_fields=["status"])
                    locked.status = "cancelled"
                    locked.save(update_fields=["status", "updated_at"])
                    cancelled += 1

        self.stdout.write(self.style.SUCCESS(
            f"recovered={recovered} cancelled={cancelled} skipped={skipped}"
            + (" (dry run)" if dry else "")
        ))
