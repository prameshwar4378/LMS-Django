from django.http import JsonResponse
from django.utils import timezone
from rest_framework_simplejwt.authentication import JWTAuthentication

class TenantSubscriptionMiddleware:
    """
    Middleware that enforces active SaaS subscriptions and property validity across all API endpoints.
    - If a property is deactivated by the platform owner -> Returns 403 PROPERTY_SUSPENDED.
    - If a property subscription is expired -> Allows read-only access (GET) while blocking
      data mutations (POST/PUT/PATCH/DELETE) with 402 SUBSCRIPTION_EXPIRED.
    """
    def __init__(self, get_response):
        self.get_response = get_response
        self.jwt_auth = JWTAuthentication()

    def __call__(self, request):
        # 1. Resolve user via JWT Bearer token if not already authenticated by session
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            auth_header = request.META.get('HTTP_AUTHORIZATION', '')
            if auth_header.startswith('Bearer '):
                try:
                    auth_result = self.jwt_auth.authenticate(request)
                    if auth_result:
                        user = auth_result[0]
                        request.user = user
                except Exception:
                    pass

        # 2. Check tenant and subscription status for authenticated non-superusers
        if user and user.is_authenticated and not user.is_superuser:
            from .tenant_views import get_active_property_for_request
            prop = get_active_property_for_request(request) or getattr(user, 'property', None)
            if prop:
                request.current_property = prop

                # Exempt paths that must always remain accessible (auth, subscriptions, platform, schema)
                path = request.path
                exempt_prefixes = [
                    '/api/auth/',
                    '/api/subscription/',
                    '/api/platform/',
                    '/api/schema/'
                ]
                is_exempt = any(path.startswith(prefix) for prefix in exempt_prefixes)

                if not is_exempt:
                    # A. Check Property Status (Suspended)
                    if prop.is_suspended():
                        return JsonResponse({
                            'success': False,
                            'error': 'PROPERTY_SUSPENDED',
                            'message': f'Property "{prop.name}" (or its parent hotel) has been suspended by the platform administrator. Access to PMS operational features is blocked. Please contact support.',
                            'property_code': prop.code,
                            'property_name': prop.name,
                            'is_suspended': True
                        }, status=403)

                    # B. Check Subscription Expiry
                    sub = prop.get_subscription()
                    if prop.is_subscription_expired():
                        return JsonResponse({
                            'success': False,
                            'error': 'SUBSCRIPTION_EXPIRED',
                            'message': f'Your subscription for {prop.name} expired on {sub.valid_until if sub else "N/A"}. Please renew your plan or contact technical support to continue using LMS.',
                            'property_name': prop.name,
                            'property_code': prop.code,
                            'plan': sub.plan.name if (sub and sub.plan) else 'Expired Plan',
                            'plan_code': sub.plan.code if (sub and sub.plan) else 'EXPIRED',
                            'valid_until': str(sub.valid_until) if sub else None,
                            'days_remaining': 0,
                            'renewal_url': '/subscription'
                        }, status=402)

        return self.get_response(request)
