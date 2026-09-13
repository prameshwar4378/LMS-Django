from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import SettingsViewSet
from .platform_views import (
    PlatformPropertyViewSet,
    PlatformSubscriptionViewSet,
    PlatformHealthView,
    PlatformInquiryViewSet
)
from .subscription_views import CurrentSubscriptionView, SubscriptionPlansListView, ActivateLicenseKeyView
from .activity_views import ActivityLogView, ActivityLogCleanupView

router = DefaultRouter()
router.register(r'settings', SettingsViewSet, basename='settings')
router.register(r'platform/properties', PlatformPropertyViewSet, basename='platform-properties')
router.register(r'platform/subscriptions', PlatformSubscriptionViewSet, basename='platform-subscriptions')
router.register(r'platform/inquiries', PlatformInquiryViewSet, basename='platform-inquiries')

urlpatterns = [
    path('platform/health/', PlatformHealthView.as_view(), name='platform-health'),
    path('subscription/current/', CurrentSubscriptionView.as_view(), name='subscription-current'),
    path('subscription/plans/', SubscriptionPlansListView.as_view(), name='subscription-plans'),
    path('subscription/activate-license/', ActivateLicenseKeyView.as_view(), name='subscription-activate-license'),
    path('activity-logs/', ActivityLogView.as_view(), name='activity-logs'),
    path('activity-logs/cleanup/', ActivityLogCleanupView.as_view(), name='activity-logs-cleanup'),
    path('', include(router.urls)),
]

