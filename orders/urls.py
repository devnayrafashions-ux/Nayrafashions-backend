from django.urls import path
from .views import CartView, OrderListCreateView, OrderDetailView

urlpatterns = [
    path('cart/', CartView.as_view(), name='cart'),
    path('orders/', OrderListCreateView.as_view(), name='orders'),
    path('orders/<int:pk>/', OrderDetailView.as_view(), name='order-detail'),
]