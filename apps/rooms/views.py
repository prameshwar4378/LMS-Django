from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q
import datetime
from .models import RoomType, Room
from .serializers import RoomTypeSerializer, RoomSerializer
from .services import check_room_availability

def parse_datetime(val_str, default_time_str):
    """
    Parses a string into a datetime object.
    Accepts ISO format or YYYY-MM-DD format (combining default time).
    """
    if not val_str:
        return None
    
    val_str = val_str.replace('T', ' ')
    
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            dt = datetime.datetime.strptime(val_str, fmt)
            if fmt == '%Y-%m-%d':
                time_parts = [int(p) for p in default_time_str.split(':')]
                dt = datetime.datetime.combine(dt.date(), datetime.time(time_parts[0], time_parts[1]))
            return dt
        except ValueError:
            pass
    return None

class RoomTypeViewSet(viewsets.ModelViewSet):
    queryset = RoomType.objects.all().order_by('name')
    serializer_class = RoomTypeSerializer
    permission_classes = [permissions.IsAuthenticated]

class RoomViewSet(viewsets.ModelViewSet):
    queryset = Room.objects.all().select_related('room_type').order_by('room_number')
    serializer_class = RoomSerializer
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=['get'])
    def availability(self, request):
        check_in_str = request.query_params.get('check_in')
        check_out_str = request.query_params.get('check_out')
        check_in_time_str = request.query_params.get('check_in_time', '12:00')
        check_out_time_str = request.query_params.get('check_out_time', '11:00')
        room_type_id = request.query_params.get('room_type')

        if not check_in_str or not check_out_str:
            return Response({'success': False, 'message': 'check_in and check_out dates/datetimes are required.', 'errors': {'check_in': ['Required.']}}, status=status.HTTP_400_BAD_REQUEST)

        target_checkin = parse_datetime(check_in_str, check_in_time_str)
        target_checkout = parse_datetime(check_out_str, check_out_time_str)

        if not target_checkin or not target_checkout:
            return Response({'success': False, 'message': 'Invalid datetime format.', 'errors': {'check_in': ['Invalid format.']}}, status=status.HTTP_400_BAD_REQUEST)

        if target_checkout <= target_checkin:
            return Response({'success': False, 'message': 'Check-out date and time must be later than check-in date and time.', 'errors': {'check_out': ['Must be after check-in.']}}, status=status.HTTP_400_BAD_REQUEST)

        all_rooms = Room.objects.all().select_related('room_type')
        if room_type_id:
            all_rooms = all_rooms.filter(room_type_id=room_type_id)

        available_rooms = []
        for r in all_rooms:
            is_avail, _ = check_room_availability(r, target_checkin, target_checkout)
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
