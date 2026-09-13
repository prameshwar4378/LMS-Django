import datetime
from django.utils import timezone
from apps.settings_app.models import Settings
from apps.rooms.models import Room
from apps.rooms.services import check_room_availability
from .models import Booking

def parse_iso_datetime(date_val, time_val, default_time):
    """
    Parses date and time strings or objects into timezone-aware datetime.
    Supports YYYY-MM-DD, DD-MM-YYYY, DD/MM/YYYY, YYYY/MM/DD.
    """
    if not date_val:
        return None

    if isinstance(date_val, str):
        date_obj = None
        date_str = date_val.strip()
        for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y', '%Y/%m/%d'):
            try:
                date_obj = datetime.datetime.strptime(date_str, fmt).date()
                break
            except ValueError:
                pass
        if not date_obj:
            return None
    elif isinstance(date_val, datetime.date):
        date_obj = date_val
    else:
        return None

    if not time_val:
        time_parts = [int(x) for x in default_time.split(':')]
        time_obj = datetime.time(time_parts[0], time_parts[1])
    elif isinstance(time_val, str):
        parts = [int(x) for x in time_val.split(':')]
        time_obj = datetime.time(parts[0], parts[1])
    elif isinstance(time_val, datetime.time):
        time_obj = time_val
    else:
        time_obj = datetime.time(12, 0)

    combined = datetime.datetime.combine(date_obj, time_obj)
    if timezone.is_naive(combined):
        combined = timezone.make_aware(combined)
    return combined

