from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions, status
from django.db.models import Sum, Count, Q
from django.utils import timezone
import datetime
from decimal import Decimal
from apps.rooms.models import Room
from apps.bookings.models import Booking
from apps.stays.models import Stay
from apps.billing.models import Payment, ExtraCharge
from apps.stays.services import calculate_stay_bill

class DashboardReportView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        today = datetime.date.today()

        # 1. Room Inventory Status Counts
        all_rooms = Room.objects.filter(is_active=True).select_related('room_type').order_by('room_number')
        total_rooms = all_rooms.count()
        available_rooms = all_rooms.filter(status=Room.Status.AVAILABLE).count()
        reserved_rooms = all_rooms.filter(status=Room.Status.RESERVED).count()
        occupied_rooms = all_rooms.filter(status=Room.Status.OCCUPIED).count()
        cleaning_rooms = all_rooms.filter(status=Room.Status.CLEANING).count()
        maintenance_rooms = all_rooms.filter(status=Room.Status.MAINTENANCE).count()

        occupancy_rate = (occupied_rooms / total_rooms * 100.0) if total_rooms > 0 else 0.0

        # 2. Today's Operations
        today_checkins_qs = Booking.objects.filter(check_in_date=today).exclude(status__in=['CANCELLED', 'NO_SHOW'])
        today_checkins_count = today_checkins_qs.count()
        today_checkins_list = [
            {
                'id': b.id,
                'booking_number': b.booking_number,
                'customer_name': b.customer.full_name,
                'mobile': b.customer.mobile,
                'room_number': b.room.room_number,
                'check_in_date': str(b.check_in_date),
                'check_in_time': str(b.check_in_time)[:5],
                'expected_checkout_date': str(b.expected_checkout_date),
                'status': b.status,
            }
            for b in today_checkins_qs.select_related('customer', 'room')[:10]
        ]

        today_checkouts_qs = Stay.objects.filter(expected_checkout_date=today, status='CHECKED_IN')
        today_checkouts_count = today_checkouts_qs.count()
        today_checkouts_list = []
        for s in today_checkouts_qs.select_related('primary_customer', 'room'):
            bill = calculate_stay_bill(s)
            today_checkouts_list.append({
                'id': s.id,
                'stay_number': s.stay_number,
                'customer_name': s.primary_customer.full_name,
                'mobile': s.primary_customer.mobile,
                'room_number': s.room.room_number,
                'checkout_date': str(s.expected_checkout_date),
                'grand_total': float(bill['grand_total']),
                'total_paid': float(bill['total_paid']),
                'balance': float(bill['balance']),
                'status': s.status,
            })

        # 3. Revenue & Payment Summaries
        today_payments = Payment.objects.filter(payment_date__date=today).aggregate(total=Sum('amount'))['total'] or 0.00
        advance_received = Booking.objects.filter(created_at__date=today).aggregate(total=Sum('advance_amount'))['total'] or 0.00

        # Current Active Stays & Pending Payments Calculation
        active_stays = Stay.objects.filter(status='CHECKED_IN').select_related('primary_customer', 'room', 'room__room_type')
        current_guests_list = []
        pending_payments_total = Decimal('0.00')

        for stay in active_stays:
            bill = calculate_stay_bill(stay)
            balance = Decimal(str(bill['balance']))
            if balance > 0:
                pending_payments_total += balance

            current_guests_list.append({
                'id': stay.id,
                'stay_number': stay.stay_number,
                'room_number': stay.room.room_number,
                'room_type_name': stay.room.room_type.name,
                'guest_name': stay.primary_customer.full_name,
                'mobile': stay.primary_customer.mobile,
                'check_in_date': str(stay.check_in_date),
                'expected_checkout_date': str(stay.expected_checkout_date),
                'grand_total': float(bill['grand_total']),
                'total_paid': float(bill['total_paid']),
                'balance': float(bill['balance']),
                'status': stay.status,
            })

        # 4. Room Grid Status Cards
        active_stay_by_room = {s.room_id: s for s in active_stays}
        room_grid_list = []
        for r in all_rooms:
            stay_obj = active_stay_by_room.get(r.id)
            guest_name = stay_obj.primary_customer.full_name if stay_obj else None
            bal = float(calculate_stay_bill(stay_obj)['balance']) if stay_obj else 0.0

            room_grid_list.append({
                'id': r.id,
                'room_number': r.room_number,
                'room_type_name': r.room_type.name,
                'floor': r.floor,
                'status': r.status,
                'guest_name': guest_name,
                'balance': bal,
            })

        # 5. Charts Data (7 Days Trend)
        days_trend = []
        for i in range(6, -1, -1):
            d = today - datetime.timedelta(days=i)
            day_str = d.strftime('%d %b')
            pmts = float(Payment.objects.filter(payment_date__date=d).aggregate(total=Sum('amount'))['total'] or 0.0)
            st_count = Stay.objects.filter(check_in_date__lte=d, expected_checkout_date__gt=d).count()
            rate = round((st_count / total_rooms * 100.0), 1) if total_rooms > 0 else 0.0
            days_trend.append({
                'date': day_str,
                'revenue': pmts,
                'occupancy_rate': rate,
                'active_stays': st_count
            })

        room_status_donut = [
            {'name': 'Available', 'value': available_rooms, 'color': '#22C55E'},
            {'name': 'Occupied', 'value': occupied_rooms, 'color': '#EF4444'},
            {'name': 'Reserved', 'value': reserved_rooms, 'color': '#2563EB'},
            {'name': 'Cleaning', 'value': cleaning_rooms, 'color': '#8B5CF6'},
            {'name': 'Maintenance', 'value': maintenance_rooms, 'color': '#64748B'},
        ]

        booking_source_pie = [
            {'name': 'Direct Walk-In', 'value': Stay.objects.filter(booking__isnull=True).count() or 1, 'color': '#2563EB'},
            {'name': 'Advance Reservation', 'value': Booking.objects.count() or 1, 'color': '#8B5CF6'},
        ]

        # 6. Recent Activity Feed
        recent_activities = []
        for p in Payment.objects.select_related('stay__primary_customer', 'stay__room').order_by('-created_at')[:5]:
            recent_activities.append({
                'id': f"pay-{p.id}",
                'title': f"Payment Received — ₹{p.amount:,.2f}",
                'description': f"Received via {p.payment_method} from {p.stay.primary_customer.full_name} (Room {p.stay.room.room_number})",
                'time': p.created_at.strftime('%I:%M %p'),
                'icon': 'CreditCard',
                'color': 'success'
            })
        for s in Stay.objects.select_related('primary_customer', 'room').order_by('-created_at')[:5]:
            recent_activities.append({
                'id': f"stay-{s.id}",
                'title': f"Guest Checked In — Room {s.room.room_number}",
                'description': f"{s.primary_customer.full_name} arrived for Stay #{s.stay_number}",
                'time': s.created_at.strftime('%I:%M %p'),
                'icon': 'UserCheck',
                'color': 'primary'
            })
        recent_activities.sort(key=lambda x: x['time'], reverse=True)

        # 7. Upcoming Reservations (Next 7 Days)
        upcoming_qs = Booking.objects.filter(check_in_date__gt=today, status='CONFIRMED').select_related('customer', 'room').order_by('check_in_date')[:10]
        upcoming_list = [
            {
                'id': b.id,
                'booking_number': b.booking_number,
                'guest_name': b.customer.full_name,
                'mobile': b.customer.mobile,
                'room_number': b.room.room_number,
                'check_in_date': str(b.check_in_date),
                'expected_checkout_date': str(b.expected_checkout_date),
                'advance_amount': float(b.advance_amount),
            }
            for b in upcoming_qs
        ]

        # 8. Performance Summary KPIs
        cancelled_count = Booking.objects.filter(status='CANCELLED').count()
        no_show_count = Booking.objects.filter(status='NO_SHOW').count()
        avg_rate = float(Room.objects.filter(is_active=True).aggregate(avg=Sum('room_type__base_price'))['avg'] or 0.0) / (total_rooms or 1)

        return Response({
            'cards': {
                'total_rooms': total_rooms,
                'available_rooms': available_rooms,
                'occupied_rooms': occupied_rooms,
                'reserved_rooms': reserved_rooms,
                'cleaning_rooms': cleaning_rooms,
                'maintenance_rooms': maintenance_rooms,
                'today_revenue': float(today_payments),
                'pending_payments': float(pending_payments_total),
                'advance_received': float(advance_received),
                'today_checkins_count': today_checkins_count,
                'today_checkouts_count': today_checkouts_count,
                'occupancy_percentage': round(occupancy_rate, 1),
                'adr': round(avg_rate, 2),
                'cancelled_count': cancelled_count,
                'no_show_count': no_show_count,
            },
            'charts': {
                'days_trend': days_trend,
                'room_status_donut': room_status_donut,
                'booking_source_pie': booking_source_pie,
            },
            'tables': {
                'today_checkins': today_checkins_list,
                'today_checkouts': today_checkouts_list,
                'current_guests': current_guests_list,
                'upcoming_reservations': upcoming_list,
            },
            'room_grid': room_grid_list,
            'recent_activities': recent_activities[:7],
        })


