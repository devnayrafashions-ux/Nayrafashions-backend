from rest_framework import viewsets, generics, permissions, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from .models import Category, Product, Review, Wishlist
from .serializers import (
    CategorySerializer, ProductListSerializer,
    ProductDetailSerializer, ReviewSerializer
)


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.filter(is_active=True).order_by('name')
    serializer_class = CategorySerializer
    lookup_field = 'slug'
    # NEW: lets the frontend ask for only Jewelry (or Dress, or Hair
    # Accessory) categories, e.g. /api/categories/?product_type=jewelry
    # — used by the sidebar so it only lists sub-categories relevant to
    # whichever type-level page the customer is currently browsing.
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['product_type']


class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Product.objects.filter(is_active=True).prefetch_related(
        'images', 'variants', 'reviews', 'category'
    ).order_by('-created_at')
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    # NEW: category__product_type added alongside the existing
    # category__slug — one filters to a specific sub-category (e.g.
    # "necklaces"), the other filters to an entire product line (e.g.
    # every jewelry product regardless of sub-category).
    filterset_fields = ['category__slug', 'category__product_type', 'badge', 'is_featured']
    search_fields = ['name', 'description']
    ordering_fields = ['price', 'created_at']
    ordering = ['-created_at']
    lookup_field = 'slug'

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return ProductDetailSerializer
        return ProductListSerializer

    @action(detail=False, methods=['get'])
    def featured(self, request):
        featured = self.queryset.filter(is_featured=True)[:8]
        serializer = ProductListSerializer(
            featured, many=True, context={'request': request}
        )
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def new_arrivals(self, request):
        new = self.queryset.order_by('-created_at')[:8]
        serializer = ProductListSerializer(
            new, many=True, context={'request': request}
        )
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def jewelry_and_accessories(self, request):
        """Used by the homepage slider (step 6) — jewelry + hair accessory
        products combined, newest first, capped for a slider row."""
        items = self.queryset.filter(
            category__product_type__in=['jewelry', 'hair_accessory']
        )[:12]
        serializer = ProductListSerializer(
            items, many=True, context={'request': request}
        )
        return Response(serializer.data)


class ReviewCreateView(generics.CreateAPIView):
    serializer_class = ReviewSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        product_id = self.kwargs['product_id']
        serializer.save(user=self.request.user, product_id=product_id)


class WishlistView(generics.RetrieveAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ProductListSerializer

    def get(self, request):
        wishlist, _ = Wishlist.objects.get_or_create(user=request.user)
        products = wishlist.products.filter(is_active=True)
        serializer = ProductListSerializer(
            products, many=True, context={'request': request}
        )
        return Response(serializer.data)

    def post(self, request):
        product_id = request.data.get('product_id')
        wishlist, _ = Wishlist.objects.get_or_create(user=request.user)
        product = Product.objects.get(id=product_id)
        if wishlist.products.filter(id=product_id).exists():
            wishlist.products.remove(product)
            return Response({'status': 'removed'})
        wishlist.products.add(product)
        return Response({'status': 'added'})