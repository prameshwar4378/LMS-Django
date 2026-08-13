import os
import django
import datetime
from django.utils import timezone
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS.settings')
django.setup()

from apps.rooms.models import Room, RoomType
from apps.bookings.models import Booking
from apps.stays.models import Stay
from apps.customers.models import Customer
from apps.settings_app.models import Settings
from apps.rooms.services import check_room_availability
from apps.bookings.services import validate_booking_payload, transition_booking_status
from apps.stays.services import calculate_stay_bill, validate_checkout

def run_tests():
    print("==================================================")
    print("   STRICT 80-RULES VALIDATION & INTEGRITY TESTS")
    print("==================================================")

    # 1. Setup Room & Settings
    settings_obj = Settings.get_settings()
    settings_obj.max_advance_booking_days = 90
    settings_obj.min_stay_duration_hours = 1
    settings_obj.max_receptionist_discount_percent = Decimal('10.00')
    settings_obj.save()

    r_type, _ = RoomType.objects.get_or_create(
        name="Executive Test Suite",
        defaults={'base_price': Decimal('1500.00'), 'max_adults': 2, 'max_children': 1}
    )
    room, _ = Room.objects.get_or_create(
        room_number="999",
        defaults={'room_type': r_type, 'floor': 9, 'is_active': True, 'status': 'AVAILABLE'}
    )
    room.is_active = True
    room.status = 'AVAILABLE'
    room.save()

    cust, _ = Customer.objects.get_or_create(
        mobile="9999999999",
        defaults={'first_name': "Test", 'last_name': "Guest"}
    )

    now_tz = timezone.now()

    # TEST 1: Past Check-In Rejection for Advance Booking (Rule #5)
    past_in = (now_tz - datetime.timedelta(hours=5)).strftime('%Y-%m-%d')
    past_out = (now_tz + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
    data_past = {
        'room': room.id,
        'check_in_date': past_in,
        'check_in_time': '12:00',
        'expected_checkout_date': past_out,
        'expected_checkout_time': '11:00',
        'adults': 1,
        'children': 0,
        'room_rate': 1500.00
    }
    val, err = validate_booking_payload(data_past, is_walkin=False)
    assert err is not None and 'check_in_date' in err, f"Expected past check-in error, got: {err}"
    print("[PASS] Test 1 Passed: Past check-in datetime correctly rejected for advance booking.")

    # TEST 2: Future Booking Beyond Max Advance Days (> 90 days) (Rule #8)
    future_far = (now_tz + datetime.timedelta(days=100)).strftime('%Y-%m-%d')
    future_far_out = (now_tz + datetime.timedelta(days=102)).strftime('%Y-%m-%d')
    data_far = {
        'room': room.id,
        'check_in_date': future_far,
        'check_in_time': '12:00',
        'expected_checkout_date': future_far_out,
        'expected_checkout_time': '11:00',
        'adults': 1,
        'children': 0,
        'room_rate': 1500.00
    }
    val, err = validate_booking_payload(data_far)
    assert err is not None and 'check_in_date' in err, f"Expected max advance booking days error, got: {err}"
    print("[PASS] Test 2 Passed: Booking beyond 90 days advance limit correctly rejected.")

    # TEST 3: Room Capacity Validation (Rule #27, #28)
    data_capacity = {
        'room': room.id,
        'check_in_date': (now_tz + datetime.timedelta(days=2)).strftime('%Y-%m-%d'),
        'check_in_time': '12:00',
        'expected_checkout_date': (now_tz + datetime.timedelta(days=3)).strftime('%Y-%m-%d'),
        'expected_checkout_time': '11:00',
        'adults': 5, # Exceeds max_adults=2
        'children': 0,
        'room_rate': 1500.00
    }
    val, err = validate_booking_payload(data_capacity)
    assert err is not None and 'adults' in err, f"Expected capacity error, got: {err}"
    print("[PASS] Test 3 Passed: Guest count exceeding room capacity correctly rejected.")

    # TEST 4: Create Valid Booking #1 (Rule #76)
    in_d1 = (now_tz + datetime.timedelta(days=5)).date()
    out_d1 = (now_tz + datetime.timedelta(days=7)).date()
    booking1 = Booking.objects.create(
        booking_number="TEST-BK-001",
        customer=cust,
        room=room,
        check_in_date=in_d1,
        check_in_time=datetime.time(12, 0),
        expected_checkout_date=out_d1,
        expected_checkout_time=datetime.time(11, 0),
        adults=2,
        children=0,
        room_rate=Decimal('1500.00'),
        status='CONFIRMED'
    )
    print(f"[PASS] Test 4 Passed: Booking #1 created ({in_d1} to {out_d1}).")

    # TEST 5: Overlapping Booking Conflict Rejection (Rule #13, #14)
    # Attempt booking overlapping from day 6 to day 8
    in_d2 = (now_tz + datetime.timedelta(days=6)).date()
    out_d2 = (now_tz + datetime.timedelta(days=8)).date()
    data_overlap = {
        'room': room.id,
        'check_in_date': in_d2.strftime('%Y-%m-%d'),
        'check_in_time': '12:00',
        'expected_checkout_date': out_d2.strftime('%Y-%m-%d'),
        'expected_checkout_time': '11:00',
        'adults': 1,
        'children': 0,
        'room_rate': 1500.00
    }
    val, err = validate_booking_payload(data_overlap)
    assert err is not None and 'room' in err, f"Expected overlap conflict error, got: {err}"
    print("[PASS] Test 5 Passed: Overlapping room booking conflict correctly rejected.")

    # TEST 6: Back-to-back Booking Allowed (Rule #15)
    # Booking starting exactly when Booking #1 ends (day 7 11:00 AM)
    in_d3 = (now_tz + datetime.timedelta(days=7)).date()
    out_d3 = (now_tz + datetime.timedelta(days=9)).date()
    data_back2back = {
        'room': room.id,
        'check_in_date': in_d3.strftime('%Y-%m-%d'),
        'check_in_time': '11:00',
        'expected_checkout_date': out_d3.strftime('%Y-%m-%d'),
        'expected_checkout_time': '11:00',
        'adults': 1,
        'children': 0,
        'room_rate': 1500.00
    }
    val, err = validate_booking_payload(data_back2back)
    assert err is None, f"Expected back-to-back booking allowed, got error: {err}"
    print("[PASS] Test 6 Passed: Non-overlapping back-to-back booking correctly allowed.")

    # TEST 7: Room Maintenance Block (Rule #11)
    room.status = 'MAINTENANCE'
    room.save()
    val, err = validate_booking_payload(data_back2back)
    assert err is not None and 'room' in err, f"Expected maintenance block error, got: {err}"
    print("[PASS] Test 7 Passed: Room under maintenance correctly blocked from booking.")

    # Cleanup Test Objects
    booking1.delete()
    room.delete()
    r_type.delete()

    print("\n==================================================")
    print(" ALL STRICT VALIDATION TESTS PASSED 100% CLEANLY!")
    print("==================================================")

if __name__ == '__main__':
    run_tests()
