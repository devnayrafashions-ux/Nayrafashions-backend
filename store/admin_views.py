import json
from rest_framework import generics, permissions, status, filters
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Sum, Count, Q
from django.utils import timezone
from datetime import timedelta
from .models import Category, Product, ProductImage, Review
from .serializers import CategorySerializer, ProductListSerializer, ProductDetailSerializer, ReviewSerializer
from users.models import CustomUser
from orders.models import Order
from orders.serializers import OrderSerializer


class IsAdminUser(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.is_staff


class AdminDashboardView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        total_revenue = Order.objects.filter(
            status__in=['confirmed', 'processing', 'shipped', 'delivered']
        ).aggregate(total=Sum('total'))['total'] or 0

        data = {
            'total_revenue': float(total_revenue),
            'total_orders': Order.objects.count(),
            'total_products': Product.objects.count(),
            'active_products': Product.objects.filter(is_active=True).count(),
            'total_customers': CustomUser.objects.filter(is_staff=False).count(),
            'pending_orders': Order.objects.filter(status='pending').count(),
            'processing_orders': Order.objects.filter(status='processing').count(),
            'shipped_orders': Order.objects.filter(status='shipped').count(),
            'delivered_orders': Order.objects.filter(status='delivered').count(),
            'cancelled_orders': Order.objects.filter(status='cancelled').count(),
        }
        return Response(data)


class AdminCategoryListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAdminUser]
    queryset = Category.objects.annotate(product_count=Count('products')).order_by('name')  # ← fixed
    serializer_class = CategorySerializer

    def create(self, request, *args, **kwargs):
        serializer = CategorySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class AdminCategoryDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminUser]
    queryset = Category.objects.all().order_by('name')  # ← fixed
    serializer_class = CategorySerializer


class AdminProductListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAdminUser]
    queryset = Product.objects.all().select_related('category').prefetch_related('images').order_by('-created_at')  # ← fixed
    serializer_class = ProductListSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['category__slug', 'badge', 'is_active', 'is_featured']
    search_fields = ['name', 'description']
    ordering_fields = ['price', 'created_at', 'stock']
    ordering = ['-created_at']

    def create(self, request, *args, **kwargs):
        data = request.data

        try:
            sizes = json.loads(data.get('sizes', '[]'))
        except (json.JSONDecodeError, TypeError):
            sizes = []

        product = Product.objects.create(
            name=data.get('name'),
            description=data.get('description', ''),
            price=float(data.get('price') or 0),
            original_price=float(data.get('original_price')) if data.get('original_price') else None,
            stock=int(data.get('stock') or 0),
            badge=data.get('badge', ''),
            is_active=data.get('is_active', 'true').lower() == 'true',
            is_featured=data.get('is_featured', 'false').lower() == 'true',
            category_id=int(data.get('category')) if data.get('category') else None,
            sizes=sizes,
        )

        image = request.FILES.get('image')
        if image:
            ProductImage.objects.create(product=product, image=image, is_primary=True)

        serializer = ProductListSerializer(product, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class AdminProductDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminUser]
    queryset = Product.objects.all().select_related('category').prefetch_related('images').order_by('-created_at')  # ← fixed
    serializer_class = ProductDetailSerializer

    def update(self, request, *args, **kwargs):
        product = self.get_object()
        data = request.data

        product.name = data.get('name', product.name)
        product.description = data.get('description', product.description)
        product.price = data.get('price', product.price)
        product.original_price = data.get('original_price') or None
        product.stock = data.get('stock', product.stock)
        product.badge = data.get('badge', product.badge)
        product.is_active = data.get('is_active', str(product.is_active)).lower() in ('true', '1', 'on')
        product.is_featured = data.get('is_featured', str(product.is_featured)).lower() in ('true', '1', 'on')

        if data.get('category'):
            product.category_id = int(data.get('category'))

        if 'sizes' in data:
            try:
                product.sizes = json.loads(data.get('sizes'))
            except (json.JSONDecodeError, TypeError):
                product.sizes = []

        product.save()

        image = request.FILES.get('image')
        if image:
            ProductImage.objects.filter(product=product, is_primary=True).delete()
            ProductImage.objects.create(product=product, image=image, is_primary=True)

        serializer = ProductDetailSerializer(product, context={'request': request})
        return Response(serializer.data)


class AdminProductToggleView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        try:
            product = Product.objects.get(pk=pk)
            product.is_active = not product.is_active
            product.save()
            return Response({'is_active': product.is_active})
        except Product.DoesNotExist:
            return Response({'error': 'Not found'}, status=404)


class AdminOrderListView(generics.ListAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = OrderSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['order_number', 'full_name', 'email', 'phone', 'city']
    ordering_fields = ['created_at', 'total', 'status']
    ordering = ['-created_at']

    def get_queryset(self):
        qs = Order.objects.all().select_related('user').order_by('-created_at')

        status_param = self.request.query_params.get('status')
        if status_param:
            qs = qs.filter(status=status_param)

        search_param = self.request.query_params.get('search')
        if search_param:
            qs = qs.filter(
                Q(order_number__icontains=search_param) |
                Q(full_name__icontains=search_param) |
                Q(email__icontains=search_param) |
                Q(phone__icontains=search_param) |
                Q(city__icontains=search_param)
            )

        return qs


class AdminOrderDetailView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = OrderSerializer

    def get_queryset(self):
        return Order.objects.all().order_by('-created_at')  # ← fixed

    def update(self, request, *args, **kwargs):
        order = self.get_object()
        new_status = request.data.get('status')
        if new_status and new_status in dict(Order.STATUS_CHOICES):
            order.status = new_status
            order.save()
        serializer = OrderSerializer(order)
        return Response(serializer.data)


class AdminCustomerListView(generics.ListAPIView):
    permission_classes = [IsAdminUser]
    filter_backends = [filters.SearchFilter]
    search_fields = ['email', 'first_name', 'last_name', 'phone']

    def get_queryset(self):
        return CustomUser.objects.filter(is_staff=False).annotate(
            order_count=Count('orders')
        ).order_by('-date_joined')

    def list(self, request, *args, **kwargs):
        from users.serializers import UserSerializer
        queryset = self.filter_queryset(self.get_queryset())
        serializer = UserSerializer(queryset, many=True)
        data = serializer.data
        for i, customer in enumerate(queryset):
            data[i]['order_count'] = customer.order_count
        return Response(data)


class AdminCustomerDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        return CustomUser.objects.filter(is_staff=False)

    def retrieve(self, request, *args, **kwargs):
        from users.serializers import UserSerializer
        customer = self.get_object()
        data = UserSerializer(customer).data
        orders = Order.objects.filter(user=customer).order_by('-created_at')
        data['orders'] = OrderSerializer(orders, many=True).data
        data['order_count'] = orders.count()
        return Response(data)


class AdminReviewListView(generics.ListAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = ReviewSerializer

    def get_queryset(self):
        return Review.objects.all().select_related('user', 'product').order_by('-created_at')


class AdminReviewDeleteView(generics.DestroyAPIView):
    permission_classes = [IsAdminUser]
    queryset = Review.objects.all().order_by('-created_at')  # ← fixed