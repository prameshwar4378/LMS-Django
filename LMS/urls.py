from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('apps.authentication.urls')),
    path('api/', include('apps.rooms.urls')),
    path('api/', include('apps.customers.urls')),
    path('api/', include('apps.bookings.urls')),
    path('api/', include('apps.stays.urls')),
    path('api/', include('apps.billing.urls')),
    path('api/', include('apps.settings_app.urls')),
    path('api/', include('apps.reports.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
