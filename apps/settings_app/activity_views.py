from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from .tenant_views import get_active_property_for_request
from .activity_service import get_activity_logs, cleanup_old_history

class ActivityLogView(APIView):
    """
    API endpoint for retrieving system activity audit logs.
    Strictly restricted to Hotel Owners and Managers only.
    Automatically prunes historical records older than 15 days.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        
        # Strictly verify user role (Manager or Owner only)
        is_manager_or_owner = bool(
            user.is_superuser
            or getattr(user, 'role', '') in ['HOTEL_OWNER', 'MANAGER', 'SUPER_ADMIN', 'SUPERUSER']
            or (hasattr(user, 'is_hotel_owner') and user.is_hotel_owner())
        )

        if not is_manager_or_owner:
            return Response(
                {'detail': 'Access denied: System activity logs are restricted to Managers and Hotel Owners only.'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Multi-tenant property resolution
        active_prop = get_active_property_for_request(request)

        # Parse query params
        try:
            page = max(1, int(request.query_params.get('page', 1)))
        except (ValueError, TypeError):
            page = 1

        try:
            page_size = min(1000, max(5, int(request.query_params.get('page_size', 20))))
        except (ValueError, TypeError):
            page_size = 20

        model_filter = request.query_params.get('model', 'ALL').strip()
        action_filter = request.query_params.get('action', 'ALL').strip()
        search_query = request.query_params.get('search', '').strip()

        # Days retention (capped to maximum 15 days as requested)
        try:
            days = min(15, max(1, int(request.query_params.get('days', 15))))
        except (ValueError, TypeError):
            days = 15

        logs_data = get_activity_logs(
            prop=active_prop,
            page=page,
            page_size=page_size,
            model_filter=model_filter,
            action_filter=action_filter,
            search_query=search_query,
            days=days,
        )

        return Response(logs_data, status=status.HTTP_200_OK)


class ActivityLogCleanupView(APIView):
    """
    Manual trigger endpoint to run the 15-day activity cleanup.
    Available to Hotel Owners and Superusers.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        is_owner = bool(
            user.is_superuser
            or getattr(user, 'role', '') in ['HOTEL_OWNER', 'SUPER_ADMIN', 'SUPERUSER']
            or (hasattr(user, 'is_hotel_owner') and user.is_hotel_owner())
        )
        if not is_owner:
            return Response(
                {'detail': 'Only the Hotel Owner or Superuser can trigger manual log cleanup.'},
                status=status.HTTP_403_FORBIDDEN
            )

        days = int(request.data.get('days', 15))
        result = cleanup_old_history(days=days)
        return Response({
            'success': True,
            'message': f"Cleaned up {result['total_deleted']} records older than {days} days.",
            'details': result,
        })
