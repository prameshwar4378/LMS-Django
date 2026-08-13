import datetime
from django.utils import timezone
from decimal import Decimal
from apps.settings_app.models import Settings
from apps.billing.models import ExtraCharge, Payment

def calculate_stay_bill(stay, actual_checkout_dt=None):
    """
    Core Stay Billing Service (Rules #53, #54, #55, #62, #65, #80).
    Recalculates stay duration, room charges, extra charges, discounts, GST, and final balance.
    Always executed on backend.
    """
    settings_obj = Settings.get_settings()

    # Determine check-in and checkout datetimes
    in_dt = stay.check_in_datetime
    if timezone.is_naive(in_dt):
        in_dt = timezone.make_aware(in_dt)

    if actual_checkout_dt:
        out_dt = actual_checkout_dt
    else:
        out_dt = timezone.now()

    if timezone.is_naive(out_dt):
        out_dt = timezone.make_aware(out_dt)

    # 1. Calculate Nights & Base Room Charge
    stay_days = max(1, (out_dt.date() - in_dt.date()).days)
    room_rate = Decimal(str(stay.room_rate or stay.room.base_price or 0))
    room_subtotal = room_rate * Decimal(stay_days)

    # Late Checkout Tier rules (Rule #54)
    expected_out = stay.expected_checkout_datetime
    if timezone.is_naive(expected_out):
        expected_out = timezone.make_aware(expected_out)

    late_fee = Decimal('0.00')
    if out_dt > expected_out:
        late_hours = (out_dt - expected_out).total_seconds() / 3600.0
        if late_hours <= 2.0:
            late_fee = Decimal('200.00')
        elif late_hours <= 5.0:
            late_fee = Decimal('500.00')
        else:
            late_fee = room_rate

    total_room_charge = room_subtotal + late_fee

    # 2. Calculate Extra Charges (Rule #62: Django calculates quantity * unit_price)
    extra_charges = ExtraCharge.objects.filter(stay=stay)
    total_extra = Decimal('0.00')
    for ec in extra_charges:
        item_amount = Decimal(str(ec.quantity)) * Decimal(str(ec.unit_price))
        total_extra += item_amount

    gross_subtotal = total_room_charge + total_extra

    # 3. Calculate Discount (Rules #31, #32)
    discount_amount = Decimal('0.00')
    disc_val = Decimal(str(stay.discount_value or 0))
    if stay.discount_type == 'PERCENTAGE':
        discount_amount = (gross_subtotal * disc_val) / Decimal('100.00')
    elif stay.discount_type == 'FIXED':
        discount_amount = min(gross_subtotal, disc_val)

    taxable_amount = max(Decimal('0.00'), gross_subtotal - discount_amount)

    # 4. Calculate GST (Rule #65: Configurable, backend calculated)
    gst_amount = Decimal('0.00')
    if settings_obj.tax_enabled:
        tax_pct = Decimal(str(settings_obj.tax_percentage or 12.00))
        gst_amount = (taxable_amount * tax_pct) / Decimal('100.00')

    grand_total = taxable_amount + gst_amount

    # 5. Calculate Previous Payments & Balance (Rules #56, #57, #58)
    payments = Payment.objects.filter(stay=stay)
    total_paid = Decimal('0.00')
    for p in payments:
        total_paid += Decimal(str(p.amount))

    # Also include booking advance deposit if present and not logged yet
    if stay.booking and stay.booking.advance_amount and total_paid == Decimal('0.00'):
        total_paid += Decimal(str(stay.booking.advance_amount))

    balance = grand_total - total_paid

    return {
        'stay_days': stay_days,
        'room_rate': room_rate,
        'room_subtotal': room_subtotal,
        'late_fee': late_fee,
        'total_room_charge': total_room_charge,
        'total_extra_charges': total_extra,
        'gross_subtotal': gross_subtotal,
        'discount_amount': discount_amount,
        'taxable_amount': taxable_amount,
        'gst_amount': gst_amount,
        'grand_total': grand_total,
        'total_paid': total_paid,
        'balance': balance,
    }

def validate_checkout(stay, actual_checkout_dt):
    """
    Validates checkout rules prior to checkout completion (Rules #49, #50, #51, #52, #56, #60).
    Returns (is_valid, bill_details, error_message).
    """
    settings_obj = Settings.get_settings()

    # Rule #60: Prevent duplicate checkout
    if stay.status == 'CHECKED_OUT':
        return False, None, "This stay has already been checked out."

    # Rule #49: Stay must be CHECKED_IN
    if stay.status != 'CHECKED_IN':
        return False, None, "This stay is not currently active."

    in_dt = stay.check_in_datetime
    if timezone.is_naive(in_dt):
        in_dt = timezone.make_aware(in_dt)

    if timezone.is_naive(actual_checkout_dt):
        actual_checkout_dt = timezone.make_aware(actual_checkout_dt)

    # Rule #51 & #52: Checkout > Check-in
    if actual_checkout_dt <= in_dt:
        return False, None, "Checkout time must be later than check-in time."

    # Recalculate Bill
    bill = calculate_stay_bill(stay, actual_checkout_dt)

    # Rule #56: Balance policy validation
    allow_balance = getattr(settings_obj, 'allow_checkout_with_balance', True)
    if not allow_balance and bill['balance'] > Decimal('0.01'):
        return False, bill, f"Outstanding balance of ₹{bill['balance']:.2f} must be fully paid before checkout."

    return True, bill, None
