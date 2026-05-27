from rest_framework import serializers
from .models import Cart, CartItem, Order, OrderItem
from store.serializers import ProductListSerializer


class CartItemSerializer(serializers.ModelSerializer):
    product = ProductListSerializer(read_only=True)
    product_id = serializers.IntegerField(write_only=True)
    subtotal = serializers.ReadOnlyField()

    class Meta:
        model = CartItem
        fields = ['id', 'product', 'product_id', 'quantity', 'subtotal', 'variant']


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    total = serializers.ReadOnlyField()
    item_count = serializers.ReadOnlyField()

    class Meta:
        model = Cart
        fields = ['id', 'items', 'total', 'item_count']


class OrderItemSerializer(serializers.ModelSerializer):
    subtotal = serializers.ReadOnlyField()

    class Meta:
        model = OrderItem
        fields = ['id', 'product_name', 'product_price',
                  'quantity', 'size', 'color', 'subtotal']


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    # ← Add customer name and email for admin display
    customer_name = serializers.SerializerMethodField()
    customer_email = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            'id', 'order_number', 'status',
            'customer_name', 'customer_email',   # ← new
            'full_name', 'email', 'phone',
            'address_line1', 'address_line2', 'city', 'state',
            'pincode', 'subtotal', 'shipping_charge', 'total',
            'items', 'notes', 'created_at'
        ]
        read_only_fields = ['id', 'order_number', 'status', 'created_at']

    def get_customer_name(self, obj):
        if obj.user:
            return f"{obj.user.first_name} {obj.user.last_name}".strip() or obj.user.email
        return obj.full_name   # fallback to shipping name

    def get_customer_email(self, obj):
        return obj.user.email if obj.user else obj.email