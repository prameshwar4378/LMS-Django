from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
import datetime
import uuid
from .models import Stay, StayGuest
from .serializers import StaySerializer, StayGuestSerializer
from .services import calculate_stay_bill, validate_checkout
from apps.customers.models import Customer
from apps.rooms.models import Room
from apps.rooms.services import check_room_availability
from apps.bookings.models import Booking
from apps.bookings.services import validate_booking_payload
from apps.billing.models import Payment, Invoice
from apps.settings_app.models import Settings

class StayViewSet(viewsets.ModelViewSet):
    queryset = Stay.objects.all().select_related('room', 'room__room_type', 'primary_customer', 'booking', 'created_by').prefetch_related('guests', 'extra_charges', 'payments').order_by('-created_at')
    serializer_class = StaySerializer
    permission_classes = [permissions.IsAuthenticated]

    def update(self, request, *args, **kwargs):
        stay = self.get_object()
        is_admin = request.user and (request.user.is_superuser or getattr(request.user, 'role', None) in ['SUPER_ADMIN', 'MANAGER'])
        if stay.status in ['CHECKED_OUT', 'COMPLETED'] and not is_admin:
            return Response({
                'success': False,
                'message': 'Receptionist staff cannot edit checked out stays. Super Admin / Manager authorization required.',
                'errors': {'status': ['Stay is checked out and locked.']}
            }, status=status.HTTP_403_FORBIDDEN)
        return super().update(request, *args, **kwargs)

    def get_queryset(self):
        queryset = super().get_queryset()
        status_param = self.request.query_params.get('status')
        search_param = self.request.query_params.get('search')

        if status_param:
            queryset = queryset.filter(status=status_param)
        else:
            if self.request.query_params.get('current') == 'true':
                queryset = queryset.filter(status='CHECKED_IN')

        if search_param:
            queryset = queryset.filter(
                Q(stay_number__icontains=search_param) |
                Q(primary_customer__first_name__icontains=search_param) |
                Q(primary_customer__last_name__icontains=search_param) |
                Q(primary_customer__mobile__icontains=search_param) |
                Q(room__room_number__icontains=search_param)
            )
        return queryset

    @action(detail=False, methods=['post'])
    @transaction.atomic
    def walk_in(self, request):
        """
        Direct Walk-In Check-In Workflow (Rules #34, #35, #36, #37, #77).
        """
        data = request.data
        user = request.user

        # 1. Validate payload and room availability via services
        validated_attrs, errors = validate_booking_payload(
            data,
            user=user,
            is_walkin=True
        )
        if errors:
            return Response({'success': False, 'message': 'Walk-in check-in validation failed.', 'errors': errors}, status=status.HTTP_400_BAD_REQUEST)

        # 2. Handle Customer Profile (Select existing or create new with deduplication)
        customer_id = data.get('customer')
        if customer_id and str(customer_id).lower() not in ['null', 'undefined', 'none', '']:
            try:
                customer = Customer.objects.get(id=customer_id)
            except Customer.DoesNotExist:
                return Response({'success': False, 'message': 'Customer not found.', 'errors': {'customer': ['Invalid customer ID.']}}, status=status.HTTP_404_NOT_FOUND)
        else:
            first_name = data.get('first_name')
            mobile = data.get('mobile')
            if not first_name or not mobile:
                return Response({'success': False, 'message': 'First name and mobile number are required.', 'errors': {'first_name': ['Required.'], 'mobile': ['Required.']}}, status=status.HTTP_400_BAD_REQUEST)

            clean_mobile = str(mobile).strip()
            customer = Customer.objects.filter(mobile=clean_mobile).first()
            if not customer:
                cust_data = {
                    'first_name': first_name,
                    'middle_name': data.get('middle_name', '') or '',
                    'last_name': data.get('last_name', '') or '',
                    'mobile': clean_mobile,
                    'email': data.get('email', '') or '',
                    'id_type': data.get('id_type', 'Aadhaar') or 'Aadhaar',
                    'id_number': data.get('id_number', '') or '',
                    'address': data.get('address', '') or '',
                }
                if request.FILES.get('photo'):
                    cust_data['photo'] = request.FILES['photo']
                if request.FILES.get('id_document'):
                    cust_data['id_document'] = request.FILES['id_document']
                if request.FILES.get('id_document_back'):
                    cust_data['id_document_back'] = request.FILES['id_document_back']

                customer = Customer.objects.create(**cust_data)
            else:
                # Update existing customer details
                customer.first_name = first_name
                if data.get('last_name'):
                    customer.last_name = data.get('last_name')
                if data.get('email'):
                    customer.email = data.get('email')
                if data.get('address'):
                    customer.address = data.get('address')
                if data.get('id_type'):
                    customer.id_type = data.get('id_type')
                if data.get('id_number'):
                    customer.id_number = data.get('id_number')
                if request.FILES.get('photo'):
                    customer.photo = request.FILES['photo']
                if request.FILES.get('id_document'):
                    customer.id_document = request.FILES['id_document']
                if request.FILES.get('id_document_back'):
                    customer.id_document_back = request.FILES['id_document_back']
                customer.save()

        room = validated_attrs['room']
        dt_in = datetime.datetime.now()

        # 3. Generate Unique Stay Number
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

        stay = Stay.objects.create(
            stay_number=stay_number,
            room=room,
            primary_customer=customer,
            check_in_date=dt_in.date(),
            check_in_time=dt_in.time(),
            expected_checkout_date=validated_attrs['expected_checkout_date'],
            expected_checkout_time=validated_attrs['expected_checkout_time'],
            adults=validated_attrs['adults'],
            children=validated_attrs['children'],
            room_rate=validated_attrs['room_rate'],
            discount_type=validated_attrs['discount_type'],
            discount_value=validated_attrs['discount_value'],
            status=Stay.Status.CHECKED_IN,
            created_by=user
        )

        # 4. Initial Payment if provided
        advance_payment = data.get('advance_payment')
        if advance_payment and float(advance_payment) > 0:
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
                amount=advance_payment,
                payment_method=data.get('payment_method', 'CASH'),
                transaction_reference=data.get('transaction_reference', 'Walk-in Payment'),
                received_by=user,
                notes='Initial Walk-in Advance Payment'
            )

        # Update Room status to OCCUPIED
        room.status = Room.Status.OCCUPIED
        room.save()

        return Response({
            'success': True,
            'message': f'Walk-in check-in for Room {room.room_number} completed successfully.',
            'data': self.get_serializer(stay).data
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'])
    def bill(self, request, pk=None):
        stay = self.get_object()
        return Response({
            'success': True,
            'message': 'Bill details retrieved.',
            'data': calculate_stay_bill(stay)
        })

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def extend(self, request, pk=None):
        stay = self.get_object()
        new_checkout_str = request.data.get('new_checkout_date')
        if not new_checkout_str:
            return Response({'success': False, 'message': 'new_checkout_date is required.', 'errors': {'new_checkout_date': ['Required.']}}, status=status.HTTP_400_BAD_REQUEST)

        try:
            new_checkout = datetime.datetime.strptime(new_checkout_str, '%Y-%m-%d').date()
        except ValueError:
            return Response({'success': False, 'message': 'Invalid date format. Use YYYY-MM-DD.', 'errors': {'new_checkout_date': ['Invalid format.']}}, status=status.HTTP_400_BAD_REQUEST)

        if new_checkout <= stay.expected_checkout_date:
            return Response({'success': False, 'message': 'New checkout date must be after current expected checkout date.', 'errors': {'new_checkout_date': ['Must be after current checkout date.']}}, status=status.HTTP_400_BAD_REQUEST)

        new_checkout_dt = datetime.datetime.combine(new_checkout, stay.expected_checkout_time or datetime.time(11, 0))
        if timezone.is_naive(new_checkout_dt):
            new_checkout_dt = timezone.make_aware(new_checkout_dt)

        in_dt = stay.check_in_datetime
        if timezone.is_naive(in_dt):
            in_dt = timezone.make_aware(in_dt)

        # Check overlapping for extension range
        is_avail, avail_err = check_room_availability(
            stay.room,
            in_dt,
            new_checkout_dt,
            exclude_stay_id=stay.id,
            exclude_booking_id=stay.booking.id if stay.booking else None
        )
        if not is_avail:
            return Response({'success': False, 'message': f'Extension denied: {avail_err}', 'errors': {'room': [avail_err]}}, status=status.HTTP_400_BAD_REQUEST)

        stay.expected_checkout_date = new_checkout
        stay.save()

        return Response({
            'success': True,
            'message': 'Stay extended successfully.',
            'data': {
                'stay': self.get_serializer(stay).data,
                'bill': calculate_stay_bill(stay)
            }
        })

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def transfer_room(self, request, pk=None):
        """
        Controlled Room Change for active stay (Rule #70).
        """
        stay = Stay.objects.select_for_update().get(pk=pk)
        if stay.status != 'CHECKED_IN':
            return Response({'success': False, 'message': 'Only active checked-in stays can undergo room transfer.', 'errors': {'status': ['Stay is not active.']}}, status=status.HTTP_400_BAD_REQUEST)

        target_room_id = request.data.get('target_room')
        if not target_room_id:
            return Response({'success': False, 'message': 'target_room is required.', 'errors': {'target_room': ['Required.']}}, status=status.HTTP_400_BAD_REQUEST)

        try:
            new_room = Room.objects.get(pk=target_room_id)
        except Room.DoesNotExist:
            return Response({'success': False, 'message': 'Target room does not exist.', 'errors': {'target_room': ['Invalid room ID.']}}, status=status.HTTP_404_NOT_FOUND)

        now_tz = timezone.now()
        out_dt = stay.expected_checkout_datetime
        if timezone.is_naive(out_dt):
            out_dt = timezone.make_aware(out_dt)

        is_avail, avail_err = check_room_availability(new_room, now_tz, out_dt, check_cleaning=True)
        if not is_avail:
            return Response({'success': False, 'message': f'Room transfer denied: {avail_err}', 'errors': {'target_room': [avail_err]}}, status=status.HTTP_400_BAD_REQUEST)

        old_room = stay.room
        old_room.status = Room.Status.CLEANING
        old_room.save()

        stay.room = new_room
        stay.save()

        new_room.status = Room.Status.OCCUPIED
        new_room.save()

        return Response({
            'success': True,
            'message': f'Room transferred successfully from Room {old_room.room_number} to Room {new_room.room_number}.',
            'data': self.get_serializer(stay).data
        })

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def checkout(self, request, pk=None):
        """
        Checkout Workflow (Rules #49, #50, #51, #52, #53, #54, #55, #56, #58, #59, #60, #66, #79).
        """
        stay = Stay.objects.select_for_update().get(pk=pk)
        actual_checkout_dt = timezone.now()

        # 1. Validate Checkout Services
        is_valid, bill, err_msg = validate_checkout(stay, actual_checkout_dt)
        if not is_valid:
            return Response({'success': False, 'message': err_msg, 'errors': {'checkout': [err_msg]}}, status=status.HTTP_400_BAD_REQUEST)

        # 2. Allow updating discount at checkout
        if 'discount_type' in request.data:
            stay.discount_type = request.data['discount_type']
        if 'discount_value' in request.data:
            stay.discount_value = request.data['discount_value']
        if 'discount_reason' in request.data:
            stay.discount_reason = request.data['discount_reason']
        stay.save()

        # 3. Handle checkout payment if provided
        payment_amount = request.data.get('payment_amount')
        if payment_amount and float(payment_amount) > 0:
            today_str = datetime.date.today().strftime('%Y%m%d')
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
                amount=payment_amount,
                payment_method=request.data.get('payment_method', 'CASH'),
                transaction_reference=request.data.get('transaction_reference', 'Checkout Payment'),
                received_by=request.user,
                notes='Final checkout payment'
            )

        # Recalculate bill after payment
        final_bill = calculate_stay_bill(stay, actual_checkout_dt)

        # 4. Complete Stay Checkout
        now = datetime.datetime.now()
        stay.actual_checkout_date = now.date()
        stay.actual_checkout_time = now.time()
        stay.status = Stay.Status.CHECKED_OUT
        stay.save()

        # 5. Update Room Status (AVAILABLE / CLEANING / MAINTENANCE)
        room = stay.room
        room_next_status = request.data.get('room_status', Room.Status.CLEANING)
        room.status = room_next_status
        room.save()

        # 6. Mark linked booking as COMPLETED
        if stay.booking:
            stay.booking.status = Booking.Status.COMPLETED
            stay.booking.save()

        # 7. Generate Invoice (Rule #66)
        settings_obj = Settings.get_settings()
        inv_prefix = settings_obj.invoice_prefix or "INV-"
        inv_count = Invoice.objects.filter(invoice_number__startswith=f"{inv_prefix}{now.strftime('%Y%m%d')}").count() + 1
        inv_number = f"{inv_prefix}{now.strftime('%Y%m%d')}-{inv_count:03d}"

        invoice, _ = Invoice.objects.update_or_create(
            stay=stay,
            defaults={
                'invoice_number': inv_number,
                'subtotal': final_bill['gross_subtotal'],
                'discount': final_bill['discount_amount'],
                'tax': final_bill['gst_amount'],
                'grand_total': final_bill['grand_total'],
                'paid_amount': final_bill['total_paid'],
                'balance': final_bill['balance'],
            }
        )

        return Response({
            'success': True,
            'message': f'Checkout for Stay #{stay.stay_number} completed successfully.',
            'data': {
                'stay': self.get_serializer(stay).data,
                'invoice_id': invoice.id,
                'invoice_number': invoice.invoice_number,
                'bill': final_bill
            }
        })


class StayGuestViewSet(viewsets.ModelViewSet):
    queryset = StayGuest.objects.all().order_by('-created_at')
    serializer_class = StayGuestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
        stay_id = self.request.query_params.get('stay')
        if stay_id:
            queryset = queryset.filter(stay_id=stay_id)
        return queryset
