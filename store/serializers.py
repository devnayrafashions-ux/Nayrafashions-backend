
from rest_framework import serializers

from .models import (
    Category,
    Product,
    ProductImage,
    ProductVariant,
    Review,
    Wishlist,
)


class CategorySerializer(serializers.ModelSerializer):
    slug = serializers.SlugField(
        required=False,
        allow_blank=True,
    )

    product_count = serializers.SerializerMethodField()

    product_type_display = serializers.CharField(
        source="get_product_type_display",
        read_only=True,
    )

    class Meta:
        model = Category
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "image",
            "is_active",
            "product_count",
            "product_type",
            "product_type_display",
        ]
        read_only_fields = [
            "id",
            "product_count",
            "product_type_display",
        ]

    def get_product_count(self, obj):
        return obj.products.filter(is_active=True).count()

    def create(self, validated_data):
        return Category.objects.create(**validated_data)


class ProductImageSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()

    class Meta:
        model = ProductImage
        fields = [
            "id",
            "image",
            "alt_text",
            "is_primary",
        ]

    def get_image(self, obj):
        request = self.context.get("request")

        if not obj.image:
            return None

        try:
            image_url = obj.image.url
        except (ValueError, AttributeError):
            return None

        if request:
            return request.build_absolute_uri(image_url)

        return image_url


class ProductVariantSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductVariant
        fields = [
            "id",
            "size",
            "color",
            "color_hex",
            "stock",
        ]


class ReviewSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = [
            "id",
            "user_name",
            "rating",
            "title",
            "body",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "user_name",
            "created_at",
        ]

    def get_user_name(self, obj):
        if not obj.user:
            return "Customer"

        return (
            f"{obj.user.first_name} {obj.user.last_name}".strip()
            or obj.user.email
        )



class ProductListSerializer(serializers.ModelSerializer):
    primary_image = serializers.SerializerMethodField()
    category_name = serializers.SerializerMethodField()
    discount_percent = serializers.SerializerMethodField()
    product_type = serializers.CharField(read_only=True)

    # Include each size and its saved stock quantity.
    variants = ProductVariantSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "price",
            "original_price",
            "discount_percent",
            "badge",
            "stock",
            "is_active",
            "is_featured",
            "is_budget_friendly",
            "is_own_brand",
            "sizes",
            "category",
            "product_type",
            "primary_image",
            "category_name",
            "variants",
        ]

    def get_primary_image(self, obj):
        request = self.context.get("request")
        image = (
            obj.images.filter(is_primary=True).first()
            or obj.images.first()
        )

        if not image or not image.image:
            return None

        try:
            image_url = image.image.url
        except (ValueError, AttributeError):
            return None

        if request:
            return request.build_absolute_uri(image_url)

        return image_url

    def get_category_name(self, obj):
        return obj.category.name if obj.category else None

    def get_discount_percent(self, obj):
        return obj.discount_percent


class ProductDetailSerializer(serializers.ModelSerializer):
    # Returns every saved product image for the gallery.
    images = ProductImageSerializer(
        many=True,
        read_only=True,
    )

    # Returns stock for each size/variant.
    variants = ProductVariantSerializer(
        many=True,
        read_only=True,
    )

    reviews = ReviewSerializer(
        many=True,
        read_only=True,
    )

    category = CategorySerializer(read_only=True)
    category_name = serializers.SerializerMethodField()
    primary_image = serializers.SerializerMethodField()
    avg_rating = serializers.SerializerMethodField()
    discount_percent = serializers.SerializerMethodField()
    product_type = serializers.CharField(read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "price",
            "original_price",
            "discount_percent",
            "badge",
            "stock",
            "is_active",
            "is_featured",
            "is_budget_friendly",
            "is_own_brand",
            "sizes",
            "product_type",
            "category",
            "category_name",
            "primary_image",
            "images",
            "variants",
            "reviews",
            "avg_rating",
            "created_at",
        ]

    def get_primary_image(self, obj):
        request = self.context.get("request")

        image = (
            obj.images.filter(is_primary=True).first()
            or obj.images.first()
        )

        if not image or not image.image:
            return None

        try:
            image_url = image.image.url
        except (ValueError, AttributeError):
            return None

        if request:
            return request.build_absolute_uri(image_url)

        return image_url

    def get_category_name(self, obj):
        return obj.category.name if obj.category else None

    def get_discount_percent(self, obj):
        return obj.discount_percent

    def get_avg_rating(self, obj):
        ratings = list(
            obj.reviews.values_list("rating", flat=True)
        )

        if not ratings:
            return None

        return round(sum(ratings) / len(ratings), 1)
