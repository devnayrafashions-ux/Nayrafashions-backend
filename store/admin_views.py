import json
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import (
    Sum,
    Count,
    Q,
    Case,
    When,
    Value,
    IntegerField,
)
from django_filters.rest_framework import DjangoFilterBackend

from rest_framework import generics, permissions, status, filters
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Category, Product, ProductImage, ProductVariant, Review
from .serializers import (
    CategorySerializer,
    ProductListSerializer,
    ProductDetailSerializer,
    ReviewSerializer,
)

from users.models import CustomUser
from orders.models import Order
from orders.serializers import OrderSerializer
from orders.utils import send_shipment_email

# Real purchases only: hides unpaid / abandoned checkouts.
from orders.views import admin_visible_orders


class IsAdminUser(permissions.BasePermission):
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.is_staff
        )


# ---------------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------------

def parse_bool(value, default=False):
    """Convert common form-data boolean values into Python booleans."""
    if value is None:
        return default

    if isinstance(value, bool):
        return value

    return str(value).strip().lower() in ("true", "1", "yes", "on")


def parse_json_list(value, default=None):
    """Safely parse a JSON list sent through multipart FormData."""
    if default is None:
        default = []

    if value is None or value == "":
        return default

    if isinstance(value, list):
        return value

    try:
        result = json.loads(value)
        return result if isinstance(result, list) else default
    except (json.JSONDecodeError, TypeError, ValueError):
        return default


def get_uploaded_images(request):
    """
    Accept multiple images under 'images' or repeated 'image' fields.
    Also supports the existing single-image frontend field.
    """
    uploaded = []

    uploaded.extend(request.FILES.getlist("images"))
    uploaded.extend(request.FILES.getlist("image"))

    # Remove duplicate file objects if the same field was submitted twice.
    unique = []
    seen = set()

    for image in uploaded:
        identifier = id(image)
        if identifier not in seen:
            seen.add(identifier)
            unique.append(image)

    return unique


def save_product_images(product, uploaded_images):
    """
    Add images without deleting existing images.
    The first image becomes primary only when no primary image exists.
    """
    has_primary = ProductImage.objects.filter(
        product=product,
        is_primary=True,
    ).exists()

    for image in uploaded_images:
        ProductImage.objects.create(
            product=product,
            image=image,
            is_primary=not has_primary,
        )
        has_primary = True


def normalize_sizes(raw_sizes):
    """
    Keep Product.sizes as a list of size labels, for example:
    ['S', 'M', 'L', 'XL'].

    Also accepts entries such as:
    [{'size': 'S', 'stock': 5}, {'size': 'M', 'stock': 8}].
    """
    result = []

    for item in raw_sizes:
        if isinstance(item, dict):
            size = item.get("size")
        else:
            size = item

        if size is None:
            continue

        size = str(size).strip()

        if size and size not in result:
            result.append(size)

    return result


def get_size_stock_data(request, raw_sizes):
    """
    Read per-size inventory from either:
      - variants: [{"size": "S", "stock": 5}, ...]
      - size_stock: [{"size": "S", "stock": 5}, ...]

    If raw_sizes contains stock values, those are also accepted.
    Returns None when no explicit per-size inventory was provided.
    """
    variant_data = request.data.get("variants")
    if variant_data is None:
        variant_data = request.data.get("size_stock")

    if variant_data is not None:
        parsed = parse_json_list(variant_data, default=None)

        # An explicit empty list is valid and means no variant stock entries.
        if parsed is not None:
            stock_map = {}

            for item in parsed:
                if not isinstance(item, dict) or not item.get("size"):
                    continue

                try:
                    quantity = int(item.get("stock", 0))
                except (TypeError, ValueError):
                    raise ValueError(
                        "Stock for each size must be a whole number."
                    )

                if quantity < 0:
                    raise ValueError(
                        "Stock for each size cannot be negative."
                    )

                stock_map[str(item["size"]).strip()] = quantity

            return stock_map

    if raw_sizes and all(isinstance(item, dict) for item in raw_sizes):
        stock_map = {}

        for item in raw_sizes:
            size = item.get("size")
            if not size:
                continue

            try:
                quantity = int(item.get("stock", 0))
            except (TypeError, ValueError):
                raise ValueError(
                    "Stock for each size must be a whole number."
                )

            if quantity < 0:
                raise ValueError(
                    "Stock for each size cannot be negative."
                )

            stock_map[str(size).strip()] = quantity

        return stock_map

    return None


