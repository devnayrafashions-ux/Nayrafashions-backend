from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from orders.models import Order


class Command(BaseCommand):
    help = "Cancel pending orders whose payment was never completed."

    def add_arguments(self, parser):
        parser.add_argument("--minutes", type=int, default=120)

    def handle(self, *args, **opts):
        cutoff = timezone.now() - timedelta(minutes=opts["minutes"])
        qs = Order.objects.filter(
            status="pending",
            created_at__lt=cutoff,
            payment__status__in=["created", "failed"],
        )
        count = qs.update(status="cancelled")
        self.stdout.write(self.style.SUCCESS(f"Cancelled {count} abandoned order(s)"))