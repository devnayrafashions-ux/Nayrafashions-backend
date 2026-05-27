from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CategoryViewSet, ProductViewSet, ReviewCreateView, WishlistView

router = DefaultRouter()
router.register(r'categories', CategoryViewSet)
router.register(r'products', ProductViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('products/<int:product_id>/reviews/', ReviewCreateView.as_view()),
    path('wishlist/', WishlistView.as_view()),
]