from django.contrib import admin, messages
from django.db import transaction

from .models import Order, OrderItem, Cart
from .utils import send_shipment_email


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ['subtotal']


def _shipment_ready(status, tracking_number):
    return status == 'shipped' and bool((tracking_number or '').strip())


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['order_number', 'user', 'status', 'payment_status',
                    'total', 'created_at']
    list_filter = ['status', 'payment__status', 'created_at']
    search_fields = ['order_number', 'email', 'full_name',
                     'razorpay_order_id', 'tracking_number']
    list_editable = ['status']
    inlines = [OrderItemInline]
    readonly_fields = ['order_number', 'razorpay_order_id',
                       'created_at', 'updated_at']

    @admin.display(description='Payment')
    def payment_status(self, obj):
        payment = getattr(obj, 'payment', None)
        return payment.status if payment else '-'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'payment')

    def save_model(self, request, obj, form, change):
        """
        Send the shipment email exactly when an order BECOMES
        'shipped with a tracking ID' - not on every later save.
        """
        was_ready = False
        if change and obj.pk:
            old = Order.objects.filter(pk=obj.pk).values(
                'status', 'tracking_number').first()
            if old:
                was_ready = _shipment_ready(old['status'], old['tracking_number'])

        obj.tracking_number = (obj.tracking_number or '').strip()
        obj.courier_name = (obj.courier_name or '').strip()
        obj.tracking_url = (obj.tracking_url or '').strip()

        super().save_model(request, obj, form, change)

        if obj.status == 'shipped' and not obj.tracking_number:
            messages.warning(
                request,
                f"Order {obj.order_number} is shipped but has no tracking ID, "
                "so no shipment email was sent. Add the tracking ID and save "
                "again to email the customer.",
            )
            return

        if _shipment_ready(obj.status, obj.tracking_number) and not was_ready:
            order_pk = obj.pk

            def _send():
                fresh = Order.objects.get(pk=order_pk)
                if send_shipment_email(fresh):
                    messages.success(
                        request,
                        f"Shipment email sent to {fresh.email}.")
                else:
                    messages.warning(
                        request,
                        f"Order saved, but the shipment email to "
                        f"{fresh.email} could not be sent. Check the logs.")

            transaction.on_commit(_send)