def validate_booking_payload(data, user=None, instance=None, is_walkin=False):
    """
    Core Booking Validation & Calculations Service (Rule #80).
    Validates all 80 rules prior to save.
    Returns (validated_attrs, error_dict).
    """
    settings_obj = Settings.get_settings()
    errors = {}

    # 1. Room Selection (Rule #9)
    room_id = data.get('room')
    if isinstance(room_id, Room):
        room = room_id
    elif room_id:
        try:
            room = Room.objects.get(pk=room_id)
        except Room.DoesNotExist:
            errors['room'] = ["Selected room does not exist."]
            return None, errors
    else:
        room = instance.room if instance else None

    if not room:
        errors['room'] = ["Please select a room."]
        return None, errors

    # 2. Datetime Parsing & Rules (Rules #1, #2, #3, #4)
    default_in_time = settings_obj.default_checkin_time.strftime('%H:%M') if settings_obj.default_checkin_time else '12:00'
    default_out_time = settings_obj.default_checkout_time.strftime('%H:%M') if settings_obj.default_checkout_time else '11:00'

    check_in_d = data.get('check_in_date') or (instance.check_in_date if instance else None)
    check_in_t = data.get('check_in_time') or (instance.check_in_time if instance else None)
    checkout_d = data.get('expected_checkout_date') or (instance.expected_checkout_date if instance else None)
    checkout_t = data.get('expected_checkout_time') or (instance.expected_checkout_time if instance else None)

    try:
        dt_in = parse_iso_datetime(check_in_d, check_in_t, default_in_time)
        dt_out = parse_iso_datetime(checkout_d, checkout_t, default_out_time)
    except Exception as e:
        errors['check_in_date'] = ["Please enter valid check-in and checkout dates and times."]
        return None, errors

    if not dt_in:
        errors['check_in_date'] = ["Check-in date and time cannot be empty."]
        return None, errors

    if not dt_out:
        errors['expected_checkout_date'] = ["Please enter a valid checkout date and time after the check-in time."]
        return None, errors

    if dt_out <= dt_in:
        errors['expected_checkout_date'] = ["Check-out date and time must be later than check-in date and time."]
        return None, errors

    # Minimum stay duration (Rule #7)
    min_stay_hours = getattr(settings_obj, 'min_stay_duration_hours', 1) or 1
    if (dt_out - dt_in) < datetime.timedelta(hours=min_stay_hours):
        errors['expected_checkout_date'] = [f"Minimum stay duration is {min_stay_hours} hour(s)."]
        return None, errors

    now_tz = timezone.now()

    # Past Booking Validation (Rule #5)
    if not is_walkin and not instance:
        # Buffer of 15 minutes for real-time form submission delay
        if dt_in.date() < now_tz.date():
            errors['check_in_date'] = ["Booking check-in date cannot be in the past."]
            return None, errors
        elif dt_in.date() == now_tz.date() and dt_in < (now_tz - datetime.timedelta(minutes=15)):
            # Same-day reservation booked after standard check-in time (e.g. 12:00 PM):
            # Auto-align check-in datetime to current time so same-day evening bookings succeed smoothly
            dt_in = now_tz

    # Maximum Advance Booking Period (Rule #8)
    max_adv_days = getattr(settings_obj, 'max_advance_booking_days', 90) or 90
    if (dt_in - now_tz) > datetime.timedelta(days=max_adv_days):
        errors['check_in_date'] = [f"Booking cannot be made more than {max_adv_days} days in advance."]
        return None, errors

    # 3. Guest Count & Capacity Validation (Rules #27, #28)
    adults = int(data.get('adults', instance.adults if instance else 1))
    children = int(data.get('children', instance.children if instance else 0))

    if adults < 1:
        errors['adults'] = ["At least one adult guest is required."]
        return None, errors
    if children < 0:
        errors['children'] = ["Children count cannot be negative."]
        return None, errors

    # Room capacity limit check removed per user directive

    # 4. Room Rate & Price Security (Rules #29, #30)
    base_rate = float(data.get('room_rate') or getattr(room, 'base_price', None) or room.room_type.base_price or 0)
    if base_rate <= 0:
        errors['room_rate'] = ["Room rate must be greater than zero."]
        return None, errors

    # Calculate Nights & Total
    cal_nights = max(1, (dt_out.date() - dt_in.date()).days)
    chargeable_nights_in = data.get('chargeable_nights')
    validated_chargeable_nights = None
    if chargeable_nights_in is not None and str(chargeable_nights_in).strip().isdigit():
        val_cn = int(str(chargeable_nights_in).strip())
        min_allowed = max(1, cal_nights - 1)
        max_allowed = cal_nights + 1
        if not (min_allowed <= val_cn <= max_allowed):
            errors['chargeable_nights'] = [f"Considered nights ({val_cn}) must be between {min_allowed} and {max_allowed} for a {cal_nights}-night calendar stay."]
            return None, errors
        validated_chargeable_nights = val_cn
        nights = val_cn
    else:
        nights = cal_nights

    subtotal = nights * base_rate

    # 5. Discount Validation (Rules #31, #32)
    discount_type = data.get('discount_type') or (instance.discount_type if instance else 'FIXED') or 'FIXED'
    discount_val = float(data.get('discount_value', instance.discount_value if instance else 0) or 0)

    if discount_val < 0:
        errors['discount_value'] = ["Discount cannot be negative."]
        return None, errors

    calculated_discount = 0.0
    if discount_type == 'PERCENTAGE':
        if discount_val > 100:
            errors['discount_value'] = ["Percentage discount cannot exceed 100%."]
            return None, errors
        calculated_discount = (subtotal * discount_val) / 100.0

        # Receptionist Discount Cap check
        max_rec_disc = float(getattr(settings_obj, 'max_receptionist_discount_percent', 10.0) or 10.0)
        if user and not (user.is_superuser or getattr(user, 'role', '') in ['ADMIN', 'SUPER_ADMIN']):
            if discount_val > max_rec_disc:
                errors['discount_value'] = [f"Your account is not authorized to apply more than {max_rec_disc}% discount."]
                return None, errors

    elif discount_type == 'FIXED':
        calculated_discount = discount_val
        if calculated_discount > subtotal:
            errors['discount_value'] = ["Discount cannot be greater than the bill amount."]
            return None, errors

    discounted_subtotal = max(0.0, subtotal - calculated_discount)

    # 6. GST & Grand Total Calculation
    tax_enabled = getattr(settings_obj, 'tax_enabled', getattr(settings_obj, 'enable_gst', True))
    if tax_enabled:
        tax_pct = getattr(settings_obj, 'tax_percentage', getattr(settings_obj, 'gst_percent', 12.0))
        gst_percent = float(tax_pct if tax_pct is not None else 0.0)
    else:
        gst_percent = 0.0
    gst_amount = round((discounted_subtotal * gst_percent) / 100.0, 2)
    grand_total_amount = round(discounted_subtotal + gst_amount, 2)

    # 7. Advance Payment Validation & Handling (Rule #33)
    advance = float(data.get('advance_payment') or data.get('advance_amount') or (instance.advance_amount if instance else 0) or 0)
    if advance < 0:
        errors['advance_amount'] = ["Advance payment cannot be negative."]
        return None, errors

    # Prevent advance truncation:
    # If advance exceeds grand total, cap the booking's direct advance allocation to grand_total_amount,
    # and calculate the excess advance to be credited directly to the customer's wallet ledger.
    excess_advance = 0.0
    booking_advance = advance
    if grand_total_amount > 0 and advance > grand_total_amount:
        excess_advance = round(advance - grand_total_amount, 2)
        booking_advance = grand_total_amount

    # 7. Room Availability Overlap Check (Rules #10, #11, #12, #13, #14, #16)
    is_avail, avail_err = check_room_availability(
        room,
        dt_in,
        dt_out,
        exclude_booking_id=instance.id if instance else None,
        check_cleaning=is_walkin
    )
    if not is_avail:
        errors['room'] = [avail_err]
        return None, errors

    # Construct validated dict
    validated_attrs = {
        'room': room,
        'check_in_date': dt_in.date(),
        'check_in_time': dt_in.time(),
        'expected_checkout_date': dt_out.date(),
        'expected_checkout_time': dt_out.time(),
        'adults': adults,
        'children': children,
        'room_rate': base_rate,
        'discount_type': discount_type,
        'discount_value': discount_val,
        'advance_amount': booking_advance,
        'excess_advance': excess_advance,
        'chargeable_nights': validated_chargeable_nights,
    }
    return validated_attrs, None

