from django.contrib import admin
from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = [
        'order', 'razorpay_order_id', 'razorpay_payment_id',
        'amount', 'status', 'created_at',
    ]
    list_filter = ['status', 'created_at']
    search_fields = [
        'order__order_number', 'razorpay_order_id', 'razorpay_payment_id',
    ]
    readonly_fields = [
        'order', 'razorpay_order_id', 'razorpay_payment_id',
        'razorpay_signature', 'amount', 'status', 'created_at',
    ]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
