from rest_framework import serializers
from .models import Category, Product, ProductImage, ProductVariant, Review, Wishlist


class CategorySerializer(serializers.ModelSerializer):
    product_count = serializers.SerializerMethodField()
    product_type_display = serializers.CharField(
        source='get_product_type_display', read_only=True
    )

    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'description', 'image',
                  'is_active', 'product_count',
                  'product_type', 'product_type_display']

    def get_product_count(self, obj):
        return obj.products.filter(is_active=True).count()


class ProductImageSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()

    class Meta:
        model = ProductImage
        fields = ['id', 'image', 'alt_text', 'is_primary']

    def get_image(self, obj):
        request = self.context.get('request')
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        elif obj.image:
            return obj.image.url
        return None


class ProductVariantSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductVariant
        fields = ['id', 'size', 'color', 'color_hex', 'stock']


class ReviewSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = ['id', 'user_name', 'rating', 'title', 'body', 'created_at']
        read_only_fields = ['id', 'user_name', 'created_at']

    def get_user_name(self, obj):
        return f"{obj.user.first_name} {obj.user.last_name}".strip() or obj.user.email


class ProductListSerializer(serializers.ModelSerializer):
    primary_image = serializers.SerializerMethodField()
    category_name = serializers.SerializerMethodField()
    discount_percent = serializers.SerializerMethodField()
    # NEW: surfaced directly so the frontend can branch on it
    # (e.g. hide size chips) without needing a separate category lookup.
    product_type = serializers.CharField(read_only=True)

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'slug', 'price', 'original_price',
            'discount_percent', 'badge', 'stock',
            'is_active', 'is_featured',
            'sizes', 'category', 'product_type',
            'primary_image', 'category_name',
        ]

    def get_primary_image(self, obj):
        request = self.context.get('request')
        img = obj.images.filter(is_primary=True).first() or obj.images.first()
        if img and request:
            return request.build_absolute_uri(img.image.url)
        elif img:
            return img.image.url
        return None

    def get_category_name(self, obj):
        return obj.category.name if obj.category else None

    def get_discount_percent(self, obj):
        return obj.discount_percent


class ProductDetailSerializer(serializers.ModelSerializer):
    images = ProductImageSerializer(many=True, read_only=True)
    variants = ProductVariantSerializer(many=True, read_only=True)
    reviews = ReviewSerializer(many=True, read_only=True)
    category = CategorySerializer(read_only=True)
    category_name = serializers.SerializerMethodField()
    primary_image = serializers.SerializerMethodField()
    avg_rating = serializers.SerializerMethodField()
    discount_percent = serializers.SerializerMethodField()
    product_type = serializers.CharField(read_only=True)

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'slug', 'description', 'price', 'original_price',
            'discount_percent', 'badge', 'stock',
            'is_active', 'is_featured', 'sizes', 'product_type',
            'category', 'category_name', 'primary_image',
            'images', 'variants', 'reviews',
            'avg_rating', 'created_at',
        ]

    def get_primary_image(self, obj):
        request = self.context.get('request')
        img = obj.images.filter(is_primary=True).first() or obj.images.first()
        if img and request:
            return request.build_absolute_uri(img.image.url)
        elif img:
            return img.image.url
        return None

    def get_category_name(self, obj):
        return obj.category.name if obj.category else None

    def get_discount_percent(self, obj):
        return obj.discount_percent

    def get_avg_rating(self, obj):
        reviews = obj.reviews.all()
        if not reviews:
            return None
        return round(sum(r.rating for r in reviews) / len(reviews), 1)