from django.shortcuts import get_object_or_404

from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Cart, CartItem, Order
from .serializers import CartSerializer, OrderSerializer
from store.models import Product, ProductVariant


def customer_visible_orders(user):
    """
    Orders a customer should see in My Orders: real purchases only.

    Hidden (but kept in the database for reconciliation):
      * status 'pending'                      -> checkout started, unpaid
      * payment status 'created' / 'failed'   -> never paid (incl. orders
        later cancelled by the abandoned-checkout job)
    Orders with no Payment row (legacy) are shown unless still 'pending'.
    Paid orders that are later cancelled/refunded by staff stay visible.
    """
    return (
        Order.objects.filter(user=user)
        .exclude(status="pending")
        .exclude(payment__status__in=["created", "failed"])
        .prefetch_related("items")
        .order_by("-created_at")
    )


class CartView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        cart, _ = Cart.objects.get_or_create(user=request.user)
        return Response(CartSerializer(cart).data)

    def post(self, request):
        product_id = request.data.get("product_id")
        variant_id = request.data.get("variant_id")
        quantity = request.data.get("quantity", 1)

        try:
            quantity = int(quantity)
            if quantity < 1:
                raise ValueError
        except (TypeError, ValueError):
            return Response(
                {"error": "Quantity must be a positive integer."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        product = get_object_or_404(Product, id=product_id, is_active=True)

        variant = None
        if variant_id:
            variant = get_object_or_404(
                ProductVariant, id=variant_id, product=product
            )
            if variant.stock < quantity:
                return Response(
                    {"error": "Not enough stock for the selected size."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        elif product.variants.exists():
            return Response(
                {"error": "Please select a size."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        elif product.stock < quantity:
            return Response(
                {"error": "Not enough stock available."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cart, _ = Cart.objects.get_or_create(user=request.user)

        item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            variant=variant,
            defaults={"quantity": quantity},
        )

        if not created:
            item.quantity += quantity
            available_stock = variant.stock if variant else product.stock
            if item.quantity > available_stock:
                return Response(
                    {"error": "Requested quantity exceeds available stock."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            item.save(update_fields=["quantity"])

        return Response(
            CartSerializer(cart).data, status=status.HTTP_201_CREATED
        )

    def delete(self, request):
        item_id = request.data.get("item_id")
        CartItem.objects.filter(id=item_id, cart__user=request.user).delete()
        cart, _ = Cart.objects.get_or_create(user=request.user)
        return Response(CartSerializer(cart).data)


class OrderListView(generics.ListAPIView):
    """
    GET /api/orders/  ->  My Orders (paid purchases only).

    The old POST handler was removed on purpose. It created orders with
    shipping hard-coded to 0, no Payment record, and bypassed the single
    checkout flow (payments/create-order -> payments/verify). Orders are now
    created ONLY by /api/payments/create-order/ and confirmed ONLY by
    /api/payments/verify/ or the Razorpay webhook.
    """
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context

    def get_queryset(self):
        return customer_visible_orders(self.request.user)


# Backwards-compatible name so orders/urls.py keeps working unchanged.
OrderListCreateView = OrderListView


class OrderDetailView(generics.RetrieveAPIView):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context

    def get_queryset(self):
        return customer_visible_orders(self.request.user)
