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
    queryset = Category.objects.filter(is_active=True)
    serializer_class = CategorySerializer
    lookup_field = 'slug'


class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Product.objects.filter(is_active=True).prefetch_related(
        'images', 'variants', 'reviews', 'category'
    )
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['category__slug', 'badge', 'is_featured']
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
        new = self.queryset.filter(badge='new').order_by('-created_at')[:8]
        serializer = ProductListSerializer(
            new, many=True, context={'request': request}
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