from django.urls import path
from .views import CreatePaymentView, VerifyPaymentView, RazorpayWebhookView

urlpatterns = [
    path('create-order/', CreatePaymentView.as_view(), name='payment-create'),
    path('verify/', VerifyPaymentView.as_view(), name='payment-verify'),
    path('webhook/', RazorpayWebhookView.as_view(), name='razorpay-webhook'),
]
