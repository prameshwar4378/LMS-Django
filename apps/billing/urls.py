from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ChargeTypeViewSet, ExtraChargeViewSet, PaymentViewSet, InvoiceViewSet

router = DefaultRouter()
router.register(r'charge-types', ChargeTypeViewSet, basename='charge-types')
router.register(r'extra-charges', ExtraChargeViewSet, basename='extra-charges')
router.register(r'payments', PaymentViewSet, basename='payments')
router.register(r'invoices', InvoiceViewSet, basename='invoices')

urlpatterns = [
    path('', include(router.urls)),
]
