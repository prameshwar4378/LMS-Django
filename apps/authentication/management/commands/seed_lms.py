from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from apps.rooms.models import RoomType, Room
from apps.customers.models import Customer
from apps.bookings.models import Booking
from apps.stays.models import Stay, StayGuest
from apps.billing.models import ChargeType, ExtraCharge, Payment, Invoice
from apps.settings_app.models import Settings
import datetime

User = get_user_model()

class Command(BaseCommand):
    help = 'Seeds initial data for Lodge Management System'

    def handle(self, *args, **options):
        self.stdout.write('Seeding LMS initial data...')

        # 1. Users
        admin_user, created = User.objects.get_or_create(
            username='admin',
            defaults={
                'email': 'admin@lodge.com',
                'first_name': 'Super',
                'last_name': 'Admin',
                'role': User.Role.SUPER_ADMIN,
                'is_staff': True,
                'is_superuser': True
            }
        )
        if created:
            admin_user.set_password('admin123')
            admin_user.save()
            self.stdout.write('  Created user: admin / admin123')

        mgr_user, created = User.objects.get_or_create(
            username='manager',
            defaults={
                'email': 'manager@lodge.com',
                'first_name': 'Rajesh',
                'last_name': 'Sharma',
                'role': User.Role.MANAGER,
            }
        )
        if created:
            mgr_user.set_password('manager123')
            mgr_user.save()

        rec_user, created = User.objects.get_or_create(
            username='receptionist',
            defaults={
                'email': 'reception@lodge.com',
                'first_name': 'Priya',
                'last_name': 'Verma',
                'role': User.Role.RECEPTIONIST,
            }
        )
        if created:
            rec_user.set_password('receptionist123')
            rec_user.save()

        # 2. Settings
        settings_obj = Settings.get_settings()
        settings_obj.lodge_name = "Grand Royal Lodge & Suites"
        settings_obj.address = "742 Evergreen Avenue, Near Railway Station, City"
        settings_obj.phone = "+91 98765 43210"
        settings_obj.email = "contact@grandroyallodge.com"
        settings_obj.gst_number = "27AAAAA1234B1Z5"
        settings_obj.tax_enabled = True
        settings_obj.tax_percentage = 12.00
        settings_obj.default_checkin_time = datetime.time(12, 0)
        settings_obj.default_checkout_time = datetime.time(11, 0)
        settings_obj.save()

        # 3. Room Types
        rt_deluxe, _ = RoomType.objects.get_or_create(
            name='Deluxe AC Room',
            defaults={
                'description': 'Spacious AC room with King size bed and city view',
                'base_price': 1800.00,
                'max_adults': 2,
                'max_children': 2,
                'amenities': 'AC, Smart TV, WiFi, Geyser, Attached Bathroom'
            }
        )

        rt_suite, _ = RoomType.objects.get_or_create(
            name='Executive Suite',
            defaults={
                'description': 'Luxury suite with living room, mini fridge and premium bath amenities',
                'base_price': 3500.00,
                'max_adults': 3,
                'max_children': 2,
                'amenities': 'AC, Smart TV, WiFi, Mini Fridge, Bathtub, Sofa, Breakfast Included'
            }
        )

        rt_std, _ = RoomType.objects.get_or_create(
            name='Standard Non-AC Room',
            defaults={
                'description': 'Comfortable budget room with queen bed and fan',
                'base_price': 1200.00,
                'max_adults': 2,
                'max_children': 1,
                'amenities': 'TV, Fan, Attached Bathroom, WiFi'
            }
        )

        # 4. Rooms
        rooms_data = [
            ('101', rt_deluxe, '1st Floor', Room.Status.OCCUPIED),
            ('102', rt_deluxe, '1st Floor', Room.Status.AVAILABLE),
            ('103', rt_deluxe, '1st Floor', Room.Status.RESERVED),
            ('201', rt_suite, '2nd Floor', Room.Status.OCCUPIED),
            ('202', rt_suite, '2nd Floor', Room.Status.AVAILABLE),
            ('301', rt_std, '3rd Floor', Room.Status.AVAILABLE),
            ('302', rt_std, '3rd Floor', Room.Status.CLEANING),
            ('303', rt_std, '3rd Floor', Room.Status.MAINTENANCE),
        ]

        rooms_dict = {}
        for r_num, r_type, floor, status in rooms_data:
            r, _ = Room.objects.get_or_create(
                room_number=r_num,
                defaults={
                    'room_type': r_type,
                    'floor': floor,
                    'status': status,
                    'description': f'{r_type.name} on {floor}'
                }
            )
            rooms_dict[r_num] = r

        # 5. Charge Types
        charges_master = [
            ('Extra Bed', 500.00, 'Rollaway extra bed with mattress'),
            ('Breakfast', 150.00, 'Complimentary buffet breakfast per person'),
            ('Lunch', 250.00, 'Thali / Buffet lunch per person'),
            ('Dinner', 300.00, 'Thali / Buffet dinner per person'),
            ('Laundry', 100.00, 'Washing and ironing service'),
            ('Water Bottle', 40.00, '1 Litre packaged mineral water'),
            ('Airport Transfer', 1200.00, 'Pickup or drop service'),
        ]
        for c_name, c_price, c_desc in charges_master:
            ChargeType.objects.get_or_create(
                name=c_name,
                defaults={'default_price': c_price, 'description': c_desc}
            )

        # 6. Sample Customers
        cust1, _ = Customer.objects.get_or_create(
            mobile='9823012345',
            defaults={
                'first_name': 'Rameshwar',
                'last_name': 'Pawar',
                'email': 'rameshwar.pawar@example.com',
                'gender': Customer.Gender.MALE,
                'address': 'Flat 402, Green Park, Shivajinagar',
                'city': 'Pune',
                'state': 'Maharashtra',
                'id_type': Customer.IDType.AADHAAR,
                'id_number': '1234-5678-9012'
            }
        )

        cust2, _ = Customer.objects.get_or_create(
            mobile='9890123456',
            defaults={
                'first_name': 'Sunita',
                'last_name': 'Kulkarni',
                'email': 'sunita.k@example.com',
                'gender': Customer.Gender.FEMALE,
                'address': '22/B MG Road',
                'city': 'Mumbai',
                'state': 'Maharashtra',
                'id_type': Customer.IDType.PAN,
                'id_number': 'ABCDE1234F'
            }
        )

        cust3, _ = Customer.objects.get_or_create(
            mobile='9970987654',
            defaults={
                'first_name': 'Amit',
                'last_name': 'Deshmukh',
                'email': 'amit.d@example.com',
                'gender': Customer.Gender.MALE,
                'address': 'Opposite City Center Mall',
                'city': 'Nagpur',
                'state': 'Maharashtra',
                'id_type': Customer.IDType.DRIVING_LICENCE,
                'id_number': 'MH31 20210045'
            }
        )

        # 7. Sample Booking & Stays
        today = datetime.date.today()
        yesterday = today - datetime.timedelta(days=1)
        two_days_later = today + datetime.timedelta(days=2)
        three_days_later = today + datetime.timedelta(days=3)

        # Active Stay 1 in Room 101
        stay1, created = Stay.objects.get_or_create(
            stay_number='STAY-20260809-001',
            defaults={
                'room': rooms_dict['101'],
                'primary_customer': cust1,
                'check_in_date': yesterday,
                'check_in_time': datetime.time(12, 30),
                'expected_checkout_date': two_days_later,
                'expected_checkout_time': datetime.time(11, 0),
                'adults': 2,
                'children': 1,
                'room_rate': 1800.00,
                'discount_type': 'PERCENTAGE',
                'discount_value': 10.00,
                'discount_reason': 'Regular Customer',
                'status': Stay.Status.CHECKED_IN,
                'created_by': rec_user
            }
        )
        if created:
            # Add Guest
            StayGuest.objects.create(
                stay=stay1,
                guest_name='Mauli Pawar',
                age=28,
                gender='Female',
                relationship='Spouse'
            )
            # Add Extra Charges
            c_bed = ChargeType.objects.get(name='Extra Bed')
            c_breakfast = ChargeType.objects.get(name='Breakfast')
            ExtraCharge.objects.create(
                stay=stay1,
                charge_type=c_bed,
                description='Extra Bed',
                quantity=1,
                unit_price=500.00,
                amount=500.00,
                created_by=rec_user
            )
            ExtraCharge.objects.create(
                stay=stay1,
                charge_type=c_breakfast,
                description='Breakfast Buffet',
                quantity=2,
                unit_price=150.00,
                amount=300.00,
                created_by=rec_user
            )
            # Add Advance Payment
            Payment.objects.create(
                payment_number='PAY-20260809-001',
                stay=stay1,
                amount=1000.00,
                payment_method='UPI',
                transaction_reference='UPI/1234567890',
                received_by=rec_user,
                notes='Advance payment during check-in'
            )

        # Active Stay 2 in Room 201
        stay2, created = Stay.objects.get_or_create(
            stay_number='STAY-20260809-002',
            defaults={
                'room': rooms_dict['201'],
                'primary_customer': cust2,
                'check_in_date': today,
                'check_in_time': datetime.time(14, 0),
                'expected_checkout_date': three_days_later,
                'expected_checkout_time': datetime.time(11, 0),
                'adults': 2,
                'children': 0,
                'room_rate': 3500.00,
                'discount_type': 'FIXED',
                'discount_value': 500.00,
                'discount_reason': 'Corporate Partner',
                'status': Stay.Status.CHECKED_IN,
                'created_by': rec_user
            }
        )
        if created:
            Payment.objects.create(
                payment_number='PAY-20260809-002',
                stay=stay2,
                amount=3000.00,
                payment_method='CARD',
                transaction_reference='POS-TXN-98765',
                received_by=rec_user,
                notes='Partial payment on check-in'
            )

        # Advance Booking for Room 103
        Booking.objects.get_or_create(
            booking_number='BK-20260809-001',
            defaults={
                'customer': cust3,
                'room': rooms_dict['103'],
                'check_in_date': today,
                'check_in_time': datetime.time(12, 0),
                'expected_checkout_date': two_days_later,
                'expected_checkout_time': datetime.time(11, 0),
                'adults': 2,
                'children': 0,
                'room_rate': 1800.00,
                'advance_amount': 500.00,
                'status': Booking.Status.CONFIRMED,
                'created_by': rec_user,
                'notes': 'Guest requested upper floor if available'
            }
        )

        self.stdout.write(self.style.SUCCESS('Successfully seeded LMS data!'))
