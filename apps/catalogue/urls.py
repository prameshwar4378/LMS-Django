from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    PublicCatalogueView,
    PublicInquiryCreateView,
    HotelCatalogueConfigViewSet,
    RoomTypePhotoViewSet,
    CatalogueInquiryViewSet,
    HotelGalleryPhotoViewSet
)

router = DefaultRouter()
router.register(r'catalogue/config', HotelCatalogueConfigViewSet, basename='catalogue-config')
router.register(r'catalogue/gallery-photos', HotelGalleryPhotoViewSet, basename='catalogue-gallery-photos')
router.register(r'catalogue/photos', RoomTypePhotoViewSet, basename='catalogue-photos')
router.register(r'catalogue/inquiries', CatalogueInquiryViewSet, basename='catalogue-inquiries')

urlpatterns = [
    # Public endpoints for guests
    path('catalogue/public/<str:property_code>/', PublicCatalogueView.as_view(), name='catalogue-public'),
    path('catalogue/public/<str:property_code>/inquire/', PublicInquiryCreateView.as_view(), name='catalogue-public-inquire'),

    # Authenticated management endpoints
    path('', include(router.urls)),
]
