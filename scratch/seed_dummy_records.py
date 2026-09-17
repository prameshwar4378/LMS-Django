import os
import sys
import django
from datetime import date, time, timedelta
from decimal import Decimal
import random

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS.settings')
django.setup()

from django.contrib.auth import get_user_model
from apps.settings_app.models import Property, Settings
from apps.rooms.models import RoomType, Room
from apps.customers.models import Customer
from apps.stays.models import Stay
from apps.bookings.models import Booking
from apps.billing.models import Payment, Invoice
from apps.billing.services import generate_unique_stay_number, generate_unique_payment_number, generate_unique_invoice_number

User = get_user_model()
admin_user = User.objects.filter(is_superuser=True).first() or User.objects.first()

print("--- CREATING DUMMY RECORDS ---")

# 1. Property (Hotel)
prop, created = Property.objects.get_or_create(
    code="GRAND-01",
    defaults={
        "name": "Grand Royale Palace & Resort",
        "legal_entity_name": "Royale Hospitality Pvt Ltd",
        "city": "Bengaluru",
        "state": "Karnataka",
        "country": "India",
        "address": "88 Residency Road, Richmond Town",
        "phone": "080-45678900",
        "email": "frontdesk@grandroyale.com",
        "is_active": True,
    }
)
print(f"Hotel Property: {prop.name} (Code: {prop.code})")

# Ensure property settings exist
settings_obj = Settings.get_settings(prop)

# 2. Room Types
room_types_data = [
    {"name": "Standard Classic", "code": "STD", "base_price": Decimal("1800.00"), "capacity": 2},
    {"name": "Deluxe King", "code": "DLX", "base_price": Decimal("2800.00"), "capacity": 2},
    {"name": "Executive Club Suite", "code": "STE", "base_price": Decimal("4500.00"), "capacity": 4},
    {"name": "Presidential Luxury Suite", "code": "PRS", "base_price": Decimal("8500.00"), "capacity": 4},
]
created_room_types = {}
for rt_data in room_types_data:
    rt, _ = RoomType.objects.get_or_create(
        property=prop,
        code=rt_data["code"],
        defaults={
            "name": rt_data["name"],
            "base_price": rt_data["base_price"],
            "capacity": rt_data["capacity"],
            "description": f"Spacious {rt_data['name']} equipped with high-speed WiFi, modern climate control & 24/7 room service."
        }
    )
    created_room_types[rt_data["code"]] = rt

print(f"Room Types: {len(created_room_types)} ready")

# 3. Rooms
rooms_data = [
    # 1st floor - Standard
    {"number": "101", "floor": "1", "type": "STD", "status": "AVAILABLE"},
    {"number": "102", "floor": "1", "type": "STD", "status": "OCCUPIED"},
    {"number": "103", "floor": "1", "type": "STD", "status": "AVAILABLE"},
    # 2nd floor - Deluxe
    {"number": "201", "floor": "2", "type": "DLX", "status": "OCCUPIED"},
    {"number": "202", "floor": "2", "type": "DLX", "status": "AVAILABLE"},
    {"number": "203", "floor": "2", "type": "DLX", "status": "RESERVED"},
    # 3rd floor - Suite
    {"number": "301", "floor": "3", "type": "STE", "status": "OCCUPIED"},
    {"number": "302", "floor": "3", "type": "STE", "status": "AVAILABLE"},
    # 4th floor - Presidential
    {"number": "401", "floor": "4", "type": "PRS", "status": "AVAILABLE"},
]

created_rooms = {}
for r_data in rooms_data:
    rt = created_room_types[r_data["type"]]
    room, _ = Room.objects.get_or_create(
        property=prop,
        room_number=r_data["number"],
        defaults={
            "floor": r_data["floor"],
            "room_type": rt,
            "base_tariff": rt.base_price,
            "status": r_data["status"],
            "is_active": True,
        }
    )
    created_rooms[r_data["number"]] = room

print(f"Rooms: {len(created_rooms)} rooms verified/created")

