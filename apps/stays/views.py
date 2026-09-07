from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import transaction, IntegrityError
from django.db.models import Q
from django.utils import timezone
from decimal import Decimal
import datetime
import uuid
from .models import Stay, StayGuest
from .serializers import StaySerializer, StayGuestSerializer
from .services import calculate_stay_bill, validate_checkout
from apps.billing.services import generate_unique_invoice_number, generate_unique_payment_number, generate_unique_stay_number
from apps.customers.models import Customer
from apps.rooms.models import Room
from apps.rooms.services import check_room_availability
from apps.bookings.models import Booking
from apps.bookings.services import validate_booking_payload
from apps.billing.models import Payment, Invoice
from apps.settings_app.models import Settings
from apps.settings_app.tenant_views import TenantScopedViewSetMixin
from apps.authentication.permissions import user_has_perm, require_perm, get_perm_limit

class StayViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):

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
        require_perm(request.user, 'stays', 'can_checkin', "You do not have permission to process walk-in check-ins.")
        data = request.data
        user = request.user

        # Validate discount permissions & limits
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
                    return Response({'success': False, 'message': f"Discount of {disc_float}% exceeds your allowed limit of {max_pct}%."}, status=status.HTTP_400_BAD_REQUEST)

        # 1. Validate payload and room availability via services
        validated_attrs, errors = validate_booking_payload(
            data,
            user=user,
            is_walkin=True
        )
        if errors:
            return Response({'success': False, 'message': 'Walk-in check-in validation failed.', 'errors': errors}, status=status.HTTP_400_BAD_REQUEST)


        # 2. Handle Customer Profile (Select existing or create new with deduplication)
        user_prop = getattr(user, 'property', None) if user and not user.is_superuser else None
        customer_id = data.get('customer')
        if customer_id and str(customer_id).lower() not in ['null', 'undefined', 'none', '']:
            try:
                customer = Customer.objects.get(property=user_prop, id=customer_id) if user_prop else Customer.objects.get(id=customer_id)
                if data.get('first_name'): customer.first_name = data.get('first_name')
                if data.get('last_name'): customer.last_name = data.get('last_name')
                if data.get('email'): customer.email = data.get('email')
                if data.get('address'): customer.address = data.get('address')
                if data.get('id_type'): customer.id_type = data.get('id_type')
                if data.get('id_number'): customer.id_number = data.get('id_number')
                if request.FILES.get('photo'): customer.photo = request.FILES['photo']
                if request.FILES.get('id_document'): customer.id_document = request.FILES['id_document']
                if request.FILES.get('id_document_back'): customer.id_document_back = request.FILES['id_document_back']
                customer.save()
            except Customer.DoesNotExist:
                return Response({'success': False, 'message': 'Customer not found in this hotel property.', 'errors': {'customer': ['Invalid customer ID.']}}, status=status.HTTP_404_NOT_FOUND)
        else:
            first_name = data.get('first_name')
            mobile = data.get('mobile')
            if not first_name or not mobile:
                return Response({'success': False, 'message': 'First name and mobile number are required.', 'errors': {'first_name': ['Required.'], 'mobile': ['Required.']}}, status=status.HTTP_400_BAD_REQUEST)

            clean_mobile = str(mobile).strip()
            cust_filter = {'mobile': clean_mobile}
            if user_prop:
                cust_filter['property'] = user_prop
            customer = Customer.objects.filter(**cust_filter).first()
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
                if user_prop:
                    cust_data['property'] = user_prop
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
        now = datetime.datetime.now()
        in_date = validated_attrs.get('check_in_date') or now.date()
        in_time = validated_attrs.get('check_in_time') or now.time()
        dt_in = datetime.datetime.combine(in_date, in_time)

        # 3. Generate Unique Stay Number
        settings_obj = Settings.get_settings(prop=user_prop)
        prefix = settings_obj.stay_prefix or "STAY-"
        stay = None
        for _ in range(10):
            stay_number = generate_unique_stay_number(user_prop, prefix)
            try:
                with transaction.atomic():
                    stay = Stay.objects.create(
                        property=user_prop,
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
                        chargeable_nights=validated_attrs.get('chargeable_nights'),
                        notes=data.get('notes', '') or '',
                        status=Stay.Status.CHECKED_IN,
                        created_by=user
                    )
                break
            except IntegrityError:
                continue

        # 4. Initial Payment if provided
        advance_payment = data.get('advance_payment')
        if advance_payment and float(advance_payment) > 0:
            from apps.shifts.services import get_active_shift_for_user
            user_shift = get_active_shift_for_user(user)

            for _ in range(10):
                payment_number = generate_unique_payment_number("PAY-")
                try:
                    with transaction.atomic():
                        Payment.objects.create(
                            property=user_prop,
                            payment_number=payment_number,
                            stay=stay,
                            amount=advance_payment,
                            payment_method=data.get('payment_method', 'CASH'),
                            transaction_reference=data.get('transaction_reference', 'Walk-in Payment'),
                            received_by=user,
                            shift=user_shift,
                            notes='Initial Walk-in Advance Payment'
                        )
                    break
                except IntegrityError:
                    continue

        # Automatic Customer Advance Credit Wallet Application
        from apps.billing.services import calculate_stay_bill
        stay_credits = 0.0
        overpaid_stays = []
        stay_filter = {'primary_customer': customer}
        if user_prop:
            stay_filter['property'] = user_prop
        for s in Stay.objects.filter(**stay_filter).exclude(id=stay.id):
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
                                property=user_prop,
                                payment_number=payment_number,
                                stay=stay,
                                amount=wallet_to_apply,
                                payment_method='OTHER',
                                transaction_reference='CUSTOMER_ADVANCE_WALLET',
                                received_by=user,
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
                                        received_by=user,
                                        notes=f'Wallet credit transfer of ₹{draw_amt:.2f} to Stay #{stay.stay_number}'
                                    )
                                break
                            except IntegrityError:
                                continue
                        remaining_to_deduct -= draw_amt

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
        require_perm(request.user, 'stays', 'can_extend', "You do not have permission to extend stay dates.")
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
        require_perm(request.user, 'stays', 'can_extend', "You do not have permission to transfer rooms.")
        stay = self.get_object()
        if stay.status != 'CHECKED_IN':
            return Response({'success': False, 'message': 'Only active checked-in stays can undergo room transfer.', 'errors': {'status': ['Stay is not active.']}}, status=status.HTTP_400_BAD_REQUEST)


        target_room_id = request.data.get('target_room')
        if not target_room_id:
            return Response({'success': False, 'message': 'target_room is required.', 'errors': {'target_room': ['Required.']}}, status=status.HTTP_400_BAD_REQUEST)

        new_room = Room.objects.filter(property=stay.property, pk=target_room_id).first() if stay.property else Room.objects.filter(pk=target_room_id).first()
        if not new_room:
            return Response({'success': False, 'message': 'Target room does not exist in this hotel property.', 'errors': {'target_room': ['Invalid room ID.']}}, status=status.HTTP_404_NOT_FOUND)

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
        require_perm(request.user, 'stays', 'can_checkout', "You do not have permission to process guest check-outs.")
        stay = self.get_object()

        # Determine custom actual_checkout_date and actual_checkout_time if provided
        now = datetime.datetime.now()
        custom_date_str = request.data.get('actual_checkout_date')
        custom_time_str = request.data.get('actual_checkout_time')

        if custom_date_str:
            try:
                actual_date = datetime.datetime.strptime(custom_date_str, '%Y-%m-%d').date()
            except ValueError:
                actual_date = now.date()
        else:
            actual_date = now.date()

        if custom_time_str:
            try:
                time_parts = custom_time_str.split(':')
                actual_time = datetime.time(int(time_parts[0]), int(time_parts[1]))
            except Exception:
                actual_time = now.time()
        else:
            actual_time = now.time()

        actual_checkout_dt = datetime.datetime.combine(actual_date, actual_time)
        if timezone.is_naive(actual_checkout_dt):
            actual_checkout_dt = timezone.make_aware(actual_checkout_dt)

        # Allow updating chargeable_nights at checkout with boundary validation
        if 'chargeable_nights' in request.data:
            cn_val = request.data.get('chargeable_nights')
            if cn_val is not None and str(cn_val).strip().isdigit():
                val_cn = int(str(cn_val).strip())
                cal_nights = max(1, (actual_date - stay.check_in_date).days)
                min_allowed = max(1, cal_nights - 1)
                max_allowed = cal_nights + 1
                if not (min_allowed <= val_cn <= max_allowed):
                    return Response({
                        'success': False,
                        'message': f"Considered nights ({val_cn}) must be between {min_allowed} and {max_allowed} for a {cal_nights}-night calendar stay.",
                        'errors': {'chargeable_nights': [f"Must be between {min_allowed} and {max_allowed}."]}
                    }, status=status.HTTP_400_BAD_REQUEST)
                stay.chargeable_nights = val_cn
                stay.save()

        # 1. Validate Checkout Services
        is_valid, bill, err_msg = validate_checkout(stay, actual_checkout_dt)
        if not is_valid:
            return Response({'success': False, 'message': err_msg, 'errors': {'checkout': [err_msg]}}, status=status.HTTP_400_BAD_REQUEST)

        # 2. Allow updating discount at checkout with permission validation
        if 'discount_value' in request.data:
            try:
                disc_float = float(request.data.get('discount_value') or 0)
            except (ValueError, TypeError):
                disc_float = 0.0
            if disc_float > 0:
                require_perm(request.user, 'billing', 'can_give_discount', "You do not have permission to apply discounts.")
                max_pct = get_perm_limit(request.user, 'billing', 'max_discount_percent', fallback=10.0)
                disc_type = request.data.get('discount_type', stay.discount_type)
                if disc_type == 'PERCENT' and disc_float > max_pct:
                    return Response({'success': False, 'message': f"Discount of {disc_float}% exceeds your allowed limit of {max_pct}%."}, status=status.HTTP_400_BAD_REQUEST)

        if 'discount_type' in request.data:
            stay.discount_type = request.data['discount_type']
        if 'discount_value' in request.data:
            stay.discount_value = request.data['discount_value']
        if 'discount_reason' in request.data:
            stay.discount_reason = request.data['discount_reason']
        stay.save()

        # 3. Handle checkout payment if provided
        # 3. Handle checkout payment if provided
        payment_amount = request.data.get('payment_amount')
        if payment_amount and float(payment_amount) > 0:
            from apps.shifts.services import get_active_shift_for_user
            user_shift = get_active_shift_for_user(request.user)

            pay_number = generate_unique_payment_number("PAY-")
            for _ in range(10):
                try:
                    with transaction.atomic():
                        Payment.objects.create(
                            property=stay.property,
                            payment_number=pay_number,
                            stay=stay,
                            amount=payment_amount,
                            payment_method=request.data.get('payment_method', 'CASH'),
                            transaction_reference=request.data.get('transaction_reference', 'Checkout Payment'),
                            received_by=request.user,
                            shift=user_shift,
                            notes='Final checkout payment'
                        )
                    break
                except IntegrityError:
                    pay_number = generate_unique_payment_number("PAY-")

        # Recalculate bill after payment
        final_bill = calculate_stay_bill(stay, actual_checkout_dt)

        # Check unsettled balance checkout permission
        bal = float(final_bill.get('balance', 0))
        if bal > 0.01 and not user_has_perm(request.user, 'stays', 'can_checkout_with_balance'):
            return Response({
                'success': False,
                'message': f"Checkout blocked: Stay has an unsettled balance of ₹{bal:.2f}. Your staff role is not permitted to check out guests with an unpaid balance. Please collect payment or contact your Manager/Owner.",
                'errors': {'balance': ['Unsettled balance requires manager authorization.']}
            }, status=status.HTTP_403_FORBIDDEN)

        # 4. Complete Stay Checkout with actual departure date & time
        stay.actual_checkout_date = actual_date
        stay.actual_checkout_time = actual_time
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
        settings_obj = Settings.get_settings(prop=stay.property)
        inv_prefix = settings_obj.invoice_prefix or "INV-"

        # Check if an invoice already exists for this stay
        existing_invoice = getattr(stay, 'invoice', None) or Invoice.objects.filter(stay=stay).first()
        if existing_invoice and existing_invoice.invoice_number:
            # Preserve existing invoice number if not conflicting with another stay's invoice
            if not Invoice.objects.all().filter(invoice_number=existing_invoice.invoice_number).exclude(id=existing_invoice.id).exists():
                inv_number = existing_invoice.invoice_number
            else:
                inv_number = generate_unique_invoice_number(stay.property, inv_prefix)
        else:
            inv_number = generate_unique_invoice_number(stay.property, inv_prefix)

        # Resilient creation / update with savepoint retry to guarantee no UNIQUE constraint failure
        invoice = None
        for attempt in range(10):
            try:
                with transaction.atomic():
                    invoice, _ = Invoice.objects.update_or_create(
                        stay=stay,
                        defaults={
                            'property': stay.property,
                            'invoice_number': inv_number,
                            'subtotal': final_bill.get('gross_subtotal', final_bill.get('subtotal', 0)),
                            'discount': final_bill.get('discount_amount', 0),
                            'tax': final_bill.get('gst_amount', final_bill.get('tax_amount', 0)),
                            'grand_total': final_bill.get('grand_total', 0),
                            'paid_amount': final_bill.get('total_paid', 0),
                            'balance': final_bill.get('balance', 0),
                        }
                    )
                break
            except IntegrityError:
                inv_number = generate_unique_invoice_number(stay.property, inv_prefix)

        if not invoice:
            invoice = getattr(stay, 'invoice', None) or Invoice.objects.filter(stay=stay).first()

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
        user = self.request.user
        if user and not user.is_superuser and getattr(user, 'property', None):
            queryset = queryset.filter(stay__property=user.property)
        stay_id = self.request.query_params.get('stay')
        if stay_id:
            queryset = queryset.filter(stay_id=stay_id)
        return queryset
        if stay_id:
            queryset = queryset.filter(stay_id=stay_id)
        return queryset
