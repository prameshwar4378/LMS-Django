from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CustomerViewSet, CustomerDocumentViewSet

router = DefaultRouter()
router.register(r'customers', CustomerViewSet, basename='customers')
router.register(r'customer-documents', CustomerDocumentViewSet, basename='customer-documents')

urlpatterns = [
    path('', include(router.urls)),
]
