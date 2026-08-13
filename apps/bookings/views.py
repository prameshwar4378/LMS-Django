from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
import datetime
import uuid
from .models import Booking
from .serializers import BookingSerializer
from .services import transition_booking_status
from apps.stays.models import Stay
from apps.billing.models import Payment
from apps.rooms.models import Room
from apps.rooms.services import check_room_availability
from apps.settings_app.models import Settings

class BookingViewSet(viewsets.ModelViewSet):
    queryset = Booking.objects.all().select_related('customer', 'room', 'room__room_type', 'created_by').order_by('-created_at')
    serializer_class = BookingSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
        status_param = self.request.query_params.get('status')
        search_param = self.request.query_params.get('search')
        date_param = self.request.query_params.get('date')

        if status_param:
            queryset = queryset.filter(status=status_param)
        
        if date_param:
            queryset = queryset.filter(check_in_date=date_param)

        if search_param:
            queryset = queryset.filter(
                Q(booking_number__icontains=search_param) |
                Q(customer__first_name__icontains=search_param) |
                Q(customer__last_name__icontains=search_param) |
                Q(customer__mobile__icontains=search_param) |
                Q(room__room_number__icontains=search_param)
            )
        return queryset

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response({
            'success': True,
            'message': 'Booking created successfully.',
            'data': serializer.data
        }, status=status.HTTP_201_CREATED, headers=headers)

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()

        # Rule #23: Prevent arbitrary editing of checked-in booking
        if instance.status == 'CHECKED_IN':
            return Response({
                'success': False,
                'message': 'Checked-in bookings cannot be modified directly. Please use the Stay Management workflow.',
                'errors': {'booking': ['Checked-in booking cannot be edited directly.']}
            }, status=status.HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response({
            'success': True,
            'message': 'Booking updated successfully.',
            'data': serializer.data
        })

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def cancel(self, request, pk=None):
        booking = self.get_object()
        ok, err = transition_booking_status(booking, 'CANCELLED')
        if not ok:
            return Response({'success': False, 'message': err, 'errors': {'status': [err]}}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'success': True,
            'message': f'Booking #{booking.booking_number} has been cancelled successfully.',
            'data': self.get_serializer(booking).data
        })

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def no_show(self, request, pk=None):
        """
        Mark Booking as NO_SHOW (Rules #19, #20, #21, #48).
        """
        booking = self.get_object()
        ok, err = transition_booking_status(booking, 'NO_SHOW')
        if not ok:
            return Response({'success': False, 'message': err, 'errors': {'status': [err]}}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'success': True,
            'message': f'Booking #{booking.booking_number} marked as No Show.',
            'data': self.get_serializer(booking).data
        })

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def check_in(self, request, pk=None):
        """
        Check-In workflow from Booking (Rules #38, #39, #40, #46, #47, #48).
        """
        booking = Booking.objects.select_for_update().get(pk=pk)

        # Rules #46, #47, #48: Check status state machine
        if booking.status == 'CHECKED_IN':
            return Response({'success': False, 'message': 'This booking has already been checked in.', 'errors': {'status': ['Already checked in.']}}, status=status.HTTP_400_BAD_REQUEST)
        if booking.status == 'CANCELLED':
            return Response({'success': False, 'message': 'Cancelled bookings cannot be checked in.', 'errors': {'status': ['Booking is cancelled.']}}, status=status.HTTP_400_BAD_REQUEST)
        if booking.status == 'NO_SHOW':
            return Response({'success': False, 'message': 'This booking has been marked as No Show.', 'errors': {'status': ['Booking is marked as No Show.']}}, status=status.HTTP_400_BAD_REQUEST)

        # Target Room Re-allocation check
        target_room = booking.room
        new_room_id = request.data.get('room') or request.data.get('room_id')
        if new_room_id and str(new_room_id) != str(booking.room_id):
            try:
                target_room = Room.objects.get(id=new_room_id)
                booking.room = target_room
            except Room.DoesNotExist:
                return Response({'success': False, 'message': 'Selected room does not exist.', 'errors': {'room': ['Invalid room ID.']}}, status=status.HTTP_404_NOT_FOUND)

        # Parse actual stay check-in / check-out dates without overwriting historical booking dates
        today = datetime.date.today()
        actual_check_in_date = today
        if request.data.get('check_in_date'):
            val = request.data['check_in_date']
            if isinstance(val, str):
                try:
                    actual_check_in_date = datetime.datetime.strptime(val, '%Y-%m-%d').date()
                except ValueError:
                    pass
            elif isinstance(val, datetime.date):
                actual_check_in_date = val

        actual_check_in_time = datetime.datetime.now().time()
        if request.data.get('check_in_time'):
            try:
                t_parts = [int(x) for x in str(request.data['check_in_time']).split(':')]
                actual_check_in_time = datetime.time(t_parts[0], t_parts[1])
            except Exception:
                pass

        actual_checkout_date = booking.expected_checkout_date
        if request.data.get('expected_checkout_date'):
            val = request.data['expected_checkout_date']
            if isinstance(val, str):
                try:
                    actual_checkout_date = datetime.datetime.strptime(val, '%Y-%m-%d').date()
                except ValueError:
                    pass
            elif isinstance(val, datetime.date):
                actual_checkout_date = val

        actual_checkout_time = booking.expected_checkout_time or datetime.time(11, 0)
        if request.data.get('expected_checkout_time'):
            try:
                t_parts = [int(x) for x in str(request.data['expected_checkout_time']).split(':')]
                actual_checkout_time = datetime.time(t_parts[0], t_parts[1])
            except Exception:
                pass

        # Build actual datetimes for Stay Availability Check
        in_dt = datetime.datetime.combine(actual_check_in_date, actual_check_in_time)
        out_dt = datetime.datetime.combine(actual_checkout_date, actual_checkout_time)
        if timezone.is_naive(in_dt):
            in_dt = timezone.make_aware(in_dt)
        if timezone.is_naive(out_dt):
            out_dt = timezone.make_aware(out_dt)

        if out_dt <= in_dt:
            return Response({
                'success': False,
                'message': 'Expected checkout date & time must be strictly later than actual check-in date & time.',
                'errors': {'expected_checkout_date': ['Must be after actual check-in datetime.']}
            }, status=status.HTTP_400_BAD_REQUEST)

        # Fresh Room Availability Check prior to Check-In
        is_avail, avail_err = check_room_availability(
            target_room,
            in_dt,
            out_dt,
            exclude_booking_id=booking.id,
            check_cleaning=True
        )
        if not is_avail:
            return Response({
                'success': False,
                'message': f'Room is no longer available for check-in: {avail_err}',
                'errors': {'room': [avail_err]}
            }, status=status.HTTP_400_BAD_REQUEST)

        # Generate Unique Stay Number
        settings_obj = Settings.get_settings()
        prefix = settings_obj.stay_prefix or "STAY-"
        today_str = datetime.date.today().strftime('%Y%m%d')
        stay_number = None
        for attempt in range(50):
            count = Stay.objects.filter(stay_number__startswith=f"{prefix}{today_str}").count() + 1 + attempt
            s_num = f"{prefix}{today_str}-{count:03d}"
            if not Stay.objects.filter(stay_number=s_num).exists():
                stay_number = s_num
                break
        if not stay_number:
            stay_number = f"{prefix}{today_str}-{uuid.uuid4().hex[:4].upper()}"

        # Create Stay record with actual stay dates while preserving booking dates
        stay = Stay.objects.create(
            stay_number=stay_number,
            booking=booking,
            room=target_room,
            primary_customer=booking.customer,
            check_in_date=actual_check_in_date,
            check_in_time=actual_check_in_time,
            expected_checkout_date=actual_checkout_date,
            expected_checkout_time=actual_checkout_time,
            adults=booking.adults,
            children=booking.children,
            room_rate=booking.room_rate,
            discount_type=booking.discount_type,
            discount_value=booking.discount_value,
            status=Stay.Status.CHECKED_IN,
            created_by=request.user
        )

        # Process advance payment if any
        if booking.advance_amount and booking.advance_amount > 0:
            pay_prefix = "PAY-"
            payment_number = None
            for attempt in range(50):
                pay_count = Payment.objects.filter(payment_number__startswith=f"{pay_prefix}{today_str}").count() + 1 + attempt
                p_num = f"{pay_prefix}{today_str}-{pay_count:03d}"
                if not Payment.objects.filter(payment_number=p_num).exists():
                    payment_number = p_num
                    break
            if not payment_number:
                payment_number = f"{pay_prefix}{today_str}-{uuid.uuid4().hex[:4].upper()}"

            Payment.objects.create(
                payment_number=payment_number,
                stay=stay,
                amount=booking.advance_amount,
                payment_method='CASH',
                transaction_reference='Advance Booking Payment',
                received_by=request.user,
                notes='Advance payment from booking'
            )

        # Transition Booking & Update Room Status
        booking.status = Booking.Status.CHECKED_IN
        booking.save()

        target_room.status = Room.Status.OCCUPIED
        target_room.save()

        return Response({
            'success': True,
            'message': f'Check-In for Booking #{booking.booking_number} completed successfully.',
            'data': {
                'stay_id': stay.id,
                'stay_number': stay.stay_number,
                'booking': self.get_serializer(booking).data
            }
        })
