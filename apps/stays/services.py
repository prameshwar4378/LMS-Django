import datetime
from django.utils import timezone
from decimal import Decimal
from apps.settings_app.models import Settings
from apps.billing.models import ExtraCharge, Payment

from apps.billing.services import calculate_stay_bill

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

    # Rule #51 & #52: Checkout Date >= Check-in Date
    if actual_checkout_dt.date() < in_dt.date():
        return False, None, "Checkout date cannot be earlier than check-in date."

    # Recalculate Bill using the actual checkout datetime
    bill = calculate_stay_bill(stay, actual_checkout_dt)

    # Rule #56: Balance policy validation
    allow_balance = getattr(settings_obj, 'allow_checkout_with_balance', True)
    if not allow_balance and bill['balance'] > Decimal('0.01'):
        return False, bill, f"Outstanding balance of ₹{bill['balance']:.2f} must be fully paid before checkout."

    return True, bill, None
