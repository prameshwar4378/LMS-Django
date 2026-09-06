from decimal import Decimal
from django.db.models import Sum
from django.utils import timezone
from .models import Shift, ShiftDenomination, ShiftExpense, ShiftCashAdjustment, ShiftHandover, ShiftAuditLog
from apps.billing.models import Payment

def get_active_shift_for_user(user, auto_create_in_single_mode=False):
    """
    Returns the currently active open shift for a given user, or None.
    If hotel operates in SINGLE_OWNER mode, shifts are completely bypassed (returns None).
    If hotel operates in standard SHIFT_WISE mode, returns the user's active open shift.
    """
    if not user or not user.is_authenticated:
        return None

    # Check property operational mode
    user_prop = getattr(user, 'property', None)
    if user_prop and hasattr(user_prop, 'is_single_owner') and user_prop.is_single_owner:
        return None

    from apps.settings_app.models import Settings
    sett = Settings.get_settings(prop=user_prop)
    if getattr(sett, 'shift_operation_mode', None) == 'SINGLE_OPERATOR':
        return None

    # Check for user's directly active open shift in standard SHIFT_WISE mode
    active = Shift.objects.filter(user=user, status__in=[Shift.Status.OPEN, Shift.Status.CLOSING]).first()
    if active:
        return active

    return None

def get_suggested_opening_balance():
    """
    Retrieves the closing physical cash balance of the most recently closed shift.
    """
    last_closed = Shift.objects.filter(status=Shift.Status.CLOSED).order_by('-closed_at', '-id').first()
    if last_closed:
        return float(last_closed.actual_cash if last_closed.actual_cash is not None else last_closed.expected_cash)
    return 0.00

def calculate_shift_financials(shift):
    """
    Calculates physical cash vs digital collections, expenses, adjustments, and exact expected cash.
    Expected Cash = Opening Cash + Cash Payments + Cash Added - Cash Refunds - Cash Expenses - Cash Removed
    Digital Payments (UPI, Card, Bank Transfer) are tracked separately and DO NOT affect physical cash.
    """
    opening_cash = Decimal(str(shift.opening_balance or 0))

    # Payments linked to this shift
    payments = Payment.objects.filter(shift=shift)

    # Positive Cash Receipts
    cash_in = payments.filter(payment_method='CASH', amount__gt=0).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    # Cash Refunds (negative amount)
    cash_out_refunds = payments.filter(payment_method='CASH', amount__lt=0).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    cash_refunds = abs(cash_out_refunds)

    # Digital Collections (Informational only - do NOT increase physical drawer cash)
    upi_in = payments.filter(payment_method='UPI').aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    card_in = payments.filter(payment_method='CARD').aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    bank_in = payments.filter(payment_method='BANK_TRANSFER').aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    other_in = payments.filter(payment_method='OTHER').aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    total_collections = cash_in + upi_in + card_in + bank_in + other_in - cash_refunds

    # Cash Expenses paid out of the till
    expenses_total = ShiftExpense.objects.filter(shift=shift).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    # Cash Adjustments (Floats Added or Removed / Bank Drops)
    cash_added = ShiftCashAdjustment.objects.filter(shift=shift, adjustment_type=ShiftCashAdjustment.AdjustmentType.ADD_CASH).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    cash_removed = ShiftCashAdjustment.objects.filter(shift=shift, adjustment_type=ShiftCashAdjustment.AdjustmentType.REMOVE_CASH).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    # Cash Handovers Given (Physical cash handed over to another cashier/shift)
    cash_handed_over = ShiftHandover.objects.filter(
        from_shift=shift
    ).exclude(status=ShiftHandover.Status.REJECTED).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    # Cash Handovers Received Mid-Shift (strictly excluding opening handover already accounted for in opening_balance)
    mid_handovers_qs = ShiftHandover.objects.filter(
        to_shift=shift,
        status=ShiftHandover.Status.ACCEPTED,
        is_opening_handover=False
    )
    # Extra robustness: if opening notes indicate shift was opened via handover, exclude matching opening float
    if shift.opening_notes and 'Opened via accepted handover' in shift.opening_notes:
        mid_handovers_qs = mid_handovers_qs.exclude(amount=shift.opening_balance)

    cash_handover_received = mid_handovers_qs.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    # EXPECTED PHYSICAL CASH FORMULA
    expected_cash = opening_cash + cash_in + cash_added + cash_handover_received - cash_refunds - expenses_total - cash_removed - cash_handed_over

    # Actual cash counted
    actual_cash = shift.actual_cash
    if actual_cash is not None:
        actual_cash_dec = Decimal(str(actual_cash))
        difference = actual_cash_dec - expected_cash
    else:
        actual_cash_dec = None
        difference = Decimal('0.00')

    return {
        'opening_cash': float(opening_cash),
        'cash_collections': float(cash_in),
        'cash_refunds': float(cash_refunds),
        'upi_collections': float(upi_in),
        'card_collections': float(card_in),
        'bank_collections': float(bank_in),
        'other_collections': float(other_in),
        'total_collections': float(total_collections),
        'cash_expenses': float(expenses_total),
        'cash_added': float(cash_added),
        'cash_removed': float(cash_removed),
        'cash_handed_over': float(cash_handed_over),
        'cash_handover_received': float(cash_handover_received),
        'expected_cash': float(expected_cash),
        'actual_cash': float(actual_cash_dec) if actual_cash_dec is not None else None,
        'cash_difference': float(difference),
        'is_reconciled': bool(actual_cash_dec is not None and difference == Decimal('0.00')),
        'has_discrepancy': bool(actual_cash_dec is not None and difference != Decimal('0.00')),
        'discrepancy_type': 'EXCESS' if difference > 0 else ('SHORTAGE' if difference < 0 else 'EXACT') if actual_cash_dec is not None else 'UNCOUNTED'
    }

