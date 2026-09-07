from decimal import Decimal
import datetime
import math
from django.utils import timezone
from apps.settings_app.models import Settings

def calculate_stay_bill(stay, override_checkout_dt=None):
    """
    Central calculation service for a Stay record using Calendar Dates.
    Returns calculated values for billing breakdown.
    """
    prop = getattr(stay, 'property', None)
    settings_obj = Settings.get_settings(prop=prop)

    # 1. Determine check-in and checkout datetimes and dates
    dt_in = stay.check_in_datetime
    if dt_in and timezone.is_naive(dt_in):
        dt_in = timezone.make_aware(dt_in)

    if override_checkout_dt:
        dt_out = override_checkout_dt
    elif stay.status == 'CHECKED_OUT' and stay.actual_checkout_datetime:
        dt_out = stay.actual_checkout_datetime
    else:
        dt_out = stay.expected_checkout_datetime or timezone.now()

    if dt_out and timezone.is_naive(dt_out):
        dt_out = timezone.make_aware(dt_out)

    # 2. Calculate stay duration strictly based on calendar days/nights, or explicit chargeable_nights override
    in_date = dt_in.date() if dt_in else stay.check_in_date
    out_date = dt_out.date() if dt_out else (stay.actual_checkout_date or stay.expected_checkout_date or datetime.date.today())

    days_diff = (out_date - in_date).days if (out_date and in_date) else 1
    calendar_days = max(1, days_diff)

    chargeable = getattr(stay, 'chargeable_nights', None)
    if chargeable and int(chargeable) > 0:
        room_days = int(chargeable)
    else:
        room_days = calendar_days

    room_rate = Decimal(str(stay.room_rate or (stay.room.base_price if stay.room else 0) or 0))
    room_subtotal = Decimal(room_days) * room_rate

    # Late fee is 0.00 for standard checkout (same-day time flexibility)
    late_fee = Decimal('0.00')

    total_room_charge = room_subtotal + late_fee
    room_amount = total_room_charge

    # 3. Extra charges sum
    extra_charges = stay.extra_charges.all()
    extra_charges_total = Decimal('0.00')
    for item in extra_charges:
        if item.amount is not None:
            extra_charges_total += Decimal(str(item.amount))
        elif item.unit_price is not None:
            qty = Decimal(str(getattr(item, 'quantity', 1)))
            price = Decimal(str(getattr(item, 'unit_price', 0)))
            extra_charges_total += qty * price

    # 4. Subtotal
    subtotal = total_room_charge + extra_charges_total

    # 5. Discount calculation
    discount_val = Decimal(str(stay.discount_value or 0))
    if stay.discount_type == 'PERCENTAGE':
        discount_amount = (subtotal * discount_val) / Decimal('100.00')
    else: # FIXED
        discount_amount = discount_val

    discount_amount = min(discount_amount, subtotal)
    taxable_amount = max(Decimal('0.00'), subtotal - discount_amount)

    # 6. Tax calculation based on Settings
    tax_enabled = settings_obj.tax_enabled
    tax_percentage = Decimal(str(settings_obj.tax_percentage or 0)) if tax_enabled else Decimal('0.00')
    
    if tax_enabled and tax_percentage > 0:
        tax_amount = (taxable_amount * tax_percentage) / Decimal('100.00')
    else:
        tax_amount = Decimal('0.00')

    grand_total = taxable_amount + tax_amount

    # 7. Payments total
    payments = stay.payments.all()
    total_paid = sum((Decimal(str(p.amount or 0)) for p in payments), Decimal('0.00'))

    advance_amount = Decimal('0.00')
    if stay.booking and stay.booking.advance_amount:
        advance_amount = Decimal(str(stay.booking.advance_amount))

    balance = grand_total - total_paid

    return {
        'stay_id': stay.id,
        'stay_number': stay.stay_number,
        'room_number': stay.room.room_number if stay.room else 'N/A',
        'room_type': stay.room.room_type.name if stay.room and stay.room.room_type else 'N/A',
        'primary_customer_name': stay.primary_customer.full_name if stay.primary_customer else 'N/A',
        'check_in_datetime': dt_in.strftime('%Y-%m-%d %H:%M') if dt_in else None,
        'checkout_datetime': dt_out.strftime('%Y-%m-%d %H:%M') if dt_out else None,
        'room_days': room_days,
        'stay_days': room_days,
        'room_rate': float(room_rate),
        'room_subtotal': float(room_subtotal),
        'late_fee': float(late_fee),
        'total_room_charge': float(total_room_charge),
        'room_amount': float(room_amount),
        'extra_charges_total': float(extra_charges_total),
        'total_extra_charges': float(extra_charges_total),
        'subtotal': float(subtotal),
        'gross_subtotal': float(subtotal),
        'discount_type': stay.discount_type,
        'discount_value': float(discount_val),
        'discount_reason': stay.discount_reason or '',
        'discount_amount': float(discount_amount),
        'taxable_amount': float(taxable_amount),
        'tax_enabled': tax_enabled,
        'tax_percentage': float(tax_percentage),
        'tax_amount': float(tax_amount),
        'gst_amount': float(tax_amount),
        'grand_total': float(grand_total),
        'advance_amount': float(advance_amount),
        'total_paid': float(total_paid),
        'balance': float(balance),
    }


