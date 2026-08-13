from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import StayViewSet, StayGuestViewSet

router = DefaultRouter()
router.register(r'stays', StayViewSet, basename='stays')
router.register(r'stay-guests', StayGuestViewSet, basename='stay-guests')

urlpatterns = [
    path('', include(router.urls)),
]
