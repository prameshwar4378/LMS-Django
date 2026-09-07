from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import transaction, IntegrityError
from django.db.models import Q
from django.utils import timezone
from decimal import Decimal
import datetime
import uuid
from .models import Booking
from .serializers import BookingSerializer
from .services import transition_booking_status
from apps.stays.models import Stay
from apps.billing.models import Payment
from apps.billing.services import generate_unique_stay_number, generate_unique_payment_number
from apps.rooms.models import Room
from apps.rooms.services import check_room_availability
from apps.settings_app.models import Settings
from apps.settings_app.tenant_views import TenantScopedViewSetMixin

from apps.authentication.permissions import user_has_perm, require_perm, get_perm_limit

class BookingViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Booking.objects.all().select_related('customer', 'room', 'room__room_type', 'created_by').order_by('-created_at')
    serializer_class = BookingSerializer
    permission_classes = [permissions.IsAuthenticated]

    def _validate_booking_discount(self, user, data):
        disc_val = data.get('discount_value')
        if disc_val:
            try:
                disc_float = float(disc_val)
            except (ValueError, TypeError):
                disc_float = 0.0
            if disc_float > 0:
                require_perm(user, 'billing', 'can_give_discount', "You do not have permission to apply discounts.")
                max_pct = get_perm_limit(user, 'billing', 'max_discount_percent', fallback=10.0)
                disc_type = data.get('discount_type', 'PERCENT')
                if disc_type == 'PERCENT' and disc_float > max_pct:
                    from rest_framework.exceptions import ValidationError
                    raise ValidationError({'discount_value': [f"Discount of {disc_float}% exceeds your role's allowed maximum limit of {max_pct}%."]})

    def get_queryset(self):
        user = getattr(self.request, 'user', None)
        if user and not user_has_perm(user, 'bookings', 'can_view'):
            require_perm(user, 'bookings', 'can_view', "You do not have permission to view reservations.")

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
        require_perm(request.user, 'bookings', 'can_create', "You do not have permission to create reservations.")
        self._validate_booking_discount(request.user, request.data)
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
        require_perm(request.user, 'bookings', 'can_edit', "You do not have permission to modify reservations.")
        self._validate_booking_discount(request.user, request.data)
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

    def destroy(self, request, *args, **kwargs):
        require_perm(request.user, 'bookings', 'can_delete', "You do not have permission to permanently delete bookings. You may cancel the booking instead.")
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def cancel(self, request, pk=None):
        require_perm(request.user, 'bookings', 'can_cancel', "You do not have permission to cancel reservations.")
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
        require_perm(request.user, 'bookings', 'can_cancel', "You do not have permission to mark reservations as No Show.")
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
        require_perm(request.user, 'stays', 'can_checkin', "You do not have permission to check in guests.")
        booking = self.get_object()


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
            target_room = Room.objects.filter(property=booking.property, id=new_room_id).first() if booking.property else Room.objects.filter(id=new_room_id).first()
            if not target_room:
                return Response({'success': False, 'message': 'Selected room does not exist.', 'errors': {'room': ['Invalid room ID.']}}, status=status.HTTP_404_NOT_FOUND)
            booking.room = target_room

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

        # Validate and handle chargeable_nights override if provided
        chargeable_nights_in = request.data.get('chargeable_nights')
        chargeable_nights = None
        if chargeable_nights_in is not None and str(chargeable_nights_in).strip().isdigit():
            val_cn = int(str(chargeable_nights_in).strip())
            cal_nights = max(1, (actual_checkout_date - actual_check_in_date).days)
            min_allowed = max(1, cal_nights - 1)
            max_allowed = cal_nights + 1
            if not (min_allowed <= val_cn <= max_allowed):
                return Response({
                    'success': False,
                    'message': f"Considered nights ({val_cn}) must be between {min_allowed} and {max_allowed} for a {cal_nights}-night calendar stay.",
                    'errors': {'chargeable_nights': [f"Must be between {min_allowed} and {max_allowed}."]}
                }, status=status.HTTP_400_BAD_REQUEST)
            chargeable_nights = val_cn

        # Generate Unique Stay Number
        settings_obj = Settings.get_settings(prop=booking.property)
        prefix = settings_obj.stay_prefix or "STAY-"
        stay = None
        for _ in range(10):
            stay_number = generate_unique_stay_number(booking.property, prefix)
            try:
                with transaction.atomic():
                    stay = Stay.objects.create(
                        property=booking.property,
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
                        chargeable_nights=chargeable_nights,
                        notes=request.data.get('notes', booking.notes or '') or '',
                        status=Stay.Status.CHECKED_IN,
                        created_by=request.user
                    )
                break
            except IntegrityError:
                continue

        # Process advance payment if any
        if booking.advance_amount and booking.advance_amount > 0:
            from apps.shifts.services import get_active_shift_for_user
            user_shift = get_active_shift_for_user(request.user)

            for _ in range(10):
                payment_number = generate_unique_payment_number("PAY-")
                try:
                    with transaction.atomic():
                        Payment.objects.create(
                            property=booking.property,
                            payment_number=payment_number,
                            stay=stay,
                            amount=booking.advance_amount,
                            payment_method='CASH',
                            transaction_reference='Advance Booking Payment',
                            received_by=request.user,
                            shift=user_shift,
                            notes='Advance payment from booking'
                        )
                    break
                except IntegrityError:
                    continue

        # Automatic Customer Advance Credit Wallet Application
        customer = booking.customer
        if customer:
            from apps.billing.services import calculate_stay_bill
            stay_credits = 0.0
            overpaid_stays = []
            for s in Stay.objects.filter(primary_customer=customer).exclude(id=stay.id):
                bill_s = calculate_stay_bill(s)
                bal_s = float(bill_s.get('balance', 0))
                if bal_s < 0:
                    credit_amt = abs(bal_s)
                    overpaid_stays.append({'stay': s, 'credit': credit_amt})
                    stay_credits += credit_amt

            total_wallet_available = float(customer.advance_credit or 0) + stay_credits

            if total_wallet_available > 0:
                bill_stay = calculate_stay_bill(stay)
                due_amount = float(bill_stay.get('balance', 0))
                wallet_to_apply = min(total_wallet_available, due_amount if due_amount > 0 else total_wallet_available)

                if wallet_to_apply > 0:
                    for _ in range(10):
                        payment_number = generate_unique_payment_number("PAY-")
                        try:
                            with transaction.atomic():
                                Payment.objects.create(
                                    payment_number=payment_number,
                                    stay=stay,
                                    amount=wallet_to_apply,
                                    payment_method='OTHER',
                                    transaction_reference='CUSTOMER_ADVANCE_WALLET',
                                    received_by=request.user,
                                    notes=f'Automatically applied ₹{wallet_to_apply:.2f} from Customer Advance Credit Wallet'
                                )
                            break
                        except IntegrityError:
                            continue

                    remaining_to_deduct = wallet_to_apply
                    adv_credit_float = float(customer.advance_credit or 0)
                    if adv_credit_float > 0:
                        deduct_adv = min(adv_credit_float, remaining_to_deduct)
                        customer.advance_credit -= Decimal(str(deduct_adv))
                        customer.save()
                        remaining_to_deduct -= deduct_adv

                    if remaining_to_deduct > 0:
                        for item in overpaid_stays:
                            if remaining_to_deduct <= 0:
                                break
                            st = item['stay']
                            st_credit = item['credit']
                            draw_amt = min(st_credit, remaining_to_deduct)

                            for _ in range(10):
                                p_num_transfer = generate_unique_payment_number("PAY-")
                                try:
                                    with transaction.atomic():
                                        Payment.objects.create(
                                            payment_number=p_num_transfer,
                                            stay=st,
                                            amount=-Decimal(str(draw_amt)),
                                            payment_method='OTHER',
                                            transaction_reference='WALLET_TRANSFER_OUT',
                                            received_by=request.user,
                                            notes=f'Wallet credit transfer of ₹{draw_amt:.2f} to Stay #{stay.stay_number}'
                                        )
                                    break
                                except IntegrityError:
                                    continue
                            remaining_to_deduct -= draw_amt

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