def credit_excess_advance_to_wallet(customer, excess_amount, booking=None, property_obj=None, user=None, shift=None, payment_method='CASH', transaction_ref=''):
    """
    Credits excess booking advance to customer's advance credit wallet
    and records an audit-compliant Payment transaction in the cashier shift.
    """
    if not customer or float(excess_amount or 0) <= 0:
        return None

    from decimal import Decimal
    from django.db import transaction, IntegrityError
    from apps.billing.models import Payment
    from apps.billing.services import generate_unique_payment_number

    excess_dec = Decimal(str(round(float(excess_amount), 2)))
    customer.advance_credit = (customer.advance_credit or Decimal('0.00')) + excess_dec
    customer.save(update_fields=['advance_credit'])

    prop = property_obj or getattr(booking, 'property', None) or getattr(customer, 'property', None)
    payment_method = payment_method or 'CASH'
    if payment_method not in dict(Payment.PaymentMethod.choices):
        payment_method = 'CASH'

    bk_num = getattr(booking, 'booking_number', '')
    ref = transaction_ref or (f"Wallet Deposit from Booking #{bk_num}" if bk_num else "Customer Advance Wallet Deposit")
    notes = f"Excess advance payment of ₹{excess_dec} from Booking #{bk_num} credited to guest wallet." if bk_num else f"Advance wallet deposit: ₹{excess_dec}"

    pay = None
    for _ in range(10):
        payment_number = generate_unique_payment_number("PAY-")
        try:
            with transaction.atomic():
                pay = Payment.objects.create(
                    property=prop,
                    payment_number=payment_number,
                    booking=booking,
                    customer=customer,
                    stay=None,
                    amount=excess_dec,
                    payment_method=payment_method,
                    transaction_reference=ref,
                    received_by=user,
                    created_by=user,
                    updated_by=user,
                    shift=shift,
                    notes=notes
                )
                pay._change_reason = notes
                pay.save()
            break
        except IntegrityError:
            continue

    if pay and shift:
        from apps.shifts.models import ShiftAuditLog
        try:
            ShiftAuditLog.objects.create(
                shift=shift,
                user=user,
                action='BOOKING_ADVANCE_COLLECTED',
                description=f"Credited ₹{excess_dec} excess advance from Booking #{bk_num} to guest wallet",
                metadata={'booking_number': bk_num, 'amount': str(excess_dec), 'customer_id': customer.id}
            )
        except Exception:
            pass

    return pay