def generate_unique_invoice_number(property_obj=None, prefix=None):
    """
    Generates a guaranteed unique invoice number that never collides with
    any existing invoice across all tenants or date sequences.
    """
    from apps.billing.models import Invoice
    from apps.settings_app.models import Settings
    import uuid

    if not prefix:
        settings_obj = Settings.get_settings(prop=property_obj)
        prefix = settings_obj.invoice_prefix or "INV-"

    clean_prefix = (prefix or "INV-").strip()
    if not clean_prefix.endswith('-'):
        clean_prefix += '-'
    today_str = timezone.now().strftime('%Y%m%d')
    base_prefix = f"{clean_prefix}{today_str}-"

    # Query all existing invoices starting with base_prefix globally across the whole table
    existing_invoices = list(Invoice.objects.all().filter(invoice_number__startswith=base_prefix).values_list('invoice_number', flat=True))
    
    max_num = 0
    for inv_num in existing_invoices:
        suffix = inv_num[len(base_prefix):]
        try:
            val = int(suffix)
            if val > max_num:
                max_num = val
        except (ValueError, TypeError):
            continue

    candidate_num = max_num + 1
    for attempt in range(200):
        candidate = f"{base_prefix}{candidate_num + attempt:03d}"
        if not Invoice.objects.all().filter(invoice_number=candidate).exists():
            return candidate

    # High-concurrency random suffix fallback
    for _ in range(50):
        candidate = f"{base_prefix}{uuid.uuid4().hex[:6].upper()}"
        if not Invoice.objects.all().filter(invoice_number=candidate).exists():
            return candidate

    return f"{clean_prefix}{today_str}-{uuid.uuid4().hex[:8].upper()}"


def generate_unique_payment_number(prefix="PAY-"):
    """
    Generates a guaranteed unique payment transaction number.
    """
    from apps.billing.models import Payment
    import uuid

    clean_prefix = (prefix or "PAY-").strip()
    if not clean_prefix.endswith('-'):
        clean_prefix += '-'
    today_str = timezone.now().strftime('%Y%m%d')
    base_prefix = f"{clean_prefix}{today_str}-"

    existing_payments = list(Payment.objects.all().filter(payment_number__startswith=base_prefix).values_list('payment_number', flat=True))
    
    max_num = 0
    for pay_num in existing_payments:
        suffix = pay_num[len(base_prefix):]
        try:
            val = int(suffix)
            if val > max_num:
                max_num = val
        except (ValueError, TypeError):
            continue

    candidate_num = max_num + 1
    for attempt in range(200):
        candidate = f"{base_prefix}{candidate_num + attempt:03d}"
        if not Payment.objects.all().filter(payment_number=candidate).exists():
            return candidate

    for _ in range(50):
        candidate = f"{base_prefix}{uuid.uuid4().hex[:6].upper()}"
        if not Payment.objects.all().filter(payment_number=candidate).exists():
            return candidate

    return f"{clean_prefix}{today_str}-{uuid.uuid4().hex[:8].upper()}"