def sync_product_variants(product, sizes, size_stock_map):
    """
    Save stock for each selected size and synchronize total product stock.
    Preserve existing variants that are not selected, so historical
    cart/order references are not broken.
    """
    sizes = normalize_sizes(sizes)
    size_stock_map = size_stock_map or {}

    for size in sizes:
        if size not in size_stock_map:
            continue

        variant, _ = ProductVariant.objects.get_or_create(
            product=product,
            size=size,
            color="",
            defaults={
                "color_hex": "",
                "stock": size_stock_map[size],
            },
        )

        # Explicitly save the submitted quantity, including zero.
        if variant.stock != size_stock_map[size]:
            variant.stock = size_stock_map[size]
            variant.save(update_fields=["stock"])

    # Total stock includes all variants still associated with this product.
    total_stock = (
        ProductVariant.objects.filter(product=product)
        .aggregate(total=Sum("stock"))["total"]
        or 0
    )

    product.stock = total_stock
    product.save(update_fields=["stock"])

    # Do not delete variants that may be referenced by cart items or orders.
    total_variant_stock = ProductVariant.objects.filter(
        product=product
    ).aggregate(total=Sum("stock"))["total"] or 0

    product.stock = total_variant_stock
    product.save(update_fields=["stock"])


def validate_price(value, field_name, allow_empty=False):
    if value in (None, ""):
        if allow_empty:
            return None
        raise ValueError(f"{field_name} is required.")

    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{field_name} must be a valid number.")

    if not amount.is_finite() or amount < 0:
        raise ValueError(f"{field_name} cannot be negative.")

    return amount


def validate_stock(value):
    try:
        stock = int(value or 0)
    except (TypeError, ValueError):
        raise ValueError("Stock must be a whole number.")

    if stock < 0:
        raise ValueError("Stock cannot be negative.")

    return stock


# ---------------------------------------------------------
# ADMIN DASHBOARD
# ---------------------------------------------------------

class AdminDashboardView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        total_revenue = (
            Order.objects.filter(
                status__in=[
                    "confirmed",
                    "processing",
                    "shipped",
                    "delivered",
                ]
            ).aggregate(total=Sum("total"))["total"]
            or 0
        )

        # Only real (paid) orders are counted. Unpaid/abandoned checkouts
        # are hidden everywhere in the admin panel.
        visible = admin_visible_orders()

        data = {
            "total_revenue": float(total_revenue),
            "total_orders": visible.count(),
            "total_products": Product.objects.count(),
            "active_products": Product.objects.filter(
                is_active=True
            ).count(),
            "total_customers": CustomUser.objects.filter(
                is_staff=False
            ).count(),
            # Unpaid "pending" orders are hidden, so "pending" here means
            # paid orders waiting for staff action (status "confirmed").
            "pending_orders": visible.filter(status="confirmed").count(),
            "processing_orders": visible.filter(status="processing").count(),
            "shipped_orders": visible.filter(status="shipped").count(),
            "delivered_orders": visible.filter(status="delivered").count(),
            "cancelled_orders": visible.filter(status="cancelled").count(),
        }

        return Response(data)


# ---------------------------------------------------------
# ADMIN CATEGORIES
# ---------------------------------------------------------

class AdminCategoryListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAdminUser]
    queryset = Category.objects.annotate(
        product_count=Count("products")
    ).order_by("name")
    serializer_class = CategorySerializer

    def create(self, request, *args, **kwargs):
        serializer = CategorySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED,
        )


class AdminCategoryDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminUser]
    queryset = Category.objects.all().order_by("name")
    serializer_class = CategorySerializer


# ---------------------------------------------------------
# ADMIN PRODUCTS
# ---------------------------------------------------------

class AdminProductListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAdminUser]

    queryset = (
        Product.objects.all()
        .select_related("category")
        .prefetch_related("images", "variants")
        .order_by("-created_at")
    )

    serializer_class = ProductListSerializer

    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]

    filterset_fields = [
        "category__slug",
        "badge",
        "is_active",
        "is_featured",
        "is_budget_friendly",
        "is_own_brand",
    ]

    search_fields = ["name", "description"]
    ordering_fields = ["price", "created_at", "stock"]
    ordering = ["-created_at"]

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        data = request.data

        try:
            raw_sizes = parse_json_list(data.get("sizes"))
            sizes = normalize_sizes(raw_sizes)

            price = validate_price(data.get("price"), "Price")
            original_price = validate_price(
                data.get("original_price"),
                "Original price",
                allow_empty=True,
            )
            stock = validate_stock(data.get("stock"))

            size_stock_map = get_size_stock_data(
                request,
                raw_sizes,
            )

            category_id = (
                int(data.get("category"))
                if data.get("category")
                else None
            )

        except (ValueError, TypeError) as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        product = Product.objects.create(
            name=data.get("name", "").strip(),
            description=data.get("description", ""),
            price=price,
            original_price=original_price,
            stock=stock,
            badge=data.get("badge", ""),
            is_active=parse_bool(data.get("is_active"), True),
            is_featured=parse_bool(data.get("is_featured"), False),
            is_budget_friendly=parse_bool(
                data.get("is_budget_friendly"),
                False,
            ),
            is_own_brand=parse_bool(
                data.get("is_own_brand"),
                False,
            ),
            category_id=category_id,
            sizes=sizes,
        )

        uploaded_images = get_uploaded_images(request)
        save_product_images(product, uploaded_images)

        # Only synchronize size inventory when the request explicitly
        # supplies per-size stock data.
        if size_stock_map is not None:
            sync_product_variants(
                product,
                sizes,
                size_stock_map,
            )

        serializer = ProductDetailSerializer(
            product,
            context={"request": request},
        )

        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED,
        )


class AdminProductDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminUser]

    queryset = (
        Product.objects.all()
        .select_related("category")
        .prefetch_related("images", "variants")
        .order_by("-created_at")
    )

    serializer_class = ProductDetailSerializer

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        product = self.get_object()
        data = request.data

        try:
            if "price" in data:
                product.price = validate_price(
                    data.get("price"),
                    "Price",
                )

            if "original_price" in data:
                product.original_price = validate_price(
                    data.get("original_price"),
                    "Original price",
                    allow_empty=True,
                )

            if "stock" in data:
                product.stock = validate_stock(data.get("stock"))

            if "sizes" in data:
                raw_sizes = parse_json_list(data.get("sizes"))
                product.sizes = normalize_sizes(raw_sizes)
            else:
                raw_sizes = product.sizes or []

            size_stock_map = get_size_stock_data(
                request,
                raw_sizes,
            )

            if "category" in data:
                category_value = data.get("category")
                product.category_id = (
                    int(category_value) if category_value else None
                )

        except (ValueError, TypeError) as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if "name" in data:
            product.name = data.get("name", "").strip()

        if "description" in data:
            product.description = data.get("description", "")

        if "badge" in data:
            product.badge = data.get("badge", "")

        if "is_active" in data:
            product.is_active = parse_bool(data.get("is_active"))

        if "is_featured" in data:
            product.is_featured = parse_bool(data.get("is_featured"))

        if "is_budget_friendly" in data:
            product.is_budget_friendly = parse_bool(
                data.get("is_budget_friendly")
            )

        if "is_own_brand" in data:
            product.is_own_brand = parse_bool(
                data.get("is_own_brand")
            )

        product.save()

        # New uploads are added to the existing gallery. Existing images
        # are not deleted when editing a product.
        uploaded_images = get_uploaded_images(request)
        save_product_images(product, uploaded_images)

        if size_stock_map is not None:
            sync_product_variants(
                product,
                product.sizes or [],
                size_stock_map,
            )

        serializer = ProductDetailSerializer(
            product,
            context={"request": request},
        )

        return Response(serializer.data)

    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)


class AdminProductToggleView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        try:
            product = Product.objects.get(pk=pk)
            product.is_active = not product.is_active
            product.save(update_fields=["is_active"])

            return Response({"is_active": product.is_active})

        except Product.DoesNotExist:
            return Response(
                {"error": "Product not found."},
                status=status.HTTP_404_NOT_FOUND,
            )


# ---------------------------------------------------------
# ADMIN ORDERS
# ---------------------------------------------------------

ACTIONABLE_STATUSES = ["pending", "confirmed", "processing"]


class AdminOrderListView(generics.ListAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = OrderSerializer

    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]

    search_fields = [
        "order_number",
        "full_name",
        "email",
        "phone",
        "city",
    ]

    ordering_fields = ["created_at", "total", "status"]
    ordering = ["-created_at"]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context

    def get_queryset(self):
        # Real (paid) orders only; unpaid/abandoned checkouts are hidden.
        queryset = admin_visible_orders()

        status_param = self.request.query_params.get("status")
        if status_param:
            queryset = queryset.filter(status=status_param)

        search_param = self.request.query_params.get("search")
        if search_param:
            queryset = queryset.filter(
                Q(order_number__icontains=search_param)
                | Q(full_name__icontains=search_param)
                | Q(email__icontains=search_param)
                | Q(phone__icontains=search_param)
                | Q(city__icontains=search_param)
            )

        queryset = queryset.annotate(
            priority=Case(
                When(
                    status__in=ACTIONABLE_STATUSES,
                    then=Value(0),
                ),
                default=Value(1),
                output_field=IntegerField(),
            )
        ).order_by("priority", "created_at")

        # Respect an explicit ordering requested by the frontend.
        ordering_param = self.request.query_params.get("ordering")
        if ordering_param:
            queryset = self.filter_queryset(queryset)
            return queryset

        return queryset


