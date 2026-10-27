
from django.db import models
from django.utils.text import slugify


class Category(models.Model):
    PRODUCT_TYPE_CHOICES = [
        ('dress', 'Dress'),
        ('jewelry', 'Jewelry'),
        ('hair_accessory', 'Hair Accessory'),
    ]

    product_type = models.CharField(
        max_length=20,
        choices=PRODUCT_TYPE_CHOICES,
        default='dress'
    )

    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField(blank=True)
    image = models.ImageField(
        upload_to='categories/',
        blank=True,
        null=True
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = 'Categories'

    def save(self, *args, **kwargs):
        # Generate a slug from the category name when missing.
        if not self.slug or not self.slug.strip():
            base_slug = slugify(self.name) or 'category'
        else:
            base_slug = slugify(self.slug) or slugify(self.name) or 'category'

        candidate = base_slug
        counter = 1

        # Ensure the slug is unique, including when a slug is supplied
        # explicitly. Exclude this category when editing an existing row.
        while Category.objects.filter(
            slug=candidate
        ).exclude(pk=self.pk).exists():
            candidate = f'{base_slug}-{counter}'
            counter += 1

        self.slug = candidate
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.get_product_type_display()})"


class Product(models.Model):
    BADGE_CHOICES = [
        ('new', 'New'),
        ('bestseller', 'Bestseller'),
        ('sale', 'Sale'),
        ('', 'None'),
    ]

    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='products'
    )

    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField(blank=True)

    price = models.DecimalField(max_digits=10, decimal_places=2)
    original_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True
    )

    stock = models.PositiveIntegerField(default=0)
    badge = models.CharField(
        max_length=20,
        choices=BADGE_CHOICES,
        blank=True
    )

    sizes = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    is_budget_friendly = models.BooleanField(default=False)
    is_own_brand = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.slug or not self.slug.strip():
            base_slug = slugify(self.name) or 'product'
        else:
            base_slug = slugify(self.slug) or slugify(self.name) or 'product'

        candidate = base_slug
        counter = 1

        while Product.objects.filter(
            slug=candidate
        ).exclude(pk=self.pk).exists():
            candidate = f'{base_slug}-{counter}'
            counter += 1

        self.slug = candidate
        super().save(*args, **kwargs)

    @property
    def product_type(self):
        """Return the product type of the associated category."""
        return self.category.product_type if self.category else None

    @property
    def discount_percent(self):
        try:
            original = float(self.original_price)
            price = float(self.price)

            if original and original > 0 and original > price:
                return round((1 - price / original) * 100)
        except (TypeError, ValueError):
            pass

        return 0

    def __str__(self):
        return self.name


class ProductImage(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='images'
    )
    image = models.ImageField(upload_to='products/')
    alt_text = models.CharField(max_length=255, blank=True)
    is_primary = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.product.name} - Image"


class ProductVariant(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='variants'
    )
    size = models.CharField(max_length=20, blank=True)
    color = models.CharField(max_length=50, blank=True)
    color_hex = models.CharField(max_length=7, blank=True)
    stock = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.product.name} - {self.size} / {self.color}"


class Review(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='reviews'
    )
    user = models.ForeignKey(
        'users.CustomUser',
        on_delete=models.CASCADE
    )
    rating = models.PositiveSmallIntegerField()
    title = models.CharField(max_length=100, blank=True)
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('product', 'user')

    def __str__(self):
        return (
            f"{self.user.email} -> {self.product.name} "
            f"({self.rating} stars)"
        )


class Wishlist(models.Model):
    user = models.OneToOneField(
        'users.CustomUser',
        on_delete=models.CASCADE,
        related_name='wishlist'
    )
    products = models.ManyToManyField(Product, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.email}'s wishlist"