def log_shift_action(shift, user, action, description, metadata=None):
    """
    Records an immutable audit event for the shift.
    """
    return ShiftAuditLog.objects.create(
        shift=shift,
        user=user if user and user.is_authenticated else None,
        action=action,
        description=description,
        metadata=metadata or {},
        created_at=timezone.now()
    )

def calculate_shift_operational_metrics(shift):
    """
    Computes operational productivity & room metrics during the active shift window.
    """
    from apps.stays.models import Stay
    from apps.bookings.models import Booking
    from django.db.models import Q

    start_time = shift.opened_at
    end_time = shift.closed_at or timezone.now()

    # Stays checked in during this shift window
    checkins_qs = Stay.objects.filter(
        Q(created_at__gte=start_time, created_at__lte=end_time) |
        Q(created_by=shift.user, created_at__gte=start_time, created_at__lte=end_time)
    ).distinct()
    total_checkins = checkins_qs.count()

    # Stays checked out during this shift window
    checkouts_qs = Stay.objects.filter(
        status=Stay.Status.CHECKED_OUT,
        updated_at__gte=start_time,
        updated_at__lte=end_time
    )
    total_checkouts = checkouts_qs.count()

    # New Bookings created during this shift window
    bookings_qs = Booking.objects.filter(
        created_at__gte=start_time,
        created_at__lte=end_time
    )
    total_bookings = bookings_qs.count()

    # Room turnover / cleaning requests generated (checkouts trigger room turnover)
    room_turnovers = total_checkouts

    # Room revenue collected in this shift
    payments_qs = Payment.objects.filter(shift=shift)
    total_revenue = payments_qs.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    # Average Daily Rate (ADR) generated from active checkins
    total_room_rate = checkins_qs.aggregate(total=Sum('room_rate'))['total'] or Decimal('0.00')
    adr = float(total_room_rate / total_checkins) if total_checkins > 0 else 0.0

    return {
        'total_checkins': total_checkins,
        'total_checkouts': total_checkouts,
        'total_bookings': total_bookings,
        'room_turnovers': room_turnovers,
        'total_revenue': float(total_revenue),
        'total_room_rate': float(total_room_rate),
        'adr': round(adr, 2)
    }
