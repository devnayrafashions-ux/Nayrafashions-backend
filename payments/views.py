import razorpay
import hmac, hashlib
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions, status
from orders.models import Order
from .models import Payment

client = razorpay.Client(
    auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
)

class CreatePaymentView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        # No order_id needed anymore — just the amount
        amount = request.data.get('amount')
        if not amount:
            return Response({'error': 'Amount is required'}, status=400)

        amount_paise = int(float(amount) * 100)

        rz_order = client.order.create({
            'amount': amount_paise,
            'currency': 'INR',
            'receipt': f"user_{request.user.id}",
        })

        # Don't create Payment or Order in DB yet — just return the Razorpay order
        return Response({
            'razorpay_order_id': rz_order['id'],
            'amount': amount_paise,
            'currency': 'INR',
            'key': settings.RAZORPAY_KEY_ID,
        })


class VerifyPaymentView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        rz_payment_id = request.data.get('razorpay_payment_id')
        rz_order_id   = request.data.get('razorpay_order_id')
        rz_signature  = request.data.get('razorpay_signature')

        if not all([rz_payment_id, rz_order_id, rz_signature]):
            return Response({'error': 'Missing payment fields'}, status=400)

        # Verify signature
        msg = f"{rz_order_id}|{rz_payment_id}"
        expected = hmac.new(
            settings.RAZORPAY_KEY_SECRET.encode(),
            msg.encode(),
            hashlib.sha256
        ).hexdigest()

        if expected != rz_signature:
            return Response({'error': 'Invalid signature'}, status=400)

        # Signature valid — find the order that was just created
        try:
            order = Order.objects.get(
                razorpay_order_id=rz_order_id,
                user=request.user
            )
        except Order.DoesNotExist:
            return Response({'error': 'Order not found'}, status=404)

        # Create Payment record and confirm order
        Payment.objects.create(
            order=order,
            razorpay_order_id=rz_order_id,
            razorpay_payment_id=rz_payment_id,
            razorpay_signature=rz_signature,
            amount=order.total,
            status='paid'
        )

        order.status = 'confirmed'
        order.save()

        return Response({'status': 'Payment verified successfully'})