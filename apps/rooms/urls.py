from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import RoomTypeViewSet, RoomViewSet

router = DefaultRouter()
router.register(r'room-types', RoomTypeViewSet, basename='room-types')
router.register(r'rooms', RoomViewSet, basename='rooms')

urlpatterns = [
    path('', include(router.urls)),
]
