from django.urls import path
from . import admin_views

urlpatterns = [
    path('dashboard/', admin_views.AdminDashboardView.as_view(), name='admin-dashboard'),
    path('categories/', admin_views.AdminCategoryListCreateView.as_view(), name='admin-categories'),
    path('categories/<int:pk>/', admin_views.AdminCategoryDetailView.as_view(), name='admin-category-detail'),
    path('products/', admin_views.AdminProductListCreateView.as_view(), name='admin-products'),
    path('products/<int:pk>/', admin_views.AdminProductDetailView.as_view(), name='admin-product-detail'),
    path('products/<int:pk>/toggle_active/', admin_views.AdminProductToggleView.as_view(), name='admin-product-toggle'),
    path('orders/', admin_views.AdminOrderListView.as_view(), name='admin-orders'),
    path('orders/<int:pk>/', admin_views.AdminOrderDetailView.as_view(), name='admin-order-detail'),
    path('customers/', admin_views.AdminCustomerListView.as_view(), name='admin-customers'),
    path('customers/<int:pk>/', admin_views.AdminCustomerDetailView.as_view(), name='admin-customer-detail'),
    path('reviews/', admin_views.AdminReviewListView.as_view(), name='admin-reviews'),
    path('reviews/<int:pk>/', admin_views.AdminReviewDeleteView.as_view(), name='admin-review-delete'),
]