# 4. Customers
customers_data = [
    {
        "first_name": "Aarav", "last_name": "Sharma", "mobile": "9811122334",
        "email": "aarav.sharma@example.com", "address": "12 Indiranagar, Bengaluru",
        "id_type": "Aadhaar", "id_number": "5423-8871-9012", "wallet": Decimal("1500.00")
    },
    {
        "first_name": "Pooja", "last_name": "Iyer", "mobile": "9822233445",
        "email": "pooja.iyer@example.com", "address": "45 Koramangala 4th Block, Bengaluru",
        "id_type": "PAN", "id_number": "BNZPI7845K", "wallet": Decimal("0.00")
    },
    {
        "first_name": "Vikram", "last_name": "Mehta", "mobile": "9833344556",
        "email": "vikram.mehta@example.com", "address": "9 Nariman Point, Mumbai",
        "id_type": "Passport", "id_number": "Z8912345", "wallet": Decimal("3200.00")
    },
    {
        "first_name": "Sneha", "last_name": "Patel", "mobile": "9844455667",
        "email": "sneha.patel@example.com", "address": "77 Ellisbridge, Ahmedabad",
        "id_type": "Driving Licence", "id_number": "GJ-01-2018-09182", "wallet": Decimal("800.00")
    },
    {
        "first_name": "Rohan", "last_name": "Verma", "mobile": "9855566778",
        "email": "rohan.verma@example.com", "address": "33 Civil Lines, Jaipur",
        "id_type": "Aadhaar", "id_number": "6102-9934-1189", "wallet": Decimal("0.00")
    },
]

created_custs = {}
for c_data in customers_data:
    cust, _ = Customer.objects.get_or_create(
        property=prop,
        mobile=c_data["mobile"],
        defaults={
            "first_name": c_data["first_name"],
            "last_name": c_data["last_name"],
            "email": c_data["email"],
            "address": c_data["address"],
            "id_type": c_data["id_type"],
            "id_number": c_data["id_number"],
            "advance_credit": c_data["wallet"],
        }
    )
    created_custs[c_data["mobile"]] = cust

print(f"Customers: {len(created_custs)} customers verified/created")

today = date.today()
yesterday = today - timedelta(days=1)
two_days_ago = today - timedelta(days=2)
tomorrow = today + timedelta(days=1)

# 5. Check-In (Active In-House Stays)
# Stay 1: Aarav Sharma in Room 102
stay1_room = created_rooms["102"]
stay1_cust = created_custs["9811122334"]
stay1 = Stay.objects.filter(property=prop, room=stay1_room, status="CHECKED_IN").first()
if not stay1:
    stay1 = Stay.objects.create(
        property=prop,
        stay_number=generate_unique_stay_number("STY-"),
        room=stay1_room,
        customer=stay1_cust,
        check_in_date=yesterday,
        check_in_time=time(14, 30),
        expected_checkout_date=tomorrow,
        expected_checkout_time=time(11, 0),
        adults=2,
        children=0,
        room_rate=stay1_room.base_tariff,
        status="CHECKED_IN",
        created_by=admin_user,
        notes="Guest requested extra pillows and airport drop assistance."
    )
    stay1_room.status = "OCCUPIED"
    stay1_room.save()
    # Advance payment
    Payment.objects.create(
        property=prop,
        payment_number=generate_unique_payment_number("PAY-"),
        stay=stay1,
        customer=stay1_cust,
        amount=Decimal("1500.00"),
        payment_method="UPI",
        transaction_reference="UPI/2026/891230491",
        received_by=admin_user,
        notes="Advance token deposit via PhonePe"
    )

# Stay 2: Vikram Mehta in Room 201
stay2_room = created_rooms["201"]
stay2_cust = created_custs["9833344556"]
stay2 = Stay.objects.filter(property=prop, room=stay2_room, status="CHECKED_IN").first()
if not stay2:
    stay2 = Stay.objects.create(
        property=prop,
        stay_number=generate_unique_stay_number("STY-"),
        room=stay2_room,
        customer=stay2_cust,
        check_in_date=today,
        check_in_time=time(11, 15),
        expected_checkout_date=today + timedelta(days=2),
        expected_checkout_time=time(11, 0),
        adults=1,
        children=0,
        room_rate=stay2_room.base_tariff,
        status="CHECKED_IN",
        created_by=admin_user,
        notes="VIP Corporate Member - Late arrival confirmed."
    )
    stay2_room.status = "OCCUPIED"
    stay2_room.save()
    # Advance payment
    Payment.objects.create(
        property=prop,
        payment_number=generate_unique_payment_number("PAY-"),
        stay=stay2,
        customer=stay2_cust,
        amount=Decimal("2800.00"),
        payment_method="CARD",
        transaction_reference="TXN-VISA-991244",
        received_by=admin_user,
        notes="Full 1st night card authorization"
    )

