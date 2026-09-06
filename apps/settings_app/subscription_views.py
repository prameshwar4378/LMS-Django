from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions, status
from django.utils import timezone
from datetime import timedelta
import re
from .models import Property, SubscriptionPlan, PropertySubscription
from .tenant_views import get_active_property_for_request
from apps.rooms.models import Room

class CurrentSubscriptionView(APIView):
    """
    Returns the active subscription details for the authenticated user's hotel property.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        prop = get_active_property_for_request(request)

        if not prop and user.is_superuser:
            # Fallback for platform superuser
            prop = Property.objects.first()

        if not prop:
            return Response({
                'success': False,
                'message': 'No hotel property assigned to this account.'
            }, status=status.HTTP_404_NOT_FOUND)

        sub = prop.get_subscription()
        today = timezone.now().date()
        room_count = Room.objects.filter(property=prop).count()

        is_prop_suspended = prop.is_suspended() if hasattr(prop, 'is_suspended') else not prop.is_active

        if not sub:
            # No subscription found
            return Response({
                'success': True,
                'property_id': prop.id,
                'property_name': prop.name,
                'property_code': prop.code,
                'has_subscription': False,
                'plan_name': 'No Active Plan',
                'plan_code': 'NONE',
                'is_expired': True,
                'is_near_expiry': False,
                'is_paid': False,
                'is_suspended': is_prop_suspended,
                'is_active': not is_prop_suspended,
                'valid_from': None,
                'valid_until': None,
                'days_remaining': 0,
                'max_rooms_allowed': prop.total_rooms or 10,
                'current_room_count': room_count,
                'license_key_masked': None
            })

        is_expired = sub.is_expired()
        days_remaining = sub.days_remaining()
        is_near_expiry = sub.is_near_expiry(15)
        urgency_level = sub.urgency_level

        return Response({
            'success': True,
            'property_id': prop.id,
            'property_name': prop.name,
            'property_code': prop.code,
            'is_branch': bool(prop.parent_property_id),
            'master_property_name': prop.parent_property.name if prop.parent_property else prop.name,
            'master_property_code': prop.parent_property.code if prop.parent_property else prop.code,
            'is_inherited': bool(prop.parent_property_id and sub.lodge_id != prop.id),
            'is_suspended': is_prop_suspended,
            'is_active': not is_prop_suspended,
            'has_subscription': True,
            'plan_name': sub.plan.name if sub.plan else 'Custom Plan',
            'plan_code': sub.plan.code if sub.plan else 'CUSTOM',
            'billing_cycle': sub.billing_cycle,
            'valid_from': str(sub.valid_from),
            'valid_until': str(sub.valid_until),
            'days_remaining': days_remaining,
            'is_expired': is_expired,
            'is_near_expiry': is_near_expiry,
            'urgency_level': urgency_level,
            'is_paid': sub.is_paid,
            'max_rooms_allowed': sub.plan.max_rooms if sub.plan else prop.total_rooms,
            'current_room_count': room_count,
            'features': sub.plan.features if sub.plan else []
        })


class SubscriptionPlansListView(APIView):
    """
    Returns list of all available SaaS subscription tiers for upgrades or renewals.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        plans = SubscriptionPlan.objects.filter(is_active=True).order_by('max_rooms')
        data = []
        for p in plans:
            data.append({
                'id': p.id,
                'name': p.name,
                'code': p.code,
                'max_rooms': p.max_rooms,
                'price_monthly': float(p.price_monthly),
                'price_annually': float(p.price_annually),
                'features': p.features or [
                    f"Up to {p.max_rooms} Managed Rooms" if p.max_rooms < 999 else "Unlimited Rooms",
                    "Front Desk POS Cash Register & Shift Tills",
                    "Guest KYC & GRC Registration Cards",
                    "Instant 80mm Thermal Receipts & Invoicing",
                    "Daily Night Audit Closeout & Reports",
                    "Automatic WhatsApp & Email Shift Reports"
                ]
            })
        return Response({
            'success': True,
            'plans': data
        })


class ActivateLicenseKeyView(APIView):
    """
    Decommissioned: Subscriptions are managed directly via Developer Platform.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        return Response({
            'success': False,
            'message': 'License key activation has been decommissioned. Subscriptions are managed directly via the Developer Platform.'
        }, status=status.HTTP_400_BAD_REQUEST)
