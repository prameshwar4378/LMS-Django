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
        if dt_in < (now_tz - datetime.timedelta(minutes=15)):
            errors['check_in_date'] = ["Booking check-in time cannot be in the past."]
            return None, errors

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
    nights = max(1, (dt_out.date() - dt_in.date()).days)
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

    total_amount = max(0.0, subtotal - calculated_discount)

    # 6. Advance Payment Validation (Rule #33)
    advance = float(data.get('advance_payment') or data.get('advance_amount') or (instance.advance_amount if instance else 0) or 0)
    if advance < 0:
        errors['advance_amount'] = ["Advance payment cannot be negative."]
        return None, errors

    if advance > total_amount and total_amount > 0:
        errors['advance_amount'] = ["Advance payment cannot exceed the applicable booking amount."]
        return None, errors

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
        'advance_amount': advance,
    }
    return validated_attrs, None

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
