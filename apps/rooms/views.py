from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from django.db.models import Q, Sum
import datetime
from .models import RoomType, Room, RoomDeletionRequest
from .serializers import RoomTypeSerializer, RoomSerializer, RoomDeletionRequestSerializer
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

def get_room_activity_details(room, user):
    from apps.stays.models import Stay
    from apps.bookings.models import Booking
    from apps.billing.models import Payment

    is_owner = bool(user and (user.is_superuser or getattr(user, 'role', '') in ['HOTEL_OWNER', 'SUPER_ADMIN', 'SUPERUSER']))
    user_role = getattr(user, 'role', 'STAFF') if user else 'STAFF'

    # 1. Stays connected to this room
    all_stays = Stay.objects.filter(room=room).select_related('primary_customer')
    active_stays_qs = all_stays.filter(status__in=['CHECKED_IN', 'RESERVED']).order_by('-check_in_date')
    active_stays_count = active_stays_qs.count()
    past_stays_count = all_stays.filter(status='CHECKED_OUT').count()
    total_stays_count = all_stays.count()

    active_stays_list = []
    has_in_house = False
    for s in active_stays_qs[:5]:
        if s.status == 'CHECKED_IN':
            has_in_house = True
        active_stays_list.append({
            'id': s.id,
            'stay_number': s.stay_number,
            'customer_name': s.primary_customer.full_name if s.primary_customer else 'Guest',
            'customer_phone': s.primary_customer.mobile if s.primary_customer else '—',
            'check_in_date': str(s.check_in_date),
            'expected_checkout_date': str(s.expected_checkout_date),
            'status': s.status
        })

    # 2. Bookings connected to this room
    all_bookings = Booking.objects.filter(room=room).select_related('customer')
    upcoming_bookings_qs = all_bookings.filter(status__in=['CONFIRMED', 'PENDING']).order_by('check_in_date')
    upcoming_bookings_count = upcoming_bookings_qs.count()
    total_bookings_count = all_bookings.count()

    upcoming_bookings_list = []
    for b in upcoming_bookings_qs[:5]:
        checkout_val = getattr(b, 'expected_checkout_date', getattr(b, 'check_out_date', ''))
        upcoming_bookings_list.append({
            'id': b.id,
            'booking_number': b.booking_number,
            'customer_name': b.customer.full_name if b.customer else 'Guest',
            'customer_phone': b.customer.mobile if b.customer else '—',
            'check_in_date': str(b.check_in_date),
            'check_out_date': str(checkout_val),
            'expected_checkout_date': str(checkout_val),
            'status': b.status
        })

    # 3. Revenue / Payments
    payments = Payment.objects.filter(Q(stay__room=room) | Q(booking__room=room))
    rev_agg = payments.aggregate(total=Sum('amount'))
    total_revenue = float(rev_agg['total'] or 0)

    # 4. Check for existing pending deletion request
    pending_req = RoomDeletionRequest.objects.filter(room=room, status=RoomDeletionRequest.Status.PENDING).first()
    pending_req_data = None
    if pending_req:
        pending_req_data = {
            'id': pending_req.id,
            'requested_by': pending_req.requested_by.get_full_name() or pending_req.requested_by.username,
            'requested_by_role': getattr(pending_req.requested_by, 'role', 'STAFF'),
            'reason': pending_req.reason,
            'created_at': pending_req.created_at.isoformat()
        }

    block_reason = ""
    if has_in_house:
        block_reason = f"Room {room.room_number} currently has an in-house guest. Guests must be checked out or transferred before deleting the room."
    elif not is_owner:
        block_reason = "Owner authorization is required. As a manager/receptionist, please submit a deletion request."

    can_delete_directly = is_owner and not has_in_house

    return {
        'room_id': room.id,
        'room_number': room.room_number,
        'room_type_name': room.room_type.name if room.room_type else '',
        'floor': room.floor,
        'status': room.status,
        'has_in_house': has_in_house,
        'active_stays': active_stays_list,
        'active_stays_count': active_stays_count,
        'upcoming_bookings': upcoming_bookings_list,
        'upcoming_bookings_count': upcoming_bookings_count,
        'past_stays_count': past_stays_count,
        'total_stays_count': total_stays_count,
        'total_bookings_count': total_bookings_count,
        'total_revenue': total_revenue,
        'pending_deletion_request': pending_req_data,
        'user_role': user_role,
        'is_owner': is_owner,
        'can_delete_directly': can_delete_directly,
        'block_reason': block_reason
    }

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
        qs = super().get_queryset()
        active_prop = self.get_property_for_request()
        if active_prop and getattr(active_prop, 'parent_property', None):
            root_prop = active_prop.get_root_property()
            return RoomType.objects.filter(Q(property=active_prop) | Q(property=root_prop)).order_by('name')
        return qs

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
            branch_label = f"branch '{user_prop.name}'" if (user_prop and getattr(user_prop, 'parent_property', None)) else f"property '{user_prop.name}'" if user_prop else "this branch"
            raise ValidationError({
                'room_number': [f"Room '{room_num}' already exists in {branch_label}. Please choose a different room number."]
            })

    def perform_update(self, serializer):
        require_perm(self.request.user, 'rooms', 'can_edit_tariffs', "You do not have permission to modify room settings or tariffs.")
        super().perform_update(serializer)

    def perform_destroy(self, instance):
        user = self.request.user
        is_owner = bool(user and (user.is_superuser or getattr(user, 'role', '') in ['HOTEL_OWNER', 'SUPER_ADMIN', 'SUPERUSER']))
        
        # If user is manager or receptionist, block direct deletion
        if not is_owner:
            raise ValidationError({
                'detail': 'Only the Hotel Owner can delete rooms directly. Managers and Receptionists must submit a deletion request for owner approval.'
            })

        # Check for active in-house stays
        active_in_house = instance.stays.filter(status='CHECKED_IN').select_related('primary_customer').first()
        if active_in_house:
            cust_name = active_in_house.primary_customer.full_name if active_in_house.primary_customer else 'Guest'
            raise ValidationError({
                'detail': f"Cannot delete Room {instance.room_number} because guest '{cust_name}' is currently checked in (Stay #{active_in_house.stay_number}). Please check out or transfer the guest before deleting this room."
            })

        # Unlink any related deletion requests so audit record remains intact
        RoomDeletionRequest.objects.filter(room=instance).update(room=None)

        super().perform_destroy(instance)

    @action(detail=True, methods=['get'])
    def activity(self, request, pk=None):
        room = self.get_object()
        data = get_room_activity_details(room, request.user)
        return Response(data)

    @action(detail=True, methods=['post'])
    def request_deletion(self, request, pk=None):
        room = self.get_object()
        user = request.user

        # Check if already pending
        existing = RoomDeletionRequest.objects.filter(room=room, status=RoomDeletionRequest.Status.PENDING).first()
        if existing:
            return Response({
                'success': False,
                'message': f"A deletion request for Room {room.room_number} is already pending owner review."
            }, status=status.HTTP_400_BAD_REQUEST)

        reason = request.data.get('reason', '').strip()
        activity_data = get_room_activity_details(room, user)

        del_req = RoomDeletionRequest.objects.create(
            property=room.property,
            room=room,
            room_number=room.room_number,
            room_type_name=room.room_type.name if room.room_type else '',
            floor=room.floor,
            requested_by=user,
            reason=reason,
            activity_summary=activity_data,
            status=RoomDeletionRequest.Status.PENDING
        )

        return Response({
            'success': True,
            'message': f"Deletion request for Room {room.room_number} submitted to Owner for review.",
            'request': RoomDeletionRequestSerializer(del_req).data
        }, status=status.HTTP_201_CREATED)

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
        
        old_status = room.status
        room.status = new_status
        room._change_reason = f"Room {room.room_number} status updated from {old_status} to {new_status}."
        room.save()
        return Response({
            'success': True,
            'message': f'Room status updated to {new_status}.',
            'data': self.get_serializer(room).data
        })


class RoomDeletionRequestViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = RoomDeletionRequest.objects.all().order_by('-created_at')
    serializer_class = RoomDeletionRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter.upper())
        return qs

    @action(detail=False, methods=['get'])
    def pending(self, request):
        qs = self.get_queryset().filter(status=RoomDeletionRequest.Status.PENDING)
        serializer = self.get_serializer(qs, many=True)
        return Response({
            'pending_count': qs.count(),
            'results': serializer.data
        })

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        from django.utils import timezone
        user = request.user
        is_owner = bool(user and (user.is_superuser or getattr(user, 'role', '') in ['HOTEL_OWNER', 'SUPER_ADMIN', 'SUPERUSER']))
        if not is_owner:
            return Response({
                'success': False,
                'message': 'Only the Hotel Owner can approve room deletions.'
            }, status=status.HTTP_403_FORBIDDEN)

        del_req = self.get_object()
        if del_req.status != RoomDeletionRequest.Status.PENDING:
            return Response({
                'success': False,
                'message': f'This deletion request is already {del_req.status}.'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Check if room exists and has active stay
        if del_req.room:
            room = del_req.room
            active_in_house = room.stays.filter(status='CHECKED_IN').exists()
            if active_in_house:
                return Response({
                    'success': False,
                    'message': f"Cannot delete Room {room.room_number} because a guest is currently checked in. Check out guest first."
                }, status=status.HTTP_400_BAD_REQUEST)

            room_num = room.room_number
            # Unlink room from this and any other requests before deleting
            del_req.room = None
            del_req.save()
            RoomDeletionRequest.objects.filter(room=room).update(room=None)
            room.delete()
        else:
            room_num = del_req.room_number

        del_req.status = RoomDeletionRequest.Status.APPROVED
        del_req.reviewed_by = user
        del_req.reviewed_at = timezone.now()
        del_req.review_notes = request.data.get('notes', 'Approved & deleted by Hotel Owner')
        del_req.save()

        return Response({
            'success': True,
            'message': f"Room {room_num} deletion approved. Room has been permanently deleted from inventory."
        })

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        from django.utils import timezone
        user = request.user
        is_owner = bool(user and (user.is_superuser or getattr(user, 'role', '') in ['HOTEL_OWNER', 'SUPER_ADMIN', 'SUPERUSER']))
        if not is_owner:
            return Response({
                'success': False,
                'message': 'Only the Hotel Owner can reject room deletion requests.'
            }, status=status.HTTP_403_FORBIDDEN)

        del_req = self.get_object()
        if del_req.status != RoomDeletionRequest.Status.PENDING:
            return Response({
                'success': False,
                'message': f'This deletion request is already {del_req.status}.'
            }, status=status.HTTP_400_BAD_REQUEST)

        del_req.status = RoomDeletionRequest.Status.REJECTED
        del_req.reviewed_by = user
        del_req.reviewed_at = timezone.now()
        del_req.review_notes = request.data.get('notes', 'Rejected by Hotel Owner')
        del_req.save()

        return Response({
            'success': True,
            'message': f"Deletion request for Room {del_req.room_number} has been rejected."
        })


