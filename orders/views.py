from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import F
from django.db.models.functions import Greatest
from .models import Cart, CartItem, Order, OrderItem
from .serializers import CartSerializer, CartItemSerializer, OrderSerializer
from store.models import Product


class CartView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        cart, _ = Cart.objects.get_or_create(user=request.user)
        return Response(CartSerializer(cart).data)

    def post(self, request):
        cart, _ = Cart.objects.get_or_create(user=request.user)
        product_id = request.data.get('product_id')
        quantity = int(request.data.get('quantity', 1))
        item, created = CartItem.objects.get_or_create(
            cart=cart, product_id=product_id
        )
        if not created:
            item.quantity += quantity
        else:
            item.quantity = quantity
        item.save()
        return Response(CartSerializer(cart).data, status=status.HTTP_201_CREATED)

    def delete(self, request):
        item_id = request.data.get('item_id')
        CartItem.objects.filter(id=item_id, cart__user=request.user).delete()
        cart = Cart.objects.get(user=request.user)
        return Response(CartSerializer(cart).data)


class OrderListCreateView(generics.ListCreateAPIView):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_context(self):
        # Needed so OrderItemSerializer.get_primary_image can build
        # absolute image URLs (request.build_absolute_uri).
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

    def get_queryset(self):
        return Order.objects.filter(
            user=self.request.user
        ).order_by('-created_at')

    def perform_create(self, serializer):
        # Order is created AFTER payment succeeds on frontend
        # razorpay_order_id is passed from frontend
        razorpay_order_id = self.request.data.get(
            'razorpay_order_id', ''
        )

        order = serializer.save(
            user=self.request.user,
            status='pending',
            razorpay_order_id=razorpay_order_id,
        )

        items_data = self.request.data.get('items', [])

        for item in items_data:
            product_id = item.get('product_id')
            quantity = item.get('quantity', 1)

            OrderItem.objects.create(
                order=order,
                product_id=product_id,
                product_name=item.get('product_name', ''),
                product_price=item.get('product_price', 0),
                quantity=quantity,
                size=item.get('size', ''),
                color=item.get('color', ''),
                # NEW: snapshot the type sent from checkout (dress /
                # jewelry / hair_accessory) so order history stays accurate
                # even if the product is later edited or removed.
                product_type=item.get('product_type', ''),
            )

            # NEW: decrement stock on the actual Product row every time
            # an order is placed, so admin's Products page always
            # reflects real remaining stock without any manual update.
            # Greatest(..., 0) prevents stock from ever going negative
            # even if quantity somehow exceeds what's left (e.g. two
            # near-simultaneous orders for the last few units).
            if product_id:
                Product.objects.filter(id=product_id).update(
                    stock=Greatest(F('stock') - quantity, 0)
                )


class OrderDetailView(generics.RetrieveAPIView):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user)