class RevenueReportView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        period = request.query_params.get('period', 'this_month')
        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')
        today = datetime.date.today()

        if period == 'today':
            start_date = today
            end_date = today
        elif period == 'yesterday':
            start_date = today - datetime.timedelta(days=1)
            end_date = start_date
        elif period == 'this_week':
            start_date = today - datetime.timedelta(days=today.weekday())
            end_date = today
        else:
            start_date = today.replace(day=1)
            end_date = today

        payments = Payment.objects.filter(payment_date__date__range=[start_date, end_date])
        total_payments = payments.aggregate(total=Sum('amount'))['total'] or 0.00
        by_method = payments.values('payment_method').annotate(total=Sum('amount')).order_by('-total')

        return Response({
            'period': period,
            'start_date': start_date,
            'end_date': end_date,
            'total_payments': float(total_payments),
            'by_payment_method': [{'method': item['payment_method'], 'total': float(item['total'])} for item in by_method]
        })


class OccupancyReportView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        total_rooms = Room.objects.filter(is_active=True).count()
        occupied = Room.objects.filter(is_active=True, status=Room.Status.OCCUPIED).count()
        reserved = Room.objects.filter(is_active=True, status=Room.Status.RESERVED).count()
        available = Room.objects.filter(is_active=True, status=Room.Status.AVAILABLE).count()
        cleaning = Room.objects.filter(is_active=True, status=Room.Status.CLEANING).count()
        maintenance = Room.objects.filter(is_active=True, status=Room.Status.MAINTENANCE).count()
        occupancy_rate = (occupied / total_rooms * 100) if total_rooms > 0 else 0.0

        return Response({
            'total_rooms': total_rooms,
            'occupied': occupied,
            'reserved': reserved,
            'available': available,
            'cleaning': cleaning,
            'maintenance': maintenance,
            'occupancy_percentage': round(occupancy_rate, 2)
        })


class GuestRegisterReportView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        stays = Stay.objects.all().select_related('primary_customer', 'room').order_by('-check_in_date')
        data = [
            {
                'id': s.id,
                'stay_number': s.stay_number,
                'guest_name': s.primary_customer.full_name,
                'mobile': s.primary_customer.mobile,
                'room_number': s.room.room_number,
                'check_in_date': s.check_in_date,
                'expected_checkout_date': s.expected_checkout_date,
                'status': s.status
            }
            for s in stays[:50]
        ]
        return Response(data)
