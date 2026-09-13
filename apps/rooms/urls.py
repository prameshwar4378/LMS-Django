from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import RoomTypeViewSet, RoomViewSet, RoomDeletionRequestViewSet

router = DefaultRouter()
router.register(r'room-types', RoomTypeViewSet, basename='room-types')
router.register(r'rooms', RoomViewSet, basename='rooms')
router.register(r'room-deletion-requests', RoomDeletionRequestViewSet, basename='room-deletion-requests')

urlpatterns = [
    path('', include(router.urls)),
]