# Stay 3: Sneha Patel in Room 301
stay3_room = created_rooms["301"]
stay3_cust = created_custs["9844455667"]
stay3 = Stay.objects.filter(property=prop, room=stay3_room, status="CHECKED_IN").first()
if not stay3:
    stay3 = Stay.objects.create(
        property=prop,
        stay_number=generate_unique_stay_number("STY-"),
        room=stay3_room,
        customer=stay3_cust,
        check_in_date=today,
        check_in_time=time(10, 0),
        expected_checkout_date=tomorrow,
        expected_checkout_time=time(11, 0),
        adults=2,
        children=1,
        room_rate=stay3_room.base_tariff,
        status="CHECKED_IN",
        created_by=admin_user,
        notes="Suite reservation with baby crib."
    )
    stay3_room.status = "OCCUPIED"
    stay3_room.save()
    Payment.objects.create(
        property=prop,
        payment_number=generate_unique_payment_number("PAY-"),
        stay=stay3,
        customer=stay3_cust,
        amount=Decimal("2000.00"),
        payment_method="CASH",
        received_by=admin_user,
        notes="Cash advance collected at reception"
    )

print("Active In-House Stays: 3 created/verified (Rooms 102, 201, 301)")

# 6. Checked-Out Stay (Completed History & Settlement)
checkout_room = created_rooms["101"]
checkout_cust = created_custs["9822233445"]
stay_out = Stay.objects.filter(property=prop, customer=checkout_cust, status="CHECKED_OUT").first()
if not stay_out:
    stay_out = Stay.objects.create(
        property=prop,
        stay_number=generate_unique_stay_number("STY-"),
        room=checkout_room,
        customer=checkout_cust,
        check_in_date=two_days_ago,
        check_in_time=time(12, 0),
        expected_checkout_date=yesterday,
        actual_checkout_date=yesterday,
        actual_checkout_time=time(10, 45),
        adults=1,
        children=0,
        room_rate=checkout_room.base_tariff,
        status="CHECKED_OUT",
        created_by=admin_user,
        notes="Standard business trip - invoice settled in full upon departure."
    )
    # Payments for checked-out stay
    Payment.objects.create(
        property=prop,
        payment_number=generate_unique_payment_number("PAY-"),
        stay=stay_out,
        customer=checkout_cust,
        amount=Decimal("1800.00"),
        payment_method="UPI",
        transaction_reference="UPI/2026/778811902",
        received_by=admin_user,
        notes="Settled bill via GooglePay"
    )

print("Checked-Out Completed Stay: 1 created (Room 101, Pooja Iyer)")

# 7. Advance Booking / Reservation
res_room = created_rooms["203"]
res_cust = created_custs["9855566778"]
booking = Booking.objects.filter(property=prop, customer=res_cust, status="CONFIRMED").first()
if not booking:
    booking = Booking.objects.create(
        property=prop,
        booking_number=f"BKG-{random.randint(10000, 99999)}",
        room=res_room,
        customer=res_cust,
        check_in_date=tomorrow,
        expected_checkout_date=tomorrow + timedelta(days=2),
        adults=2,
        children=0,
        room_rate=res_room.base_tariff,
        advance_amount=Decimal("1000.00"),
        payment_method="UPI",
        status="CONFIRMED",
        created_by=admin_user,
        notes="Advance reservation confirmed. Welcome drinks upon arrival."
    )
    res_room.status = "RESERVED"
    res_room.save()
    Payment.objects.create(
        property=prop,
        payment_number=generate_unique_payment_number("PAY-"),
        customer=res_cust,
        amount=Decimal("1000.00"),
        payment_method="UPI",
        transaction_reference="UPI/BKG/9981247",
        received_by=admin_user,
        notes="Online advance booking deposit"
    )

print("Upcoming Reservation: 1 created (Room 203, Rohan Verma)")

print("\n--- ALL DUMMY RECORDS SUCCESSFULLY CREATED & LINKED ---")
