
from rest_framework import serializers
from .models import Cart, CartItem, Order, OrderItem
from store.serializers import ProductListSerializer


class CartItemSerializer(serializers.ModelSerializer):
    product = ProductListSerializer(read_only=True)
    product_id = serializers.IntegerField(write_only=True)
    subtotal = serializers.ReadOnlyField()

    class Meta:
        model = CartItem
        fields = [
            'id',
            'product',
            'product_id',
            'quantity',
            'subtotal',
            'variant',
        ]


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    total = serializers.ReadOnlyField()
    item_count = serializers.ReadOnlyField()

    class Meta:
        model = Cart
        fields = [
            'id',
            'items',
            'total',
            'item_count',
        ]


class OrderItemSerializer(serializers.ModelSerializer):
    subtotal = serializers.ReadOnlyField()
    primary_image = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = [
            'id',
            'product',
            'product_name',
            'product_price',
            'quantity',
            'size',
            'color',
            'product_type',
            'subtotal',
            'primary_image',
        ]

    def get_primary_image(self, obj):
        request = self.context.get('request')
        url = obj.primary_image

        if url and request:
            return request.build_absolute_uri(url)

        return url


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    customer_name = serializers.SerializerMethodField()
    customer_email = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            'id',
            'order_number',
            'status',

            # Customer details
            'customer_name',
            'customer_email',
            'full_name',
            'email',
            'phone',

            # Shipping address
            'address_line1',
            'address_line2',
            'city',
            'state',
            'pincode',

            # Order amounts
            'subtotal',
            'shipping_charge',
            'total',

            # Courier and tracking details
            'courier_name',
            'tracking_number',
            'tracking_url',

            # Other order details
            'items',
            'notes',
            'created_at',
        ]

        # Status can be updated by the admin order API.
        # Order number and creation date remain read-only.
        read_only_fields = [
            'id',
            'order_number',
            'created_at',
        ]

    def get_customer_name(self, obj):
        if obj.user:
            return (
                f"{obj.user.first_name} {obj.user.last_name}".strip()
                or obj.user.email
            )

        return obj.full_name

    def get_customer_email(self, obj):
        if obj.user:
            return obj.user.email

        return obj.email
