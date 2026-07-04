from django.db import models
from store.models import Product, ProductVariant

class Cart(models.Model):
    user = models.OneToOneField(
        'users.CustomUser', on_delete=models.CASCADE,
        null=True, blank=True, related_name='cart'
    )
    session_key = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def total(self):
        return sum(item.subtotal for item in self.items.all())

    @property
    def item_count(self):
        return sum(item.quantity for item in self.items.all())

    def __str__(self):
        return f"Cart — {self.user.email if self.user else self.session_key}"


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    variant = models.ForeignKey(
        ProductVariant, on_delete=models.SET_NULL, null=True, blank=True
    )
    quantity = models.PositiveIntegerField(default=1)

    @property
    def subtotal(self):
        return self.product.price * self.quantity

    def __str__(self):
        return f"{self.quantity}x {self.product.name}"


class Order(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('processing', 'Processing'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
        ('refunded', 'Refunded'),
    ]

    user = models.ForeignKey(
        'users.CustomUser', on_delete=models.SET_NULL,
        null=True, related_name='orders'
    )
    order_number = models.CharField(max_length=20, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    # Shipping details
    full_name = models.CharField(max_length=200)
    email = models.EmailField()
    phone = models.CharField(max_length=15)
    address_line1 = models.CharField(max_length=255)
    address_line2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    pincode = models.CharField(max_length=10)

    # Pricing
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    shipping_charge = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2)

    # NEW: shipment tracking info, filled in by admin when marking an
    # order "Shipped". Used to email the customer their tracking details.
    tracking_number = models.CharField(max_length=100, blank=True)
    courier_name = models.CharField(max_length=100, blank=True)

    notes = models.TextField(blank=True)
    razorpay_order_id = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.order_number:
            import random, string
            self.order_number = 'NF' + ''.join(
                random.choices(string.digits, k=8)
            )
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Order #{self.order_number}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True)
    product_name = models.CharField(max_length=255)  # snapshot
    product_price = models.DecimalField(max_digits=10, decimal_places=2)  # snapshot
    quantity = models.PositiveIntegerField()
    size = models.CharField(max_length=20, blank=True)
    color = models.CharField(max_length=50, blank=True)
    # NEW: snapshot of 'dress' / 'jewelry' / 'hair_accessory' at order time.
    # Lets My Orders / Admin Orders always know whether to show a size chip
    # for this line item, even if the product or its category is later
    # edited or deleted — mirrors the existing product_name/product_price
    # snapshot pattern rather than relying on a live FK lookup.
    product_type = models.CharField(max_length=20, blank=True)

    @property
    def subtotal(self):
        return self.product_price * self.quantity

    @property
    def primary_image(self):
        """Falls back to the live product's image if it still exists;
        returns None if the product was deleted so the frontend can show
        a placeholder instead of erroring."""
        if not self.product:
            return None
        img = self.product.images.filter(is_primary=True).first() or self.product.images.first()
        return img.image.url if img else None

    def __str__(self):
        return f"{self.quantity}x {self.product_name}"