class AdminOrderDetailView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = OrderSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context

    def get_queryset(self):
        # Hidden (unpaid) orders cannot be opened or edited by ID.
        return admin_visible_orders()

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        from django.core.exceptions import ValidationError
        from django.core.validators import URLValidator
        import logging

        logger = logging.getLogger(__name__)
        order = self.get_object()

        new_status = request.data.get("status", order.status)
        was_already_shipped = order.status == "shipped"

        if new_status not in dict(Order.STATUS_CHOICES):
            return Response(
                {"error": "Invalid order status."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Preserve existing tracking values if a field was not submitted.
        courier_name = str(
            request.data.get("courier_name", order.courier_name) or ""
        ).strip()

        tracking_number = str(
            request.data.get("tracking_number", order.tracking_number) or ""
        ).strip()

        tracking_url = str(
            request.data.get("tracking_url", order.tracking_url) or ""
        ).strip()

        # Validate all shipping details before marking an order shipped.
        if new_status == "shipped":
            if not courier_name:
                return Response(
                    {"error": "Please enter the courier name."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if not tracking_number:
                return Response(
                    {"error": "Please enter the tracking ID/AWB number."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if not tracking_url:
                return Response(
                    {"error": "Please enter the courier tracking URL."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                URLValidator(schemes=["https"])(tracking_url)
            except ValidationError:
                return Response(
                    {"error": "Please enter a valid HTTPS tracking URL."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Preserve the existing restriction on cancelled/refunded orders.
        if (
            order.status in ("cancelled", "refunded")
            and new_status not in ("cancelled", "refunded")
        ):
            return Response(
                {
                    "error": (
                        "Cancelled or refunded orders cannot be reopened."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        order.courier_name = courier_name
        order.tracking_number = tracking_number
        order.tracking_url = tracking_url
        order.status = new_status

        try:
            order.save()

            # Send once, only after the order and tracking details are saved.
            if new_status == "shipped" and not was_already_shipped:
                order_id = order.pk

                def send_email_after_commit():
                    try:
                        saved_order = Order.objects.get(pk=order_id)
                        sent = send_shipment_email(saved_order)

                        if not sent:
                            logger.error(
                                "Shipment email was not sent for order %s",
                                saved_order.order_number,
                            )
                    except Exception:
                        logger.exception(
                            "Shipment email failed for order ID %s",
                            order_id,
                        )

                transaction.on_commit(send_email_after_commit)

        except Exception:
            logger.exception("Admin order update failed")
            return Response(
                {"error": "Could not update the order. Check server logs."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        serializer = self.get_serializer(order)
        return Response(serializer.data)

    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)


# ---------------------------------------------------------
# ADMIN CUSTOMERS
# ---------------------------------------------------------

class AdminCustomerListView(generics.ListAPIView):
    permission_classes = [IsAdminUser]
    filter_backends = [filters.SearchFilter]
    search_fields = ["email", "first_name", "last_name", "phone"]

    def get_queryset(self):
        # Count only real (paid) orders, not unpaid/abandoned checkouts.
        paid_orders = ~Q(orders__status="pending") & ~Q(
            orders__payment__status__in=["created", "failed"]
        )

        return (
            CustomUser.objects.filter(is_staff=False)
            .annotate(
                order_count=Count("orders", filter=paid_orders, distinct=True)
            )
            .order_by("-date_joined")
        )

    def list(self, request, *args, **kwargs):
        from users.serializers import UserSerializer

        queryset = self.filter_queryset(self.get_queryset())
        serializer = UserSerializer(queryset, many=True)
        data = serializer.data

        for index, customer in enumerate(queryset):
            data[index]["order_count"] = customer.order_count

        return Response(data)


class AdminCustomerDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        return CustomUser.objects.filter(is_staff=False)

    def retrieve(self, request, *args, **kwargs):
        from users.serializers import UserSerializer

        customer = self.get_object()
        data = UserSerializer(customer).data

        orders = admin_visible_orders().filter(user=customer)

        data["orders"] = OrderSerializer(
            orders,
            many=True,
            context={"request": request},
        ).data

        data["order_count"] = orders.count()

        return Response(data)


# ---------------------------------------------------------
# ADMIN REVIEWS
# ---------------------------------------------------------

class AdminReviewListView(generics.ListAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = ReviewSerializer

    def get_queryset(self):
        return (
            Review.objects.all()
            .select_related("user", "product")
            .order_by("-created_at")
        )


class AdminReviewDeleteView(generics.DestroyAPIView):
    permission_classes = [IsAdminUser]
    queryset = Review.objects.all().order_by("-created_at")