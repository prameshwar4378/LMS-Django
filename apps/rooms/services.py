import datetime
from django.utils import timezone
from apps.settings_app.models import Settings
from apps.bookings.models import Booking
from apps.stays.models import Stay

def check_room_availability(room, check_in_dt, check_out_dt, exclude_booking_id=None, exclude_stay_id=None, check_cleaning=False):
    """
    Core Room Availability Service (Rule #80).
    Checks room status, active bookings, and active stays with exact datetime logic and turnaround buffer.
    Returns (is_available, error_message).
    """
    settings_obj = Settings.get_settings()
    turnaround_mins = getattr(settings_obj, 'room_turnaround_minutes', 0) or 0
    buffer = datetime.timedelta(minutes=turnaround_mins)

    # 1. Room Active Validation (Rule #10)
    if not room.is_active:
        return False, "This room is currently inactive and cannot be booked."

    # 2. Room Maintenance Validation (Rule #11)
    if room.status == 'MAINTENANCE':
        return False, "This room is currently under maintenance."

    # 3. Room Cleaning Validation for Immediate Check-In (Rule #12)
    if check_cleaning and room.status == 'CLEANING':
        return False, "This room is currently being cleaned and is not available for check-in."

    # Ensure datetimes are timezone aware
    if timezone.is_naive(check_in_dt):
        check_in_dt = timezone.make_aware(check_in_dt)
    if timezone.is_naive(check_out_dt):
        check_out_dt = timezone.make_aware(check_out_dt)

    # 4. Overlap Check with Active Bookings (Rule #13, #14, #16, #17, #18, #19)
    # Excludes CANCELLED, COMPLETED, NO_SHOW
    booking_qs = Booking.objects.filter(
        room=room,
        status__in=['CONFIRMED', 'CHECKED_IN', 'PENDING']
    )
    if exclude_booking_id:
        booking_qs = booking_qs.exclude(pk=exclude_booking_id)

    for b in booking_qs:
        b_in = b.check_in_datetime
        b_out = b.expected_checkout_datetime
        if timezone.is_naive(b_in):
            b_in = timezone.make_aware(b_in)
        if timezone.is_naive(b_out):
            b_out = timezone.make_aware(b_out)

        # Overlap with turnaround buffer: new_check_in < b_out + buffer AND new_check_out > b_in
        if check_in_dt < (b_out + buffer) and check_out_dt > b_in:
            b_in_str = b_in.strftime("%d-%b %I:%M %p")
            b_out_str = b_out.strftime("%d-%b %I:%M %p")
            return False, f"Room {room.room_number} is already booked between {b_in_str} and {b_out_str}."

    # 5. Overlap Check with Active Stays (Rule #16)
    stay_qs = Stay.objects.filter(
        room=room,
        status='CHECKED_IN'
    )
    if exclude_stay_id:
        stay_qs = stay_qs.exclude(pk=exclude_stay_id)

    for s in stay_qs:
        s_in = s.check_in_datetime
        s_out = s.expected_checkout_datetime
        if timezone.is_naive(s_in):
            s_in = timezone.make_aware(s_in)
        if timezone.is_naive(s_out):
            s_out = timezone.make_aware(s_out)

        if check_in_dt < (s_out + buffer) and check_out_dt > s_in:
            s_in_str = s_in.strftime("%d-%b %I:%M %p")
            s_out_str = s_out.strftime("%d-%b %I:%M %p")
            return False, f"Room {room.room_number} is currently occupied by an active stay between {s_in_str} and {s_out_str}."

    return True, None
