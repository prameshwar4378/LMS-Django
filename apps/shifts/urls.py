from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ShiftViewSet, CashDrawerViewSet

router = DefaultRouter()
router.register(r'shifts/cash-drawers', CashDrawerViewSet, basename='shift-cash-drawer')
router.register(r'shifts', ShiftViewSet, basename='shift')
router.register(r'cash-drawers', CashDrawerViewSet, basename='cash-drawer')

urlpatterns = [
    path('', include(router.urls)),
]
