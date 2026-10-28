"""
Test SMTP and the real email templates.

  python manage.py send_test_email you@example.com
      -> plain SMTP test; raises the REAL error if SMTP is misconfigured.

  python manage.py send_test_email you@example.com --order NF12345678 --kind confirmation
  python manage.py send_test_email you@example.com --order NF12345678 --kind shipment
      -> renders that order's real email but sends it to YOU, not the customer.
"""
from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError

from orders.models import Order
from orders.utils import send_order_confirmation_email, send_shipment_email


class Command(BaseCommand):
    help = "Send a test email to verify SMTP and templates."

    def add_arguments(self, parser):
        parser.add_argument("to")
        parser.add_argument("--order")
        parser.add_argument("--kind", choices=["confirmation", "shipment"],
                            default="confirmation")

    def handle(self, *args, **opts):
        to = opts["to"]

        if not opts["order"]:
            sent = send_mail(
                "Nayra Fashions SMTP test",
                "If you can read this, SMTP is working.",
                getattr(settings, "DEFAULT_FROM_EMAIL", None)
                or settings.EMAIL_HOST_USER,
                [to],
                fail_silently=False,
            )
            self.stdout.write(self.style.SUCCESS(f"SMTP OK ({sent} sent) -> {to}"))
            return

        try:
            order = Order.objects.get(order_number=opts["order"])
        except Order.DoesNotExist:
            raise CommandError("Order not found")

        order.email = to  # in memory only; never saved
        fn = (send_order_confirmation_email if opts["kind"] == "confirmation"
              else send_shipment_email)
        ok = fn(order)
        self.stdout.write(
            self.style.SUCCESS("Sent") if ok
            else self.style.ERROR("Failed - see the log output above")
        )
