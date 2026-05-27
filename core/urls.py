from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('users.urls')),
    path('api/', include('store.urls')),
    path('api/', include('orders.urls')),
    path('api/payments/', include('payments.urls')),
    path('api/admin/', include('store.admin_urls')),  # ← ADD THIS
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)