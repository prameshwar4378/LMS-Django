from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import SettingsViewSet
from .platform_views import PlatformPropertyViewSet, PlatformSubscriptionViewSet, PlatformHealthView
from .subscription_views import CurrentSubscriptionView, SubscriptionPlansListView, ActivateLicenseKeyView

router = DefaultRouter()
router.register(r'settings', SettingsViewSet, basename='settings')
router.register(r'platform/properties', PlatformPropertyViewSet, basename='platform-properties')
router.register(r'platform/subscriptions', PlatformSubscriptionViewSet, basename='platform-subscriptions')

urlpatterns = [
    path('platform/health/', PlatformHealthView.as_view(), name='platform-health'),
    path('subscription/current/', CurrentSubscriptionView.as_view(), name='subscription-current'),
    path('subscription/plans/', SubscriptionPlansListView.as_view(), name='subscription-plans'),
    path('subscription/activate-license/', ActivateLicenseKeyView.as_view(), name='subscription-activate-license'),
    path('', include(router.urls)),
]

