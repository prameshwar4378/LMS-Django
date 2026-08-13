from decimal import Decimal
import datetime
import math
from apps.settings_app.models import Settings

def calculate_stay_bill(stay):
    """
    Central calculation service for a Stay record using DateTime.
    Returns calculated values for billing breakdown.
    Django backend is the SINGLE SOURCE OF TRUTH.
    """
    dt_in = stay.check_in_datetime
    dt_out = stay.actual_checkout_datetime if stay.status == 'CHECKED_OUT' else stay.expected_checkout_datetime
    
    # Calculate stay duration in hours
    if dt_out and dt_in:
        delta_sec = (dt_out - dt_in).total_seconds()
        hours = max(0, delta_sec / 3600.0)
        # Standard Lodge 24-hour cycle (e.g. 12:00 PM to 11:00 AM next day = ~23 hours = 1 day)
        if hours <= 0:
            room_days = 1
        else:
            # Full 24h slots or fraction
            room_days = max(1, math.ceil((hours - 2.0) / 24.0)) if hours > 2 else 1
    else:
        room_days = 1

    room_rate = Decimal(str(stay.room_rate or 0))
    room_amount = room_days * room_rate

    # 2. Extra charges sum
    extra_charges = stay.extra_charges.all()
    extra_charges_total = sum((Decimal(str(item.amount or 0)) for item in extra_charges), Decimal('0.00'))

    # 3. Subtotal
    subtotal = room_amount + extra_charges_total

    # 4. Discount calculation
    discount_val = Decimal(str(stay.discount_value or 0))
    if stay.discount_type == 'PERCENTAGE':
        discount_amount = (subtotal * discount_val) / Decimal('100.00')
    else: # FIXED
        discount_amount = discount_val

    # Discount cannot exceed subtotal
    discount_amount = min(discount_amount, subtotal)
    after_discount = subtotal - discount_amount

    # 5. Tax calculation based on Settings
    settings_obj = Settings.get_settings()
    tax_enabled = settings_obj.tax_enabled
    tax_percentage = Decimal(str(settings_obj.tax_percentage or 0)) if tax_enabled else Decimal('0.00')
    
    if tax_enabled and tax_percentage > 0:
        tax_amount = (after_discount * tax_percentage) / Decimal('100.00')
    else:
        tax_amount = Decimal('0.00')

    # 6. Grand total
    grand_total = after_discount + tax_amount

    # 7. Payments total
    payments = stay.payments.all()
    total_paid = sum((Decimal(str(p.amount or 0)) for p in payments), Decimal('0.00'))

    # Advance payment check from booking if applicable
    advance_amount = Decimal('0.00')
    if stay.booking and stay.booking.advance_amount:
        advance_amount = Decimal(str(stay.booking.advance_amount))

    balance = grand_total - total_paid

    return {
        'stay_id': stay.id,
        'stay_number': stay.stay_number,
        'room_number': stay.room.room_number,
        'room_type': stay.room.room_type.name,
        'primary_customer_name': stay.primary_customer.full_name,
        'check_in_datetime': dt_in.strftime('%Y-%m-%d %H:%M') if dt_in else None,
        'checkout_datetime': dt_out.strftime('%Y-%m-%d %H:%M') if dt_out else None,
        'room_days': room_days,
        'room_rate': float(room_rate),
        'room_amount': float(room_amount),
        'extra_charges_total': float(extra_charges_total),
        'subtotal': float(subtotal),
        'discount_type': stay.discount_type,
        'discount_value': float(discount_val),
        'discount_reason': stay.discount_reason or '',
        'discount_amount': float(discount_amount),
        'tax_enabled': tax_enabled,
        'tax_percentage': float(tax_percentage),
        'tax_amount': float(tax_amount),
        'grand_total': float(grand_total),
        'advance_amount': float(advance_amount),
        'total_paid': float(total_paid),
        'balance': float(balance),
    }