def transition_booking_status(booking, new_status):
    """
    Enforces valid booking status state machine transitions (Rules #20, #21).
    """
    valid_transitions = {
        'PENDING': ['CONFIRMED', 'CANCELLED'],
        'CONFIRMED': ['CHECKED_IN', 'COMPLETED', 'CANCELLED', 'NO_SHOW'],
        'CHECKED_IN': ['COMPLETED'],
        'COMPLETED': [],
        'CANCELLED': [],
        'NO_SHOW': [],
    }

    current = booking.status
    if new_status not in valid_transitions.get(current, []):
        return False, f"Invalid status transition from {current} to {new_status}."

    booking.status = new_status
    booking.save()
    return True, None


def process_booking_cancellation_advance(
    booking,
    user=None,
    action=None,
    refund_method=None,
    amount=None,
    shift=None,
    notes=None,
    transaction_ref=None
):
    """
    Handles advance deposit when a booking is cancelled or marked no-show.
    Supported actions:
      - 'WALLET_CREDIT': Credits advance to customer's advance_credit wallet.
      - 'REFUND': Creates negative Payment record reversing the advance & links to active shift.
      - 'FORFEIT': Retains advance deposit as cancellation fee (no wallet credit, no refund).
    """
    from decimal import Decimal
    from django.db import transaction, models, IntegrityError
    from apps.billing.models import Payment
    from apps.billing.services import generate_unique_payment_number

    # 1. Calculate total unrefunded advance amount
    booking_adv = Decimal(str(booking.advance_amount or '0.00'))
    pos_pays = booking.payments.filter(amount__gt=0).aggregate(tot=models.Sum('amount'))['tot'] or Decimal('0.00')
    deposit_val = max(booking_adv, pos_pays)
    
    already_refunded = abs(booking.payments.filter(amount__lt=0).aggregate(tot=models.Sum('amount'))['tot'] or Decimal('0.00'))
    refundable_advance = max(Decimal('0.00'), deposit_val - already_refunded)

    if refundable_advance <= Decimal('0.00'):
        return {
            'advance_amount': 0.0,
            'action': 'NONE',
            'wallet_credit_added': 0.0,
            'refund_payment_number': None,
            'customer_wallet_balance': float(booking.customer.advance_credit) if booking.customer else 0.0,
            'message': 'No advance deposit to process.'
        }

    # Override custom amount if specified
    if amount is not None:
        try:
            custom_dec = Decimal(str(amount))
            if Decimal('0.00') <= custom_dec <= refundable_advance:
                refundable_advance = custom_dec
        except (ValueError, TypeError):
            pass

    action_norm = (action or 'WALLET_CREDIT').upper().strip()
    if action_norm not in ['WALLET_CREDIT', 'REFUND', 'FORFEIT']:
        action_norm = 'WALLET_CREDIT'

    customer = booking.customer
    bk_num = booking.booking_number
    cust_name = customer.full_name if customer else 'Guest'
    user_name = (user.get_full_name() or user.username) if user else "Staff"

    refund_pay = None
    wallet_credit_added = Decimal('0.00')

    # Resolve active shift if not passed
    if not shift and user and user.is_authenticated:
        from apps.shifts.services import get_active_shift_for_user
        shift = get_active_shift_for_user(user)
        if not shift:
            from apps.shifts.models import Shift
            shift = Shift.objects.filter(user=user, status__in=[Shift.Status.OPEN, Shift.Status.CLOSING]).first()
        if not shift and booking.property:
            from apps.shifts.models import Shift
            shift = Shift.objects.filter(property=booking.property, status=Shift.Status.OPEN).first()

    if action_norm == 'WALLET_CREDIT':
        if customer and refundable_advance > Decimal('0.00'):
            customer.advance_credit = (customer.advance_credit or Decimal('0.00')) + refundable_advance
            customer.save(update_fields=['advance_credit'])
            wallet_credit_added = refundable_advance

            c_notes = f"\n[Cancellation] ₹{refundable_advance:.2f} advance deposit credited to guest wallet."
            booking.notes = (booking.notes or "") + c_notes
            booking._change_reason = f"Cancelled Booking #{bk_num}. Credited ₹{refundable_advance:.2f} advance to guest wallet."
            booking.save(update_fields=['notes'])

            if shift:
                from apps.shifts.services import log_shift_action
                try:
                    log_shift_action(
                        shift,
                        user,
                        'BOOKING_ADVANCE_CREDITED_TO_WALLET',
                        f"Advance of ₹{refundable_advance:.2f} from cancelled Booking #{bk_num} credited to guest wallet ({cust_name})",
                        {'booking_number': bk_num, 'amount': float(refundable_advance), 'customer_id': customer.id if customer else None}
                    )
                except Exception:
                    pass

    elif action_norm == 'REFUND':
        if not refund_method or refund_method not in dict(Payment.PaymentMethod.choices):
            orig_p = booking.payments.filter(amount__gt=0).first()
            refund_method = orig_p.payment_method if orig_p else 'CASH'

        ref_number = None
        for _ in range(10):
            payment_number = generate_unique_payment_number("PAY-")
            try:
                with transaction.atomic():
                    refund_pay = Payment.objects.create(
                        property=booking.property,
                        payment_number=payment_number,
                        booking=booking,
                        customer=customer,
                        stay=None,
                        shift=shift,
                        amount=-refundable_advance,
                        payment_method=refund_method,
                        transaction_reference=transaction_ref or f"REFUND-BK-{bk_num}",
                        received_by=user,
                        created_by=user,
                        updated_by=user,
                        notes=notes or f"Advance refund of ₹{refundable_advance:.2f} for cancelled Booking #{bk_num} via {refund_method}"
                    )
                ref_number = payment_number
                break
            except IntegrityError:
                continue

        c_notes = f"\n[Cancellation] ₹{refundable_advance:.2f} advance deposit refunded via {refund_method} (PAY: {ref_number})."
        booking.notes = (booking.notes or "") + c_notes
        booking._change_reason = f"Cancelled Booking #{bk_num}. Refunded ₹{refundable_advance:.2f} advance via {refund_method}."
        booking.save(update_fields=['notes'])

        if shift:
            from apps.shifts.services import log_shift_action
            try:
                log_shift_action(
                    shift,
                    user,
                    'BOOKING_ADVANCE_REFUNDED',
                    f"Refunded ₹{refundable_advance:.2f} advance ({refund_method}) for cancelled Booking #{bk_num} to {cust_name} by {user_name}",
                    {
                        'booking_number': bk_num,
                        'amount': float(refundable_advance),
                        'payment_method': refund_method,
                        'payment_number': ref_number
                    }
                )
            except Exception:
                pass

    elif action_norm == 'FORFEIT':
        c_notes = f"\n[Cancellation] Advance deposit of ₹{refundable_advance:.2f} retained as cancellation fee."
        booking.notes = (booking.notes or "") + c_notes
        booking._change_reason = f"Cancelled Booking #{bk_num}. Advance deposit of ₹{refundable_advance:.2f} retained as cancellation fee."
        booking.save(update_fields=['notes'])

    return {
        'advance_amount': float(refundable_advance),
        'action': action_norm,
        'wallet_credit_added': float(wallet_credit_added),
        'refund_payment_number': refund_pay.payment_number if refund_pay else None,
        'refund_method': refund_method if action_norm == 'REFUND' else None,
        'customer_wallet_balance': float(customer.advance_credit) if customer else 0.0,
        'message': f"Advance deposit of ₹{refundable_advance:.2f} processed via {action_norm}."
    }
