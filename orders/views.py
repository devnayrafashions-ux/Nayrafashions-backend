from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import Cart, CartItem, Order, OrderItem
from .serializers import CartSerializer, CartItemSerializer, OrderSerializer

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

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user).order_by('-created_at')

    def perform_create(self, serializer):
        # Save order with user
        order = serializer.save(user=self.request.user)

        # Save order items from request data
        items_data = self.request.data.get('items', [])
        for item in items_data:
            OrderItem.objects.create(
                order=order,
                product_id=item.get('product_id'),
                product_name=item.get('product_name', ''),
                product_price=item.get('product_price', 0),
                quantity=item.get('quantity', 1),
                size=item.get('size', ''),
                color=item.get('color', ''),
            )


class OrderDetailView(generics.RetrieveAPIView):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user)