from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q
import datetime
from .models import RoomType, Room
from .serializers import RoomTypeSerializer, RoomSerializer
from .services import check_room_availability

def parse_datetime(val_str, default_time_str='12:00'):
    """
    Parses a string into a timezone-naive or aware datetime object safely.
    Accepts ISO strings, YYYY-MM-DD HH:MM:SS, YYYY-MM-DD HH:MM, or YYYY-MM-DD.
    """
    if not val_str:
        return None
    
    clean_str = str(val_str).strip().replace('T', ' ')
    parts = clean_str.split(' ')
    date_part = parts[0]
    time_part = parts[1] if len(parts) > 1 and parts[1] else default_time_str

    try:
        d = datetime.datetime.strptime(date_part, '%Y-%m-%d').date()
    except Exception:
        return None

    t_parts = str(time_part).split(':')
    try:
        h = int(t_parts[0]) if len(t_parts) > 0 and t_parts[0].isdigit() else 12
        m = int(t_parts[1]) if len(t_parts) > 1 and t_parts[1].isdigit() else 0
        s = int(t_parts[2]) if len(t_parts) > 2 and t_parts[2].isdigit() else 0
        return datetime.datetime.combine(d, datetime.time(h, m, s))
    except Exception:
        return datetime.datetime.combine(d, datetime.time(12, 0))

from apps.settings_app.tenant_views import TenantScopedViewSetMixin

from apps.authentication.permissions import user_has_perm, require_perm

class RoomTypeViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = RoomType.objects.all().order_by('name')
    serializer_class = RoomTypeSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = getattr(self.request, 'user', None)
        if user and not user_has_perm(user, 'rooms', 'can_view'):
            require_perm(user, 'rooms', 'can_view', "You do not have permission to view room categories.")
        return super().get_queryset()

    def perform_create(self, serializer):
        require_perm(self.request.user, 'rooms', 'can_create', "You do not have permission to add room categories.")
        super().perform_create(serializer)

    def perform_update(self, serializer):
        require_perm(self.request.user, 'rooms', 'can_edit_tariffs', "You do not have permission to edit room categories or tariffs.")
        super().perform_update(serializer)

    def perform_destroy(self, instance):
        require_perm(self.request.user, 'rooms', 'can_create', "You do not have permission to delete room categories.")
        super().perform_destroy(instance)

class RoomViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Room.objects.all().select_related('room_type').order_by('room_number')
    serializer_class = RoomSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = getattr(self.request, 'user', None)
        if user and not user_has_perm(user, 'rooms', 'can_view'):
            require_perm(user, 'rooms', 'can_view', "You do not have permission to view the room inventory.")
        return super().get_queryset()

    def perform_create(self, serializer):
        from django.db import IntegrityError
        from rest_framework.exceptions import ValidationError

        user = self.request.user
        # 1. Role matrix permission validation
        require_perm(user, 'rooms', 'can_create', "You do not have permission to create new rooms.")

        # 2. Subscription Plan Room Quota Validation
        user_prop = self.get_property_for_request()
        if user_prop and not (user and user.is_superuser):
            current_rooms = Room.objects.filter(property=user_prop).count()
            max_allowed = user_prop.get_max_rooms_allowed()
            if current_rooms >= max_allowed:
                sub = user_prop.get_subscription()
                plan_name = sub.plan.name if (sub and sub.plan) else "Current Subscription Plan"
                raise ValidationError({
                    'detail': f"Room limit reached! Your hotel is on the {plan_name} tier, which permits a maximum of {max_allowed} rooms. Currently, you have {current_rooms} rooms created. Please upgrade your subscription plan or contact technical support to add more rooms.",
                    'max_rooms': max_allowed,
                    'current_rooms': current_rooms
                })

        try:
            super().perform_create(serializer)
        except IntegrityError:
            room_num = serializer.validated_data.get('room_number', '')
            raise ValidationError({
                'room_number': [f"Room '{room_num}' already exists in this property. Please choose a different room number."]
            })

    def perform_update(self, serializer):
        require_perm(self.request.user, 'rooms', 'can_edit_tariffs', "You do not have permission to modify room settings or tariffs.")
        super().perform_update(serializer)

    def perform_destroy(self, instance):
        require_perm(self.request.user, 'rooms', 'can_create', "You do not have permission to delete rooms.")
        super().perform_destroy(instance)



    @action(detail=False, methods=['get'])
    def availability(self, request):
        check_in_str = request.query_params.get('check_in')
        check_out_str = request.query_params.get('check_out')
        check_in_time_str = request.query_params.get('check_in_time', '12:00')
        check_out_time_str = request.query_params.get('check_out_time', '11:00')
        room_type_id = request.query_params.get('room_type')
        exclude_booking_id = request.query_params.get('exclude_booking_id')
        exclude_stay_id = request.query_params.get('exclude_stay_id')

        if not check_in_str or not check_out_str:
            return Response({'success': False, 'message': 'check_in and check_out dates/datetimes are required.', 'errors': {'check_in': ['Required.']}}, status=status.HTTP_400_BAD_REQUEST)

        target_checkin = parse_datetime(check_in_str, check_in_time_str)
        target_checkout = parse_datetime(check_out_str, check_out_time_str)

        if not target_checkin or not target_checkout:
            return Response({'success': False, 'message': 'Invalid datetime format.', 'errors': {'check_in': ['Invalid format.']}}, status=status.HTTP_400_BAD_REQUEST)

        if target_checkout <= target_checkin:
            return Response({'success': False, 'message': 'Check-out date and time must be later than check-in date and time.', 'errors': {'check_out': ['Must be after check-in.']}}, status=status.HTTP_400_BAD_REQUEST)

        all_rooms = self.get_queryset().select_related('room_type')
        if room_type_id:
            all_rooms = all_rooms.filter(room_type_id=room_type_id)

        try:
            ex_b_id = int(exclude_booking_id) if exclude_booking_id else None
        except (ValueError, TypeError):
            ex_b_id = None

        try:
            ex_s_id = int(exclude_stay_id) if exclude_stay_id else None
        except (ValueError, TypeError):
            ex_s_id = None

        available_rooms = []
        for r in all_rooms:
            is_avail, _ = check_room_availability(
                r,
                target_checkin,
                target_checkout,
                exclude_booking_id=ex_b_id,
                exclude_stay_id=ex_s_id
            )
            if is_avail:
                available_rooms.append(r)

        serializer = self.get_serializer(available_rooms, many=True)
        return Response({
            'success': True,
            'message': 'Available rooms retrieved.',
            'check_in': target_checkin.strftime('%Y-%m-%d %H:%M'),
            'check_out': target_checkout.strftime('%Y-%m-%d %H:%M'),
            'available_count': len(available_rooms),
            'rooms': serializer.data
        })

    @action(detail=True, methods=['post'])
    def update_status(self, request, pk=None):
        require_perm(request.user, 'rooms', 'can_change_status', "You do not have permission to change room housekeeping status.")
        room = self.get_object()
        new_status = request.data.get('status')
        if new_status not in Room.Status.values:
            return Response({'success': False, 'message': f'Invalid status. Allowed: {Room.Status.values}', 'errors': {'status': ['Invalid.']}}, status=status.HTTP_400_BAD_REQUEST)
        
        room.status = new_status
        room.save()
        return Response({
            'success': True,
            'message': f'Room status updated to {new_status}.',
            'data': self.get_serializer(room).data
        })