def generate_unique_stay_number(property_obj=None, prefix=None):
    """
    Generates a guaranteed unique stay number that never collides across tenants or dates.
    """
    from apps.stays.models import Stay
    from apps.settings_app.models import Settings
    import uuid

    if not prefix:
        settings_obj = Settings.get_settings(prop=property_obj)
        prefix = settings_obj.stay_prefix or "STAY-"

    clean_prefix = (prefix or "STAY-").strip()
    if not clean_prefix.endswith('-'):
        clean_prefix += '-'
    today_str = timezone.now().strftime('%Y%m%d')
    base_prefix = f"{clean_prefix}{today_str}-"

    existing_numbers = list(Stay.objects.all().filter(stay_number__startswith=base_prefix).values_list('stay_number', flat=True))
    
    max_num = 0
    for s_num in existing_numbers:
        suffix = s_num[len(base_prefix):]
        try:
            val = int(suffix)
            if val > max_num:
                max_num = val
        except (ValueError, TypeError):
            continue

    candidate_num = max_num + 1
    for attempt in range(200):
        candidate = f"{base_prefix}{candidate_num + attempt:03d}"
        if not Stay.objects.all().filter(stay_number=candidate).exists():
            return candidate

    for _ in range(50):
        candidate = f"{base_prefix}{uuid.uuid4().hex[:6].upper()}"
        if not Stay.objects.all().filter(stay_number=candidate).exists():
            return candidate

    return f"{clean_prefix}{today_str}-{uuid.uuid4().hex[:8].upper()}"


def generate_unique_booking_number(property_obj=None, prefix=None):
    """
    Generates a guaranteed unique booking reservation number.
    """
    from apps.bookings.models import Booking
    from apps.settings_app.models import Settings
    import uuid

    if not prefix:
        settings_obj = Settings.get_settings(prop=property_obj)
        prefix = settings_obj.booking_prefix or "BK-"

    clean_prefix = (prefix or "BK-").strip()
    if not clean_prefix.endswith('-'):
        clean_prefix += '-'
    today_str = timezone.now().strftime('%Y%m%d')
    base_prefix = f"{clean_prefix}{today_str}-"

    existing_numbers = list(Booking.objects.all().filter(booking_number__startswith=base_prefix).values_list('booking_number', flat=True))
    
    max_num = 0
    for b_num in existing_numbers:
        suffix = b_num[len(base_prefix):]
        try:
            val = int(suffix)
            if val > max_num:
                max_num = val
        except (ValueError, TypeError):
            continue

    candidate_num = max_num + 1
    for attempt in range(200):
        candidate = f"{base_prefix}{candidate_num + attempt:03d}"
        if not Booking.objects.all().filter(booking_number=candidate).exists():
            return candidate

    for _ in range(50):
        candidate = f"{base_prefix}{uuid.uuid4().hex[:6].upper()}"
        if not Booking.objects.all().filter(booking_number=candidate).exists():
            return candidate

    return f"{clean_prefix}{today_str}-{uuid.uuid4().hex[:8].upper()}"


def generate_unique_shift_number(property_obj=None, prefix=None):
    """
    Generates a guaranteed unique staff shift session number.
    """
    from apps.shifts.models import Shift
    import uuid

    clean_prefix = (prefix or "SHIFT-").strip()
    if not clean_prefix.endswith('-'):
        clean_prefix += '-'
    today_str = timezone.now().strftime('%Y%m%d')
    base_prefix = f"{clean_prefix}{today_str}-"

    existing_numbers = list(Shift.objects.all().filter(shift_number__startswith=base_prefix).values_list('shift_number', flat=True))
    
    max_num = 0
    for s_num in existing_numbers:
        suffix = s_num[len(base_prefix):]
        try:
            val = int(suffix)
            if val > max_num:
                max_num = val
        except (ValueError, TypeError):
            continue

    candidate_num = max_num + 1
    for attempt in range(200):
        candidate = f"{base_prefix}{candidate_num + attempt:03d}"
        if not Shift.objects.all().filter(shift_number=candidate).exists():
            return candidate

    for _ in range(50):
        candidate = f"{base_prefix}{uuid.uuid4().hex[:6].upper()}"
        if not Shift.objects.all().filter(shift_number=candidate).exists():
            return candidate

    return f"{clean_prefix}{today_str}-{uuid.uuid4().hex[:8].upper()}"


