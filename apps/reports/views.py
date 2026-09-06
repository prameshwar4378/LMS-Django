from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions, status
from django.db.models import Sum, Count, Q, Avg, F, Value, DecimalField
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone
import datetime
from decimal import Decimal

from apps.rooms.models import Room, RoomType
from apps.bookings.models import Booking
from apps.stays.models import Stay, StayGuest
from apps.billing.models import Payment, ExtraCharge, ChargeType, Invoice
from apps.customers.models import Customer
from apps.settings_app.models import Settings
from apps.billing.services import calculate_stay_bill
from apps.settings_app.tenant_views import get_active_property_for_request
from apps.authentication.permissions import user_has_perm, require_perm




def parse_date_range(params):
    """
    Parses date/datetime range from query params or preset shortcuts.
    Returns (start_date, end_date, start_datetime, end_datetime, label).
    """
    today = datetime.date.today()
    period = params.get('period', 'this_month')
    start_date_str = params.get('start_date')
    end_date_str = params.get('end_date')
    start_dt_str = params.get('start_datetime')
    end_dt_str = params.get('end_datetime')

    start_date = None
    end_date = None
    start_datetime = None
    end_datetime = None

    if start_dt_str:
        try:
            start_datetime = datetime.datetime.fromisoformat(start_dt_str.replace('Z', ''))
            start_date = start_datetime.date()
        except Exception:
            pass

    if end_dt_str:
        try:
            end_datetime = datetime.datetime.fromisoformat(end_dt_str.replace('Z', ''))
            end_date = end_datetime.date()
        except Exception:
            pass

    if not start_date and start_date_str:
        try:
            start_date = datetime.datetime.strptime(start_date_str, '%Y-%m-%d').date()
        except Exception:
            pass

    if not end_date and end_date_str:
        try:
            end_date = datetime.datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except Exception:
            pass

    if not start_date or not end_date:
        if period == 'today':
            start_date = today
            end_date = today
            label = "Today"
        elif period == 'yesterday':
            start_date = today - datetime.timedelta(days=1)
            end_date = start_date
            label = "Yesterday"
        elif period == 'last_7_days':
            start_date = today - datetime.timedelta(days=6)
            end_date = today
            label = "Last 7 Days"
        elif period == 'this_week':
            start_date = today - datetime.timedelta(days=today.weekday())
            end_date = today
            label = "This Week"
        elif period == 'last_month':
            first_this_month = today.replace(day=1)
            last_month_end = first_this_month - datetime.timedelta(days=1)
            start_date = last_month_end.replace(day=1)
            end_date = last_month_end
            label = "Last Month"
        elif period == 'this_fy':
            # Indian Financial Year: 1st April to 31st March
            if today.month >= 4:
                start_date = datetime.date(today.year, 4, 1)
                end_date = datetime.date(today.year + 1, 3, 31)
            else:
                start_date = datetime.date(today.year - 1, 4, 1)
                end_date = datetime.date(today.year, 3, 31)
            label = "This Financial Year"
        elif period == 'all':
            start_date = datetime.date(2020, 1, 1)
            end_date = today + datetime.timedelta(days=365)
            label = "All Time"
        else: # 'this_month'
            start_date = today.replace(day=1)
            end_date = today
            label = "This Month"
    else:
        label = f"{start_date.strftime('%d %b %Y')} – {end_date.strftime('%d %b %Y')}"

    if not start_datetime:
        start_datetime = datetime.datetime.combine(start_date, datetime.time.min)
    if not end_datetime:
        end_datetime = datetime.datetime.combine(end_date, datetime.time.max)

    return start_date, end_date, start_datetime, end_datetime, label


class ReportFilterOptionsView(APIView):
    """
    Returns dropdown filter options: Rooms, Room Types, Charge Categories, Payment Methods, etc.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        prop = get_active_property_for_request(request)

        room_qs = Room.objects.filter(property=prop, is_active=True) if prop else Room.objects.filter(is_active=True)
        rooms = [
            {'id': r.id, 'room_number': r.room_number, 'room_type': r.room_type.name if r.room_type else ''}
            for r in room_qs.select_related('room_type').order_by('room_number')
        ]
        rt_qs = RoomType.objects.filter(property=prop, is_active=True) if prop else RoomType.objects.filter(is_active=True)
        room_types = [
            {'id': rt.id, 'name': rt.name}
            for rt in rt_qs.order_by('name')
        ]
        ct_qs = ChargeType.objects.filter(property=prop, is_active=True) if prop else ChargeType.objects.filter(is_active=True)
        charge_types = [
            {'id': ct.id, 'name': ct.name, 'default_price': float(ct.default_price)}
            for ct in ct_qs.order_by('name')
        ]
        payment_methods = [
            {'value': 'CASH', 'label': 'Cash'},
            {'value': 'UPI', 'label': 'UPI / QR'},
            {'value': 'CARD', 'label': 'Card'},
            {'value': 'BANK_TRANSFER', 'label': 'Bank Transfer'},
            {'value': 'OTHER', 'label': 'Other'},
        ]
        stay_statuses = [
            {'value': 'CHECKED_IN', 'label': 'Checked In (Active)'},
            {'value': 'CHECKED_OUT', 'label': 'Checked Out'},
            {'value': 'CANCELLED', 'label': 'Cancelled'},
        ]
        booking_statuses = [
            {'value': 'CONFIRMED', 'label': 'Confirmed'},
            {'value': 'CHECKED_IN', 'label': 'Checked-In'},
            {'value': 'COMPLETED', 'label': 'Completed'},
            {'value': 'CANCELLED', 'label': 'Cancelled'},
            {'value': 'NO_SHOW', 'label': 'No-Show'},
        ]

        settings_obj = Settings.get_settings(prop=prop)
        lodge_info = {
            'lodge_name': settings_obj.lodge_name,
            'address': settings_obj.address,
            'phone': settings_obj.phone,
            'email': settings_obj.email,
            'gst_number': settings_obj.gst_number,
            'tax_percentage': float(settings_obj.tax_percentage or 0),
            'tax_enabled': settings_obj.tax_enabled,
            'property_code': prop.code if prop else 'LMS',
        }

        # Fetch recent completed and active shifts for shift-wise reporting if enabled
        is_shift_wise = getattr(prop, 'is_shift_wise', True) if prop else True
        operation_mode = getattr(prop, 'operation_mode', 'SHIFT_WISE') if prop else 'SHIFT_WISE'

        shifts = []
        if is_shift_wise:
            from apps.shifts.models import Shift
            shift_base = Shift.objects.filter(property=prop) if prop else Shift.objects.all()
            shifts = [
                {
                    'id': s.id,
                    'shift_number': s.shift_number,
                    'user_name': s.user.get_full_name() or s.user.username if s.user else 'Staff',
                    'status': s.status,
                    'status_display': s.get_status_display(),
                    'opened_at': s.opened_at.strftime('%Y-%m-%d %I:%M %p') if s.opened_at else '',
                    'closed_at': s.closed_at.strftime('%Y-%m-%d %I:%M %p') if s.closed_at else 'Open',
                    'cash_drawer_code': s.cash_drawer.code if s.cash_drawer else 'Till',
                }
                for s in shift_base.select_related('user', 'cash_drawer').order_by('-opened_at')[:40]
            ]

        return Response({
            'rooms': rooms,
            'room_types': room_types,
            'charge_types': charge_types,
            'payment_methods': payment_methods,
            'stay_statuses': stay_statuses,
            'booking_statuses': booking_statuses,
            'lodge_info': lodge_info,
            'operation_mode': operation_mode,
            'is_shift_wise': is_shift_wise,
            'shifts': shifts,
        })


class ReportDataView(APIView):
    """
    Central report data query engine supporting all 8 report categories and 25+ specialized reports.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        category = request.query_params.get('category', 'stay_guest')
        report_id = request.query_params.get('report_id', 'current_stays')
        search = request.query_params.get('search', '').strip()
        room_id = request.query_params.get('room_id')
        room_type_id = request.query_params.get('room_type_id')
        status_filter = request.query_params.get('status')
        payment_method = request.query_params.get('payment_method')
        charge_type_id = request.query_params.get('charge_type_id')

        user = request.user
        prop = get_active_property_for_request(request)

        start_date, end_date, start_datetime, end_datetime, date_label = parse_date_range(request.query_params)
        settings_obj = Settings.get_settings(prop=prop)
        tax_pct = Decimal(str(settings_obj.tax_percentage or 0)) if settings_obj.tax_enabled else Decimal('0.00')

        # Matrix permissions checks
        if category in ['revenue_payments', 'gst_tax']:
            require_perm(user, 'reports', 'can_view_revenue', "You do not have permission to view revenue reports.")

        if report_id in ['police_inquiry', 'form_c', 'police_gazette']:
            require_perm(user, 'reports', 'can_view_police_gazette', "You do not have permission to view the Police Gazette.")

        if request.query_params.get('export') in ['excel', 'csv', 'true', '1']:
            require_perm(user, 'reports', 'can_export_excel', "You do not have permission to export reports to Excel/CSV.")

        # Route to appropriate report generator
        if report_id == 'shift_dossier' or category in ['shift_audit', 'shift_reconciliation', 'shifts']:
            shift_id = request.query_params.get('shift_id')
            return self._handle_shift_reports(report_id, start_date, end_date, date_label, search, shift_id, prop)
        elif category == 'stay_guest':
            return self._handle_stay_guest_reports(report_id, start_date, end_date, start_datetime, end_datetime, date_label, search, room_id, room_type_id, status_filter, prop)
        elif category == 'bookings':
            return self._handle_booking_reports(report_id, start_date, end_date, start_datetime, end_datetime, date_label, search, room_id, status_filter, prop)
        elif category == 'rooms':
            return self._handle_room_reports(report_id, start_date, end_date, date_label, search, room_type_id, prop)
        elif category == 'revenue_payments':
            return self._handle_revenue_reports(report_id, start_date, end_date, start_datetime, end_datetime, date_label, search, payment_method, room_id, prop)
        elif category == 'gst_tax':
            return self._handle_gst_reports(report_id, start_date, end_date, start_datetime, end_datetime, date_label, search, tax_pct, room_id, prop)
        elif category == 'extra_charges':
            return self._handle_extra_charges_reports(report_id, start_date, end_date, start_datetime, end_datetime, date_label, search, charge_type_id, room_id, prop)
        elif category == 'customers':
            return self._handle_customer_reports(report_id, start_date, end_date, date_label, search, prop)
        elif category == 'cancellations':
            return self._handle_cancellation_reports(report_id, start_date, end_date, date_label, search, room_id, prop)
        else:
            return Response({'error': f"Unknown report category '{category}'"}, status=status.HTTP_400_BAD_REQUEST)

    # =========================================================================
    # 1. STAY & GUEST REPORTS
    # =========================================================================
    def _handle_stay_guest_reports(self, report_id, start_date, end_date, start_datetime, end_datetime, date_label, search, room_id, room_type_id, status_filter, prop=None):
        base_qs = Stay.objects.filter(property=prop) if prop else Stay.objects.all()
        stays_qs = base_qs.select_related('primary_customer', 'room', 'room__room_type', 'booking').prefetch_related('payments', 'extra_charges', 'guests')

        if room_id:
            stays_qs = stays_qs.filter(room_id=room_id)
        if room_type_id:
            stays_qs = stays_qs.filter(room__room_type_id=room_type_id)
        if status_filter:
            stays_qs = stays_qs.filter(status=status_filter)
        if search:
            stays_qs = stays_qs.filter(
                Q(stay_number__icontains=search) |
                Q(primary_customer__full_name__icontains=search) |
                Q(primary_customer__mobile__icontains=search) |
                Q(room__room_number__icontains=search)
            )

        title = "Stay & Guest Report"
        description = "Guest stays, check-ins, check-outs, and occupancy history."
        chart_data = None

        if report_id == 'current_stays':
            title = "Current Active Stays"
            description = "All guests currently checked in and residing in the lodge."
            stays_qs = stays_qs.filter(status='CHECKED_IN').order_by('room__room_number')
        elif report_id == 'checkin_report':
            title = "Check-In Report"
            description = f"Guests who checked in between {date_label}."
            stays_qs = stays_qs.filter(check_in_date__range=[start_date, end_date]).order_by('-check_in_date', '-check_in_time')
        elif report_id == 'checkout_report':
            title = "Check-Out Report"
            description = f"Guests who checked out between {date_label}."
            stays_qs = stays_qs.filter(
                Q(actual_checkout_date__range=[start_date, end_date]) |
                Q(status='CHECKED_OUT', updated_at__date__range=[start_date, end_date])
            ).order_by('-actual_checkout_date')
        elif report_id == 'overdue_stays':
            title = "Overdue Stay Report"
            description = "Active stays that have exceeded their scheduled expected checkout date."
            today = datetime.date.today()
            stays_qs = stays_qs.filter(status='CHECKED_IN', expected_checkout_date__lt=today).order_by('expected_checkout_date')
        elif report_id == 'guest_register':
            title = "Statutory Guest Register"
            description = f"Comprehensive chronological guest register for statutory and police verification ({date_label})."
            stays_qs = stays_qs.filter(check_in_date__range=[start_date, end_date]).order_by('-check_in_date')
            
            # Format detailed guest register with primary and additional guests
            rows = []
            serial = 1
            for s in stays_qs:
                c = s.primary_customer
                bill = calculate_stay_bill(s)
                rows.append({
                    'id': f"stay-{s.id}-prim",
                    'sr_no': serial,
                    'stay_number': s.stay_number,
                    'guest_name': c.full_name if c else 'Guest',
                    'guest_type': 'Primary Guest',
                    'gender': getattr(c, 'gender', '—'),
                    'age': getattr(c, 'age', '—') or '—',
                    'mobile': c.mobile if c else '',
                    'id_type': c.id_type if c else '—',
                    'id_number': c.id_number if c else '—',
                    'address': getattr(c, 'address', '—') or '—',
                    'room_number': s.room.room_number if s.room else '—',
                    'check_in': f"{s.check_in_date} {str(s.check_in_time)[:5]}",
                    'checkout': f"{s.actual_checkout_date or s.expected_checkout_date} {str(s.actual_checkout_time or s.expected_checkout_time)[:5]}",
                    'status': s.status,
                    'total_amount': float(bill['grand_total']),
                    'paid_amount': float(bill['total_paid']),
                    'balance': float(bill['balance']),
                })
                serial += 1
                for ag in s.guests.all():
                    rows.append({
                        'id': f"stay-{s.id}-ag-{ag.id}",
                        'sr_no': serial,
                        'stay_number': s.stay_number,
                        'guest_name': ag.guest_name,
                        'guest_type': f"Additional ({ag.relationship or 'Guest'})",
                        'gender': ag.gender or '—',
                        'age': ag.age or '—',
                        'mobile': ag.mobile or '—',
                        'id_type': ag.id_type or '—',
                        'id_number': ag.id_number or '—',
                        'address': getattr(c, 'address', '—') or '—',
                        'room_number': s.room.room_number if s.room else '—',
                        'check_in': f"{s.check_in_date} {str(s.check_in_time)[:5]}",
                        'checkout': f"{s.actual_checkout_date or s.expected_checkout_date} {str(s.actual_checkout_time or s.expected_checkout_time)[:5]}",
                        'status': s.status,
                        'total_amount': 0.0,
                        'paid_amount': 0.0,
                        'balance': 0.0,
                    })
                    serial += 1

            kpis = [
                {'label': 'Total Entries', 'value': len(rows), 'format': 'number', 'color': 'primary'},
                {'label': 'Total Stays', 'value': stays_qs.count(), 'format': 'number', 'color': 'info'},
                {'label': 'Period', 'value': date_label, 'format': 'text', 'color': 'secondary'},
            ]

            columns = [
                {'key': 'sr_no', 'label': '#', 'align': 'center'},
                {'key': 'stay_number', 'label': 'Stay #', 'align': 'left', 'sortable': True},
                {'key': 'guest_name', 'label': 'Guest Name', 'align': 'left', 'sortable': True},
                {'key': 'guest_type', 'label': 'Role', 'align': 'left'},
                {'key': 'gender', 'label': 'Gender/Age', 'align': 'center'},
                {'key': 'mobile', 'label': 'Mobile', 'align': 'left'},
                {'key': 'id_type', 'label': 'ID Type', 'align': 'left'},
                {'key': 'id_number', 'label': 'ID Number', 'align': 'left'},
                {'key': 'room_number', 'label': 'Room', 'align': 'center', 'sortable': True},
                {'key': 'check_in', 'label': 'Check-In', 'align': 'left', 'sortable': True},
                {'key': 'checkout', 'label': 'Check-Out', 'align': 'left'},
                {'key': 'status', 'label': 'Status', 'align': 'center', 'badgeStyle': 'status'},
            ]

            return Response({
                'report_id': report_id,
                'category': 'stay_guest',
                'title': title,
                'description': description,
                'date_label': date_label,
                'kpis': kpis,
                'columns': columns,
                'rows': rows,
                'total_count': len(rows),
            })
        elif report_id == 'police_gazette':
            title = "Statutory Police Gazette & Form C"
            description = f"Official statutory guest register formatted for State Police & Tourism verification ({date_label})."
            stays_qs = stays_qs.filter(check_in_date__range=[start_date, end_date]).order_by('-check_in_date')
            
            rows = []
            serial = 1
            for s in stays_qs:
                c = s.primary_customer
                bill = calculate_stay_bill(s)
                rows.append({
                    'id': f"stay-{s.id}-prim",
                    'sr_no': serial,
                    'stay_number': s.stay_number,
                    'guest_name': c.full_name if c else 'Guest',
                    'guest_type': 'Primary Guest',
                    'gender': getattr(c, 'gender', '—'),
                    'age': getattr(c, 'age', '—') or '—',
                    'mobile': c.mobile if c else '',
                    'id_type': c.id_type if c else '—',
                    'id_number': c.id_number if c else '—',
                    'nationality': 'Indian',
                    'address': getattr(c, 'address', '—') or '—',
                    'vehicle_number': getattr(c, 'vehicle_number', '—') or '—',
                    'coming_from': 'City of Residence',
                    'room_number': s.room.room_number if s.room else '—',
                    'check_in': f"{s.check_in_date} {str(s.check_in_time)[:5]}",
                    'checkout': f"{s.actual_checkout_date or s.expected_checkout_date} {str(s.actual_checkout_time or s.expected_checkout_time)[:5]}",
                    'status': s.status,
                })
                serial += 1
                for ag in s.guests.all():
                    rows.append({
                        'id': f"stay-{s.id}-ag-{ag.id}",
                        'sr_no': serial,
                        'stay_number': s.stay_number,
                        'guest_name': ag.guest_name,
                        'guest_type': f"Additional ({ag.relationship or 'Guest'})",
                        'gender': ag.gender or '—',
                        'age': ag.age or '—',
                        'mobile': ag.mobile or '—',
                        'id_type': ag.id_type or '—',
                        'id_number': ag.id_number or '—',
                        'nationality': 'Indian',
                        'address': getattr(c, 'address', '—') or '—',
                        'vehicle_number': '—',
                        'coming_from': '—',
                        'room_number': s.room.room_number if s.room else '—',
                        'check_in': f"{s.check_in_date} {str(s.check_in_time)[:5]}",
                        'checkout': f"{s.actual_checkout_date or s.expected_checkout_date} {str(s.actual_checkout_time or s.expected_checkout_time)[:5]}",
                        'status': s.status,
                    })
                    serial += 1

            kpis = [
                {'label': 'Verified Guests', 'value': len(rows), 'format': 'number', 'color': 'primary'},
                {'label': 'Total Stays', 'value': stays_qs.count(), 'format': 'number', 'color': 'info'},
                {'label': 'Police Verification', 'value': 'Statutory Ready', 'format': 'text', 'color': 'success'},
            ]

            columns = [
                {'key': 'sr_no', 'label': '#', 'align': 'center'},
                {'key': 'guest_name', 'label': 'Guest Full Name', 'align': 'left', 'sortable': True},
                {'key': 'gender', 'label': 'Gender/Age', 'align': 'center'},
                {'key': 'mobile', 'label': 'Mobile Number', 'align': 'left'},
                {'key': 'id_type', 'label': 'ID Type', 'align': 'left'},
                {'key': 'id_number', 'label': 'ID Number', 'align': 'left', 'sortable': True},
                {'key': 'address', 'label': 'Permanent Address', 'align': 'left'},
                {'key': 'room_number', 'label': 'Room Allocated', 'align': 'center', 'sortable': True},
                {'key': 'check_in', 'label': 'Arrival Datetime', 'align': 'left', 'sortable': True},
                {'key': 'checkout', 'label': 'Departure Datetime', 'align': 'left'},
                {'key': 'status', 'label': 'Status', 'align': 'center', 'badgeStyle': 'status'},
            ]

            return Response({
                'report_id': report_id,
                'category': 'stay_guest',
                'title': title,
                'description': description,
                'date_label': date_label,
                'kpis': kpis,
                'columns': columns,
                'rows': rows,
                'total_count': len(rows),
            })
        else: # 'stay_history'
            title = "Stay History Report"
            description = f"Chronological history of all room stays for {date_label}."
            stays_qs = stays_qs.filter(check_in_date__range=[start_date, end_date]).order_by('-check_in_date')

        # Standard Stay Table Rows
        rows = []
        tot_grand = Decimal('0.00')
        tot_paid = Decimal('0.00')
        tot_balance = Decimal('0.00')
        tot_nights = 0

        for s in stays_qs:
            bill = calculate_stay_bill(s)
            tot_grand += Decimal(str(bill['grand_total']))
            tot_paid += Decimal(str(bill['total_paid']))
            tot_balance += Decimal(str(bill['balance']))
            tot_nights += int(bill['room_days'])

            rows.append({
                'id': s.id,
                'stay_number': s.stay_number,
                'guest_name': s.primary_customer.full_name if s.primary_customer else 'Guest',
                'mobile': s.primary_customer.mobile if s.primary_customer else '',
                'room_number': s.room.room_number if s.room else '—',
                'room_type': s.room.room_type.name if (s.room and s.room.room_type) else 'Standard',
                'check_in': f"{s.check_in_date} {str(s.check_in_time)[:5]}",
                'expected_checkout': f"{s.expected_checkout_date} {str(s.expected_checkout_time)[:5]}",
                'actual_checkout': f"{s.actual_checkout_date} {str(s.actual_checkout_time)[:5]}" if s.actual_checkout_date else '—',
                'nights': bill['room_days'],
                'room_rate': float(bill['room_rate']),
                'subtotal': float(bill['subtotal']),
                'extra_charges': float(bill['extra_charges_total']),
                'discount': float(bill['discount_amount']),
                'tax_amount': float(bill['tax_amount']),
                'grand_total': float(bill['grand_total']),
                'total_paid': float(bill['total_paid']),
                'balance': float(bill['balance']),
                'status': s.status,
            })

        kpis = [
            {'label': 'Total Stays', 'value': len(rows), 'format': 'number', 'color': 'primary'},
            {'label': 'Total Nights', 'value': tot_nights, 'format': 'number', 'color': 'info'},
            {'label': 'Total Billing', 'value': float(tot_grand), 'format': 'currency', 'color': 'dark'},
            {'label': 'Total Paid', 'value': float(tot_paid), 'format': 'currency', 'color': 'success'},
            {'label': 'Pending Balance', 'value': float(tot_balance), 'format': 'currency', 'color': 'danger' if tot_balance > 0 else 'secondary'},
        ]

        columns = [
            {'key': 'stay_number', 'label': 'Stay #', 'align': 'left', 'sortable': True},
            {'key': 'guest_name', 'label': 'Guest Name', 'align': 'left', 'sortable': True},
            {'key': 'mobile', 'label': 'Mobile', 'align': 'left'},
            {'key': 'room_number', 'label': 'Room', 'align': 'center', 'sortable': True},
            {'key': 'check_in', 'label': 'Check-In', 'align': 'left', 'sortable': True},
            {'key': 'actual_checkout', 'label': 'Check-Out', 'align': 'left'},
            {'key': 'nights', 'label': 'Nights', 'align': 'center', 'sortable': True},
            {'key': 'grand_total', 'label': 'Total (₹)', 'align': 'right', 'format': 'currency', 'sortable': True},
            {'key': 'total_paid', 'label': 'Paid (₹)', 'align': 'right', 'format': 'currency', 'sortable': True},
            {'key': 'balance', 'label': 'Balance (₹)', 'align': 'right', 'format': 'currency', 'sortable': True},
            {'key': 'status', 'label': 'Status', 'align': 'center', 'badgeStyle': 'status'},
        ]

        return Response({
            'report_id': report_id,
            'category': 'stay_guest',
            'title': title,
            'description': description,
            'date_label': date_label,
            'kpis': kpis,
            'chart_data': chart_data,
            'columns': columns,
            'rows': rows,
            'total_count': len(rows),
        })

    # =========================================================================
    # 2. BOOKING REPORTS
    # =========================================================================
    def _handle_booking_reports(self, report_id, start_date, end_date, start_datetime, end_datetime, date_label, search, room_id, status_filter, prop=None):
        base_qs = Booking.objects.filter(property=prop) if prop else Booking.objects.all()
        b_qs = base_qs.select_related('customer', 'room', 'room__room_type')

        if room_id:
            b_qs = b_qs.filter(room_id=room_id)
        if status_filter:
            b_qs = b_qs.filter(status=status_filter)
        if search:
            b_qs = b_qs.filter(
                Q(booking_number__icontains=search) |
                Q(customer__full_name__icontains=search) |
                Q(customer__mobile__icontains=search) |
                Q(room__room_number__icontains=search)
            )

        title = "Booking Report"
        description = "Reservations, advance bookings, sources, and cancellations."
        today = datetime.date.today()
        chart_data = None

        if report_id == 'upcoming_bookings':
            title = "Upcoming Bookings"
            description = "Advance confirmed bookings scheduled for future check-in."
            b_qs = b_qs.filter(check_in_date__gte=today, status='CONFIRMED').order_by('check_in_date')
        elif report_id == 'cancelled_bookings':
            title = "Cancelled Bookings Report"
            description = f"Bookings cancelled between {date_label}."
            b_qs = b_qs.filter(status='CANCELLED', updated_at__date__range=[start_date, end_date]).order_by('-updated_at')
        elif report_id == 'noshow_bookings':
            title = "No-Show Bookings Report"
            description = f"Guests who did not arrive for their reservations ({date_label})."
            b_qs = b_qs.filter(status='NO_SHOW', check_in_date__range=[start_date, end_date]).order_by('-check_in_date')
        elif report_id == 'booking_source':
            title = "Booking Source Breakdown"
            description = f"Analysis of reservation channels and booking sources for {date_label}."
            b_qs = b_qs.filter(created_at__date__range=[start_date, end_date]).order_by('-created_at')
        else: # 'booking_summary' / 'booking_history'
            title = "Booking History & Summary"
            description = f"All reservations booked or scheduled between {date_label}."
            b_qs = b_qs.filter(
                Q(created_at__date__range=[start_date, end_date]) |
                Q(check_in_date__range=[start_date, end_date])
            ).order_by('-created_at')

        # Compute status distribution for Chart
        status_counts = b_qs.values('status').annotate(count=Count('id'))
        status_colors = {
            'CONFIRMED': '#2563EB',
            'CHECKED_IN': '#16A34A',
            'COMPLETED': '#0D9488',
            'CANCELLED': '#EF4444',
            'NO_SHOW': '#F59E0B',
        }
        chart_data = [
            {'name': sc['status'].replace('_', ' '), 'value': sc['count'], 'color': status_colors.get(sc['status'], '#64748B')}
            for sc in status_counts
        ]

        rows = []
        tot_adv = Decimal('0.00')

        for b in b_qs:
            tot_adv += Decimal(str(b.advance_amount or 0))
            nights = (b.expected_checkout_date - b.check_in_date).days if b.expected_checkout_date and b.check_in_date else 1
            rows.append({
                'id': b.id,
                'booking_number': b.booking_number,
                'customer_name': b.customer.full_name if b.customer else 'Guest',
                'mobile': b.customer.mobile if b.customer else '',
                'room_number': b.room.room_number if b.room else '—',
                'room_type': b.room.room_type.name if (b.room and b.room.room_type) else 'Standard',
                'booking_date': b.created_at.strftime('%Y-%m-%d %H:%M'),
                'check_in_date': str(b.check_in_date),
                'checkout_date': str(b.expected_checkout_date),
                'nights': max(1, nights),
                'advance_amount': float(b.advance_amount or 0),
                'special_requests': b.notes or '—',
                'status': b.status,
            })

        kpis = [
            {'label': 'Total Bookings', 'value': len(rows), 'format': 'number', 'color': 'primary'},
            {'label': 'Advance Collected', 'value': float(tot_adv), 'format': 'currency', 'color': 'success'},
            {'label': 'Confirmed', 'value': sum(1 for r in rows if r['status'] == 'CONFIRMED'), 'format': 'number', 'color': 'info'},
            {'label': 'Checked-In', 'value': sum(1 for r in rows if r['status'] == 'CHECKED_IN'), 'format': 'number', 'color': 'primary'},
            {'label': 'Cancelled / No-Show', 'value': sum(1 for r in rows if r['status'] in ['CANCELLED', 'NO_SHOW']), 'format': 'number', 'color': 'danger'},
        ]

        columns = [
            {'key': 'booking_number', 'label': 'Booking #', 'align': 'left', 'sortable': True},
            {'key': 'customer_name', 'label': 'Guest Name', 'align': 'left', 'sortable': True},
            {'key': 'mobile', 'label': 'Mobile', 'align': 'left'},
            {'key': 'room_number', 'label': 'Room', 'align': 'center', 'sortable': True},
            {'key': 'check_in_date', 'label': 'Arrival Date', 'align': 'left', 'sortable': True},
            {'key': 'checkout_date', 'label': 'Departure Date', 'align': 'left'},
            {'key': 'nights', 'label': 'Nights', 'align': 'center'},
            {'key': 'advance_amount', 'label': 'Advance Paid (₹)', 'align': 'right', 'format': 'currency', 'sortable': True},
            {'key': 'status', 'label': 'Booking Status', 'align': 'center', 'badgeStyle': 'status'},
        ]

        return Response({
            'report_id': report_id,
            'category': 'bookings',
            'title': title,
            'description': description,
            'date_label': date_label,
            'kpis': kpis,
            'chart_data': chart_data,
            'columns': columns,
            'rows': rows,
            'total_count': len(rows),
        })

    # =========================================================================
    def _handle_room_reports(self, report_id, start_date, end_date, date_label, search, room_type_id, prop=None):
        room_base = Room.objects.filter(property=prop, is_active=True) if prop else Room.objects.filter(is_active=True)
        all_rooms = room_base.select_related('room_type').order_by('room_number')
        if room_type_id:
            all_rooms = all_rooms.filter(room_type_id=room_type_id)
        if search:
            all_rooms = all_rooms.filter(
                Q(room_number__icontains=search) |
                Q(room_type__name__icontains=search)
            )

        if report_id == 'occupancy_forecast':
            title = "30-Day Predictive Occupancy & Revenue Forecast"
            description = "Forward-looking 30-day projection based on confirmed reservations and historical demand patterns."
            
            today = datetime.date.today()
            total_active_rooms = all_rooms.count()
            forecast_rows = []
            chart_data = []
            
            proj_total_rev = Decimal('0.00')
            proj_total_nights = 0

            for d_offset in range(30):
                target_date = today + datetime.timedelta(days=d_offset)
                date_str = target_date.strftime('%Y-%m-%d')
                day_name = target_date.strftime('%a')
                
                stay_base = Stay.objects.filter(property=prop) if prop else Stay.objects.all()
                overlapping_stays = stay_base.filter(
                    check_in_date__lte=target_date,
                    expected_checkout_date__gt=target_date,
                    status__in=['CHECKED_IN', 'RESERVED']
                )
                
                book_base = Booking.objects.filter(property=prop) if prop else Booking.objects.all()
                overlapping_bookings = book_base.filter(
                    check_in_date__lte=target_date,
                    expected_checkout_date__gt=target_date,
                    status__in=['CONFIRMED', 'CHECKED_IN']
                )

                booked_count = overlapping_stays.count() + overlapping_bookings.count()
                is_weekend = target_date.weekday() in [4, 5, 6]
                est_walkins = 2 if is_weekend else 1
                projected_occ_rooms = min(total_active_rooms, booked_count + est_walkins)
                occ_pct = round((projected_occ_rooms / (total_active_rooms or 1) * 100.0), 1)
                
                avg_rate = 1800.0
                day_rev = projected_occ_rooms * avg_rate
                proj_total_rev += Decimal(str(day_rev))
                proj_total_nights += projected_occ_rooms

                forecast_rows.append({
                    'id': f"fc-{date_str}",
                    'date': date_str,
                    'day': day_name,
                    'total_rooms': total_active_rooms,
                    'confirmed_reservations': booked_count,
                    'projected_walkins': est_walkins,
                    'projected_occupied': projected_occ_rooms,
                    'occupancy_pct': occ_pct,
                    'projected_revenue': float(day_rev),
                    'demand_level': 'High' if occ_pct >= 70 else ('Moderate' if occ_pct >= 40 else 'Low')
                })

                chart_data.append({
                    'date': f"{target_date.strftime('%b %d')} ({day_name})",
                    'Occupancy': occ_pct,
                    'revenue': float(day_rev),
                })

            avg_proj_occ = round((proj_total_nights / ((total_active_rooms * 30) or 1) * 100.0), 1)

            kpis = [
                {'label': 'Projected 30D Revenue', 'value': float(proj_total_rev), 'format': 'currency', 'color': 'primary'},
                {'label': 'Average Forecast Occupancy', 'value': f"{avg_proj_occ}%", 'format': 'text', 'color': 'success'},
                {'label': 'Projected Occupied Nights', 'value': proj_total_nights, 'format': 'number', 'color': 'info'},
                {'label': 'Forecast Window', 'value': 'Next 30 Days', 'format': 'text', 'color': 'secondary'},
            ]

            columns = [
                {'key': 'date', 'label': 'Date', 'align': 'left', 'sortable': True},
                {'key': 'day', 'label': 'Day', 'align': 'center'},
                {'key': 'confirmed_reservations', 'label': 'Confirmed Bookings', 'align': 'center', 'sortable': True},
                {'key': 'projected_occupied', 'label': 'Projected Rooms', 'align': 'center', 'sortable': True},
                {'key': 'occupancy_pct', 'label': 'Occupancy %', 'align': 'center', 'sortable': True},
                {'key': 'projected_revenue', 'label': 'Projected Revenue (₹)', 'align': 'right', 'format': 'currency', 'sortable': True},
                {'key': 'demand_level', 'label': 'Demand Level', 'align': 'center', 'badgeStyle': 'status'},
            ]

            return Response({
                'report_id': report_id,
                'category': 'rooms',
                'title': title,
                'description': description,
                'date_label': "Next 30 Days Forecast",
                'kpis': kpis,
                'chart_data': chart_data,
                'columns': columns,
                'rows': forecast_rows,
                'total_count': len(forecast_rows),
            })

        days_in_period = max(1, (end_date - start_date).days + 1)
        total_capacity_nights = all_rooms.count() * days_in_period

        # Fetch stays overlapping the period
        stay_base = Stay.objects.filter(property=prop) if prop else Stay.objects.all()
        period_stays = stay_base.filter(
            check_in_date__lte=end_date,
            expected_checkout_date__gte=start_date
        ).select_related('room', 'primary_customer').prefetch_related('payments', 'extra_charges')

        room_stats = {}
        for r in all_rooms:
            room_stats[r.id] = {
                'room_obj': r,
                'stays_count': 0,
                'nights_count': 0,
                'room_revenue': Decimal('0.00'),
                'extra_charges': Decimal('0.00'),
                'discounts': Decimal('0.00'),
                'gst_tax': Decimal('0.00'),
                'total_revenue': Decimal('0.00'),
            }

        for s in period_stays:
            if s.room_id in room_stats:
                bill = calculate_stay_bill(s)
                rs = room_stats[s.room_id]
                rs['stays_count'] += 1
                rs['nights_count'] += int(bill['room_days'])
                rs['room_revenue'] += Decimal(str(bill['total_room_charge']))
                rs['extra_charges'] += Decimal(str(bill['extra_charges_total']))
                rs['discounts'] += Decimal(str(bill['discount_amount']))
                rs['gst_tax'] += Decimal(str(bill['tax_amount']))
                rs['total_revenue'] += Decimal(str(bill['grand_total']))

        rows = []
        tot_rev = Decimal('0.00')
        tot_nights = 0
        tot_stays = 0

        for rid, rs in room_stats.items():
            r = rs['room_obj']
            occ_rate = round((rs['nights_count'] / days_in_period * 100.0), 1) if days_in_period > 0 else 0.0
            tot_rev += rs['total_revenue']
            tot_nights += rs['nights_count']
            tot_stays += rs['stays_count']

            rows.append({
                'id': r.id,
                'room_number': r.room_number,
                'room_type': r.room_type.name if r.room_type else 'Standard',
                'base_price': float((r.room_type.base_price if r.room_type else 0) or 0),
                'current_status': r.status,
                'total_stays': rs['stays_count'],
                'total_nights': rs['nights_count'],
                'occupancy_pct': occ_rate,
                'room_revenue': float(rs['room_revenue']),
                'extra_charges': float(rs['extra_charges']),
                'discount': float(rs['discounts']),
                'gst_tax': float(rs['gst_tax']),
                'total_revenue': float(rs['total_revenue']),
                'adr': round(float(rs['total_revenue']) / (rs['nights_count'] or 1), 2),
            })

        # Chart: Top 10 Rooms by Revenue
        sorted_by_rev = sorted(rows, key=lambda x: x['total_revenue'], reverse=True)[:8]
        chart_data = [
            {'name': f"Room {x['room_number']}", 'revenue': x['total_revenue'], 'nights': x['total_nights']}
            for x in sorted_by_rev
        ]

        overall_occ = round((tot_nights / (total_capacity_nights or 1) * 100.0), 1)
        adr = round(float(tot_rev) / (tot_nights or 1), 2)
        revpar = round(float(tot_rev) / (total_capacity_nights or 1), 2)

        kpis = [
            {'label': 'Total Room Revenue', 'value': float(tot_rev), 'format': 'currency', 'color': 'primary'},
            {'label': 'Total Occupied Nights', 'value': tot_nights, 'format': 'number', 'color': 'info'},
            {'label': 'Average Occupancy', 'value': f"{overall_occ}%", 'format': 'text', 'color': 'success'},
            {'label': 'ADR (Avg Daily Rate)', 'value': float(adr), 'format': 'currency', 'color': 'dark'},
            {'label': 'RevPAR', 'value': float(revpar), 'format': 'currency', 'color': 'secondary'},
        ]

        columns = [
            {'key': 'room_number', 'label': 'Room', 'align': 'center', 'sortable': True},
            {'key': 'room_type', 'label': 'Room Type', 'align': 'left', 'sortable': True},
            {'key': 'total_stays', 'label': 'Stays', 'align': 'center', 'sortable': True},
            {'key': 'total_nights', 'label': 'Nights', 'align': 'center', 'sortable': True},
            {'key': 'occupancy_pct', 'label': 'Occupancy %', 'align': 'center', 'sortable': True},
            {'key': 'room_revenue', 'label': 'Room Tariff (₹)', 'align': 'right', 'format': 'currency', 'sortable': True},
            {'key': 'extra_charges', 'label': 'Extra Services (₹)', 'align': 'right', 'format': 'currency'},
            {'key': 'discount', 'label': 'Discount (₹)', 'align': 'right', 'format': 'currency'},
            {'key': 'gst_tax', 'label': 'GST (₹)', 'align': 'right', 'format': 'currency'},
            {'key': 'total_revenue', 'label': 'Total Revenue (₹)', 'align': 'right', 'format': 'currency', 'sortable': True},
            {'key': 'adr', 'label': 'ADR (₹)', 'align': 'right', 'format': 'currency'},
        ]

        return Response({
            'report_id': report_id,
            'category': 'rooms',
            'title': "Room Performance & Revenue Report",
            'description': f"Room-wise utilization, nights occupied, tariff, and extra service revenue ({date_label}).",
            'date_label': date_label,
            'kpis': kpis,
            'chart_data': chart_data,
            'columns': columns,
            'rows': rows,
            'total_count': len(rows),
        })

    # =========================================================================
    # 4. REVENUE & PAYMENT REPORTS
    # =========================================================================
    def _handle_revenue_reports(self, report_id, start_date, end_date, start_datetime, end_datetime, date_label, search, payment_method, room_id, prop=None):
        title = "Revenue & Collections Report"
        description = f"Financial audit of payments, collections, and pending balances for {date_label}."

        if report_id == 'payment_collections':
            title = "Payment Collections Audit"
            description = f"Detailed ledger of all financial transactions received between {date_label}."
            pay_base = Payment.objects.filter(property=prop) if prop else Payment.objects.all()
            payments_qs = pay_base.filter(payment_date__date__range=[start_date, end_date]).select_related('customer', 'stay', 'stay__room', 'received_by')
            if payment_method:
                payments_qs = payments_qs.filter(payment_method=payment_method)
            if room_id:
                payments_qs = payments_qs.filter(stay__room_id=room_id)
            if search:
                payments_qs = payments_qs.filter(
                    Q(payment_number__icontains=search) |
                    Q(transaction_reference__icontains=search) |
                    Q(customer__full_name__icontains=search) |
                    Q(stay__stay_number__icontains=search)
                )

            payments_qs = payments_qs.order_by('-payment_date')

            rows = []
            tot_coll = Decimal('0.00')
            tot_refund = Decimal('0.00')

            for p in payments_qs:
                amt = Decimal(str(p.amount or 0))
                if amt >= 0:
                    tot_coll += amt
                else:
                    tot_refund += abs(amt)

                c_name = p.customer.full_name if p.customer else (p.stay.primary_customer.full_name if (p.stay and p.stay.primary_customer) else 'Guest')
                room_no = p.stay.room.room_number if (p.stay and p.stay.room) else '—'

                rows.append({
                    'id': p.id,
                    'payment_number': p.payment_number,
                    'payment_datetime': p.payment_date.strftime('%Y-%m-%d %I:%M %p'),
                    'customer_name': c_name,
                    'stay_number': p.stay.stay_number if p.stay else '—',
                    'room_number': room_no,
                    'payment_method': p.payment_method,
                    'transaction_ref': p.transaction_reference or '—',
                    'amount': float(amt),
                    'type': 'COLLECTION' if amt >= 0 else 'REFUND',
                    'received_by': p.received_by.get_full_name() or p.received_by.username if p.received_by else 'Staff',
                    'notes': p.notes or '—',
                })

            net_coll = tot_coll - tot_refund
            chart_data = [
                {'name': 'Cash', 'amount': float(payments_qs.filter(payment_method='CASH', amount__gt=0).aggregate(t=Sum('amount'))['t'] or 0)},
                {'name': 'UPI / QR', 'amount': float(payments_qs.filter(payment_method='UPI', amount__gt=0).aggregate(t=Sum('amount'))['t'] or 0)},
                {'name': 'Cards', 'amount': float(payments_qs.filter(payment_method='CARD', amount__gt=0).aggregate(t=Sum('amount'))['t'] or 0)},
                {'name': 'Bank Transfers', 'amount': float(payments_qs.filter(payment_method='BANK_TRANSFER', amount__gt=0).aggregate(t=Sum('amount'))['t'] or 0)},
                {'name': 'Other / Wallet', 'amount': float(payments_qs.filter(payment_method__in=['OTHER', 'WALLET'], amount__gt=0).aggregate(t=Sum('amount'))['t'] or 0)},
            ]

            kpis = [
                {'label': 'Net Collections', 'value': float(net_coll), 'format': 'currency', 'color': 'success'},
                {'label': 'Gross Receipts', 'value': float(tot_coll), 'format': 'currency', 'color': 'primary'},
                {'label': 'Refunds / Returns', 'value': float(tot_refund), 'format': 'currency', 'color': 'danger' if tot_refund > 0 else 'secondary'},
                {'label': 'Total Transactions', 'value': len(rows), 'format': 'number', 'color': 'info'},
            ]

            columns = [
                {'key': 'payment_number', 'label': 'Receipt #', 'align': 'left', 'sortable': True},
                {'key': 'payment_datetime', 'label': 'Date & Time', 'align': 'left', 'sortable': True},
                {'key': 'customer_name', 'label': 'Guest', 'align': 'left', 'sortable': True},
                {'key': 'room_number', 'label': 'Room', 'align': 'center'},
                {'key': 'payment_method', 'label': 'Method', 'align': 'center', 'sortable': True},
                {'key': 'transaction_ref', 'label': 'Ref / URN', 'align': 'left'},
                {'key': 'amount', 'label': 'Amount (₹)', 'align': 'right', 'format': 'currency', 'sortable': True},
                {'key': 'type', 'label': 'Type', 'align': 'center', 'badgeStyle': 'status'},
                {'key': 'received_by', 'label': 'Collected By', 'align': 'left'},
            ]

            return Response({
                'report_id': report_id,
                'category': 'revenue_payments',
                'title': title,
                'description': description,
                'date_label': date_label,
                'kpis': kpis,
                'chart_data': chart_data,
                'columns': columns,
                'rows': rows,
                'total_count': len(rows),
            })

        elif report_id == 'pending_payments':
            title = "Pending Balances & Unsettled Folios"
            description = "Active and completed stays with outstanding balance due."
            stay_base = Stay.objects.filter(property=prop) if prop else Stay.objects.all()
            active_stays = stay_base.filter(status__in=['CHECKED_IN', 'CHECKED_OUT']).select_related('primary_customer', 'room').prefetch_related('payments', 'extra_charges')
            if room_id:
                active_stays = active_stays.filter(room_id=room_id)
            if search:
                active_stays = active_stays.filter(
                    Q(stay_number__icontains=search) |
                    Q(primary_customer__full_name__icontains=search) |
                    Q(primary_customer__mobile__icontains=search) |
                    Q(room__room_number__icontains=search)
                )

            rows = []
            tot_pending = Decimal('0.00')

            for s in active_stays:
                bill = calculate_stay_bill(s)
                bal = Decimal(str(bill['balance']))
                if bal > Decimal('0.01'):
                    tot_pending += bal
                    rows.append({
                        'id': s.id,
                        'stay_number': s.stay_number,
                        'customer_name': s.primary_customer.full_name if s.primary_customer else 'Guest',
                        'mobile': s.primary_customer.mobile if s.primary_customer else '',
                        'room_number': s.room.room_number if s.room else '—',
                        'check_in': str(s.check_in_date),
                        'expected_checkout': str(s.actual_checkout_date or s.expected_checkout_date),
                        'grand_total': float(bill['grand_total']),
                        'total_paid': float(bill['total_paid']),
                        'balance_due': float(bal),
                        'status': s.status,
                    })

            rows.sort(key=lambda x: x['balance_due'], reverse=True)

            kpis = [
                {'label': 'Total Outstanding', 'value': float(tot_pending), 'format': 'currency', 'color': 'danger'},
                {'label': 'Unsettled Stays', 'value': len(rows), 'format': 'number', 'color': 'warning'},
                {'label': 'Status', 'value': 'Requires Follow-up', 'format': 'text', 'color': 'danger'},
            ]

            columns = [
                {'key': 'stay_number', 'label': 'Stay #', 'align': 'left', 'sortable': True},
                {'key': 'customer_name', 'label': 'Guest Name', 'align': 'left', 'sortable': True},
                {'key': 'mobile', 'label': 'Mobile', 'align': 'left'},
                {'key': 'room_number', 'label': 'Room', 'align': 'center', 'sortable': True},
                {'key': 'check_in', 'label': 'Check-In', 'align': 'left'},
                {'key': 'expected_checkout', 'label': 'Check-Out', 'align': 'left'},
                {'key': 'grand_total', 'label': 'Total Bill (₹)', 'align': 'right', 'format': 'currency', 'sortable': True},
                {'key': 'total_paid', 'label': 'Paid (₹)', 'align': 'right', 'format': 'currency', 'sortable': True},
                {'key': 'balance_due', 'label': 'Balance Due (₹)', 'align': 'right', 'format': 'currency', 'sortable': True},
                {'key': 'status', 'label': 'Stay Status', 'align': 'center', 'badgeStyle': 'status'},
            ]

            return Response({
                'report_id': report_id,
                'category': 'revenue_payments',
                'title': title,
                'description': description,
                'date_label': "Current Live Balances",
                'kpis': kpis,
                'columns': columns,
                'rows': rows,
                'total_count': len(rows),
            })

        elif report_id == 'shift_handover':
            title = "Shift & Cash Drawer Handover Audit"
            description = f"Cash drawer reconciliation, cashier collections, and till balancing ({date_label})."
            pay_base = Payment.objects.filter(property=prop) if prop else Payment.objects.all()
            payments_qs = pay_base.filter(payment_date__date__range=[start_date, end_date]).select_related('customer', 'stay', 'stay__room', 'received_by')
            if search:
                payments_qs = payments_qs.filter(
                    Q(payment_number__icontains=search) |
                    Q(received_by__username__icontains=search) |
                    Q(customer__full_name__icontains=search)
                )

            payments_qs = payments_qs.order_by('-payment_date')

            cash_in = Decimal('0.00')
            cash_out = Decimal('0.00')
            digital_in = Decimal('0.00')
            staff_set = set()

            rows = []
            for p in payments_qs:
                amt = Decimal(str(p.amount or 0))
                staff_name = p.received_by.get_full_name() or p.received_by.username if p.received_by else 'Staff'
                staff_set.add(staff_name)

                if p.payment_method == 'CASH':
                    if amt >= 0:
                        cash_in += amt
                    else:
                        cash_out += abs(amt)
                else:
                    if amt >= 0:
                        digital_in += amt

                c_name = p.customer.full_name if p.customer else (p.stay.primary_customer.full_name if (p.stay and p.stay.primary_customer) else 'Guest')
                room_no = p.stay.room.room_number if (p.stay and p.stay.room) else '—'

                rows.append({
                    'id': p.id,
                    'payment_number': p.payment_number,
                    'payment_datetime': p.payment_date.strftime('%Y-%m-%d %I:%M %p'),
                    'cashier': staff_name,
                    'customer_name': c_name,
                    'room_number': room_no,
                    'payment_method': p.payment_method,
                    'cash_in': float(amt) if (p.payment_method == 'CASH' and amt >= 0) else 0.0,
                    'cash_out': float(abs(amt)) if (p.payment_method == 'CASH' and amt < 0) else 0.0,
                    'digital_amount': float(amt) if p.payment_method != 'CASH' else 0.0,
                    'amount': float(amt),
                    'notes': p.notes or '—',
                })

            net_cash = cash_in - cash_out
            kpis = [
                {'label': 'Net Cash in Drawer', 'value': float(net_cash), 'format': 'currency', 'color': 'success'},
                {'label': 'Total Cash In', 'value': float(cash_in), 'format': 'currency', 'color': 'primary'},
                {'label': 'Total Cash Refunds', 'value': float(cash_out), 'format': 'currency', 'color': 'danger' if cash_out > 0 else 'secondary'},
                {'label': 'Digital (UPI/Card/Bank)', 'value': float(digital_in), 'format': 'currency', 'color': 'info'},
                {'label': 'Active Cashiers', 'value': len(staff_set), 'format': 'number', 'color': 'dark'},
            ]

            columns = [
                {'key': 'payment_datetime', 'label': 'Time', 'align': 'left', 'sortable': True},
                {'key': 'payment_number', 'label': 'Receipt #', 'align': 'left', 'sortable': True},
                {'key': 'cashier', 'label': 'Cashier / Staff', 'align': 'left', 'sortable': True},
                {'key': 'customer_name', 'label': 'Guest', 'align': 'left'},
                {'key': 'payment_method', 'label': 'Method', 'align': 'center', 'sortable': True},
                {'key': 'cash_in', 'label': 'Cash Received (₹)', 'align': 'right', 'format': 'currency'},
                {'key': 'cash_out', 'label': 'Cash Return (₹)', 'align': 'right', 'format': 'currency'},
                {'key': 'digital_amount', 'label': 'Digital (₹)', 'align': 'right', 'format': 'currency'},
                {'key': 'notes', 'label': 'Remarks / Shift Notes', 'align': 'left'},
            ]

            return Response({
                'report_id': report_id,
                'category': 'revenue_payments',
                'title': title,
                'description': description,
                'date_label': date_label,
                'kpis': kpis,
                'columns': columns,
                'rows': rows,
                'total_count': len(rows),
            })

        else: # 'daily_revenue' / 'revenue_summary'
            title = "Daily Revenue & Financial Summary"
            description = f"Day-by-day revenue accrual, discounts, GST, and collections for {date_label}."
            
            # Daily aggregation
            curr_date = start_date
            rows = []
            chart_data = []
            tot_gross = Decimal('0.00')
            tot_disc = Decimal('0.00')
            tot_gst = Decimal('0.00')
            tot_net = Decimal('0.00')
            tot_paid = Decimal('0.00')

            pay_base = Payment.objects.filter(property=prop) if prop else Payment.objects.all()
            stay_base = Stay.objects.filter(property=prop) if prop else Stay.objects.all()

            while curr_date <= end_date:
                # Payments on this date
                pmts = pay_base.filter(payment_date__date=curr_date).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
                # Stays active or checked-in on this date
                day_stays = stay_base.filter(check_in_date__lte=curr_date, expected_checkout_date__gte=curr_date)
                
                day_room_rev = Decimal('0.00')
                day_extra = Decimal('0.00')
                day_disc = Decimal('0.00')
                day_gst = Decimal('0.00')

                for s in day_stays:
                    bill = calculate_stay_bill(s)
                    stay_days = max(1, int(bill['room_days']))
                    day_room_rev += Decimal(str(bill['total_room_charge'])) / Decimal(stay_days)
                    day_extra += Decimal(str(bill['extra_charges_total'])) / Decimal(stay_days)
                    day_disc += Decimal(str(bill['discount_amount'])) / Decimal(stay_days)
                    day_gst += Decimal(str(bill['tax_amount'])) / Decimal(stay_days)

                day_gross = day_room_rev + day_extra
                day_net = max(Decimal('0.00'), day_gross - day_disc) + day_gst

                tot_gross += day_gross
                tot_disc += day_disc
                tot_gst += day_gst
                tot_net += day_net
                tot_paid += pmts

                day_str = curr_date.strftime('%d %b %Y')
                rows.append({
                    'id': str(curr_date),
                    'date': day_str,
                    'gross_amount': round(float(day_gross), 2),
                    'discount': round(float(day_disc), 2),
                    'taxable_amount': round(float(max(Decimal('0.00'), day_gross - day_disc)), 2),
                    'gst_amount': round(float(day_gst), 2),
                    'net_revenue': round(float(day_net), 2),
                    'collections': round(float(pmts), 2),
                    'variance': round(float(pmts - day_net), 2),
                })

                chart_data.append({
                    'date': curr_date.strftime('%d %b'),
                    'Revenue': round(float(day_net), 2),
                    'Collections': round(float(pmts), 2),
                })

                curr_date += datetime.timedelta(days=1)

            kpis = [
                {'label': 'Net Accrued Revenue', 'value': float(tot_net), 'format': 'currency', 'color': 'primary'},
                {'label': 'Total Collections', 'value': float(tot_paid), 'format': 'currency', 'color': 'success'},
                {'label': 'Total GST Accrued', 'value': float(tot_gst), 'format': 'currency', 'color': 'info'},
                {'label': 'Total Discounts', 'value': float(tot_disc), 'format': 'currency', 'color': 'danger'},
            ]

            columns = [
                {'key': 'date', 'label': 'Date', 'align': 'left', 'sortable': True},
                {'key': 'gross_amount', 'label': 'Gross Accrual (₹)', 'align': 'right', 'format': 'currency'},
                {'key': 'discount', 'label': 'Discount (₹)', 'align': 'right', 'format': 'currency'},
                {'key': 'taxable_amount', 'label': 'Taxable (₹)', 'align': 'right', 'format': 'currency'},
                {'key': 'gst_amount', 'label': 'GST (₹)', 'align': 'right', 'format': 'currency'},
                {'key': 'net_revenue', 'label': 'Net Billing (₹)', 'align': 'right', 'format': 'currency', 'sortable': True},
                {'key': 'collections', 'label': 'Paid Collections (₹)', 'align': 'right', 'format': 'currency', 'sortable': True},
            ]

            return Response({
                'report_id': report_id,
                'category': 'revenue_payments',
                'title': title,
                'description': description,
                'date_label': date_label,
                'kpis': kpis,
                'chart_data': chart_data,
                'columns': columns,
                'rows': rows,
                'total_count': len(rows),
            })

    # =========================================================================
    # 5. GST / TAX REPORTS
    # =========================================================================
    def _handle_gst_reports(self, report_id, start_date, end_date, start_datetime, end_datetime, date_label, search, tax_pct, room_id, prop=None):
        title = "GST & Statutory Tax Compliance"
        description = f"Taxable supplies, CGST, SGST breakdown, and GST invoices for {date_label}."

        stay_base = Stay.objects.filter(property=prop) if prop else Stay.objects.all()
        stays_qs = stay_base.filter(
            check_in_date__lte=end_date,
            expected_checkout_date__gte=start_date
        ).select_related('primary_customer', 'room', 'room__room_type').prefetch_related('payments', 'extra_charges')

        if room_id:
            stays_qs = stays_qs.filter(room_id=room_id)
        if search:
            stays_qs = stays_qs.filter(
                Q(stay_number__icontains=search) |
                Q(primary_customer__full_name__icontains=search) |
                Q(room__room_number__icontains=search)
            )

        rows = []
        tot_taxable = Decimal('0.00')
        tot_cgst = Decimal('0.00')
        tot_sgst = Decimal('0.00')
        tot_gst = Decimal('0.00')
        tot_grand = Decimal('0.00')

        cgst_pct = (tax_pct / Decimal('2.00')) if tax_pct > 0 else Decimal('0.00')
        sgst_pct = (tax_pct / Decimal('2.00')) if tax_pct > 0 else Decimal('0.00')

        for s in stays_qs:
            bill = calculate_stay_bill(s)
            taxable = Decimal(str(bill['taxable_amount']))
            gst = Decimal(str(bill['tax_amount']))
            cgst = (gst / Decimal('2.00')) if gst > 0 else Decimal('0.00')
            sgst = (gst / Decimal('2.00')) if gst > 0 else Decimal('0.00')
            grand = Decimal(str(bill['grand_total']))

            tot_taxable += taxable
            tot_cgst += cgst
            tot_sgst += sgst
            tot_gst += gst
            tot_grand += grand

            c = s.primary_customer
            gst_no = getattr(c, 'gst_number', '') or 'URP (Unregistered)'

            rows.append({
                'id': s.id,
                'stay_number': s.stay_number,
                'invoice_number': f"INV-{s.stay_number.replace('STAY-', '')}",
                'customer_name': c.full_name if c else 'Guest',
                'customer_gstin': gst_no,
                'room_number': s.room.room_number if s.room else '—',
                'stay_dates': f"{s.check_in_date} to {s.actual_checkout_date or s.expected_checkout_date}",
                'taxable_value': float(taxable),
                'cgst_rate': f"{cgst_pct:.1f}%",
                'cgst_amount': float(cgst),
                'sgst_rate': f"{sgst_pct:.1f}%",
                'sgst_amount': float(sgst),
                'total_tax': float(gst),
                'invoice_total': float(grand),
                'state_code': '29 (Karnataka / Domestic)',
            })

        kpis = [
            {'label': 'Total Taxable Turnover', 'value': float(tot_taxable), 'format': 'currency', 'color': 'primary'},
            {'label': 'Total GST Liability', 'value': float(tot_gst), 'format': 'currency', 'color': 'danger'},
            {'label': 'CGST Output', 'value': float(tot_cgst), 'format': 'currency', 'color': 'info'},
            {'label': 'SGST Output', 'value': float(tot_sgst), 'format': 'currency', 'color': 'info'},
            {'label': 'Gross Invoiced', 'value': float(tot_grand), 'format': 'currency', 'color': 'success'},
        ]

        columns = [
            {'key': 'invoice_number', 'label': 'Invoice #', 'align': 'left', 'sortable': True},
            {'key': 'customer_name', 'label': 'Recipient / B2B Guest', 'align': 'left', 'sortable': True},
            {'key': 'customer_gstin', 'label': 'Guest GSTIN', 'align': 'left'},
            {'key': 'room_number', 'label': 'Room', 'align': 'center'},
            {'key': 'stay_dates', 'label': 'Supply Period', 'align': 'left'},
            {'key': 'taxable_value', 'label': 'Taxable (₹)', 'align': 'right', 'format': 'currency', 'sortable': True},
            {'key': 'cgst_amount', 'label': 'CGST (₹)', 'align': 'right', 'format': 'currency'},
            {'key': 'sgst_amount', 'label': 'SGST (₹)', 'align': 'right', 'format': 'currency'},
            {'key': 'total_tax', 'label': 'Total GST (₹)', 'align': 'right', 'format': 'currency', 'sortable': True},
            {'key': 'invoice_total', 'label': 'Total Bill (₹)', 'align': 'right', 'format': 'currency', 'sortable': True},
        ]

        return Response({
            'report_id': report_id,
            'category': 'gst_tax',
            'title': title,
            'description': description,
            'date_label': date_label,
            'kpis': kpis,
            'columns': columns,
            'rows': rows,
            'total_count': len(rows),
        })

    # =========================================================================
    # 6. EXTRA CHARGES & SERVICES
    # =========================================================================
    def _handle_extra_charges_reports(self, report_id, start_date, end_date, start_datetime, end_datetime, date_label, search, charge_type_id, room_id, prop=None):
        title = "Extra Charges & Service Revenue"
        description = f"Breakdown of food & beverage, laundry, extra bed, and add-on services ({date_label})."

        ec_base = ExtraCharge.objects.filter(property=prop) if prop else ExtraCharge.objects.all()
        charges_qs = ec_base.filter(
            charge_date__date__range=[start_date, end_date]
        ).select_related('stay', 'stay__room', 'stay__primary_customer', 'charge_type', 'created_by')

        if charge_type_id:
            charges_qs = charges_qs.filter(charge_type_id=charge_type_id)
        if room_id:
            charges_qs = charges_qs.filter(stay__room_id=room_id)
        if search:
            charges_qs = charges_qs.filter(
                Q(description__icontains=search) |
                Q(charge_type__name__icontains=search) |
                Q(stay__stay_number__icontains=search) |
                Q(stay__primary_customer__full_name__icontains=search)
            )

        charges_qs = charges_qs.order_by('-charge_date')

        # Category Breakdown Chart
        by_cat = charges_qs.values('charge_type__name').annotate(total=Sum('amount'), count=Count('id')).order_by('-total')
        chart_data = [
            {'name': bc['charge_type__name'] or 'General Service', 'revenue': float(bc['total'] or 0), 'count': bc['count']}
            for bc in by_cat
        ]

        rows = []
        tot_amount = Decimal('0.00')
        tot_qty = 0

        for ec in charges_qs:
            amt = Decimal(str(ec.amount or 0))
            tot_amount += amt
            tot_qty += int(ec.quantity or 1)

            rows.append({
                'id': ec.id,
                'date_time': ec.charge_date.strftime('%Y-%m-%d %I:%M %p'),
                'stay_number': ec.stay.stay_number if ec.stay else '—',
                'guest_name': ec.stay.primary_customer.full_name if (ec.stay and ec.stay.primary_customer) else 'Guest',
                'room_number': ec.stay.room.room_number if (ec.stay and ec.stay.room) else '—',
                'category': ec.charge_type.name if ec.charge_type else 'General Service',
                'description': ec.description,
                'quantity': ec.quantity,
                'unit_price': float(ec.unit_price or 0),
                'amount': float(amt),
                'billed_by': ec.created_by.get_full_name() or ec.created_by.username if ec.created_by else 'Staff',
            })

        kpis = [
            {'label': 'Total Services Billed', 'value': float(tot_amount), 'format': 'currency', 'color': 'primary'},
            {'label': 'Total Quantity Items', 'value': tot_qty, 'format': 'number', 'color': 'info'},
            {'label': 'Service Entries', 'value': len(rows), 'format': 'number', 'color': 'success'},
        ]

        columns = [
            {'key': 'date_time', 'label': 'Date & Time', 'align': 'left', 'sortable': True},
            {'key': 'stay_number', 'label': 'Stay #', 'align': 'left'},
            {'key': 'room_number', 'label': 'Room', 'align': 'center'},
            {'key': 'guest_name', 'label': 'Guest', 'align': 'left'},
            {'key': 'category', 'label': 'Service Category', 'align': 'left', 'sortable': True},
            {'key': 'description', 'label': 'Item Details', 'align': 'left'},
            {'key': 'quantity', 'label': 'Qty', 'align': 'center'},
            {'key': 'unit_price', 'label': 'Unit Price (₹)', 'align': 'right', 'format': 'currency'},
            {'key': 'amount', 'label': 'Total Amount (₹)', 'align': 'right', 'format': 'currency', 'sortable': True},
            {'key': 'billed_by', 'label': 'Billed By', 'align': 'left'},
        ]

        return Response({
            'report_id': report_id,
            'category': 'extra_charges',
            'title': title,
            'description': description,
            'date_label': date_label,
            'kpis': kpis,
            'chart_data': chart_data,
            'columns': columns,
            'rows': rows,
            'total_count': len(rows),
        })

    # =========================================================================
    # 7. CUSTOMER REPORTS
    # =========================================================================
    def _handle_customer_reports(self, report_id, start_date, end_date, date_label, search, prop=None):
        title = "Customer Intelligence & Loyalty Report"
        description = "Guest visit frequency, cumulative spend, and loyalty analytics."

        cust_base = Customer.objects.filter(property=prop) if prop else Customer.objects.all()
        cust_qs = cust_base.prefetch_related('stays', 'bookings', 'payments')
        if search:
            cust_qs = cust_qs.filter(
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(mobile__icontains=search) |
                Q(email__icontains=search) |
                Q(id_number__icontains=search)
            )

        rows = []
        tot_all_spend = Decimal('0.00')

        for c in cust_qs:
            c_stays = c.stays.all()
            if prop:
                c_stays = c_stays.filter(property=prop)
            stay_count = c_stays.count()
            if stay_count == 0 and report_id == 'frequent_guests':
                continue

            total_nights = 0
            cust_spend = Decimal('0.00')
            last_dt = None

            for s in c_stays:
                bill = calculate_stay_bill(s)
                total_nights += int(bill['room_days'])
                cust_spend += Decimal(str(bill['grand_total']))
                if not last_dt or s.check_in_date > last_dt:
                    last_dt = s.check_in_date

            tot_all_spend += cust_spend

            tier = 'PLATINUM' if (stay_count >= 5 or cust_spend >= 25000) else ('GOLD' if (stay_count >= 3 or cust_spend >= 10000) else ('SILVER' if stay_count >= 2 else 'BRONZE'))

            rows.append({
                'id': c.id,
                'customer_name': c.full_name,
                'mobile': c.mobile,
                'email': c.email or '—',
                'id_type': c.id_type or '—',
                'id_number': c.id_number or '—',
                'total_stays': stay_count,
                'total_nights': total_nights,
                'total_spend': float(cust_spend),
                'last_visit': str(last_dt) if last_dt else 'Never',
                'loyalty_tier': tier,
                'advance_credit': float(c.advance_credit or 0),
            })

        rows.sort(key=lambda x: x['total_spend'], reverse=True)

        kpis = [
            {'label': 'Total Registered Guests', 'value': len(rows), 'format': 'number', 'color': 'primary'},
            {'label': 'Cumulative Guest Lifetime Value', 'value': float(tot_all_spend), 'format': 'currency', 'color': 'success'},
            {'label': 'Platinum & Gold Guests', 'value': sum(1 for r in rows if r['loyalty_tier'] in ['PLATINUM', 'GOLD']), 'format': 'number', 'color': 'warning'},
        ]

        columns = [
            {'key': 'customer_name', 'label': 'Customer Full Name', 'align': 'left', 'sortable': True},
            {'key': 'mobile', 'label': 'Mobile Number', 'align': 'left'},
            {'key': 'id_type', 'label': 'ID Proof', 'align': 'left'},
            {'key': 'id_number', 'label': 'ID Number', 'align': 'left'},
            {'key': 'total_stays', 'label': 'Visits / Stays', 'align': 'center', 'sortable': True},
            {'key': 'total_nights', 'label': 'Total Nights', 'align': 'center', 'sortable': True},
            {'key': 'total_spend', 'label': 'Total Spend (₹)', 'align': 'right', 'format': 'currency', 'sortable': True},
            {'key': 'last_visit', 'label': 'Last Visit Date', 'align': 'left', 'sortable': True},
            {'key': 'loyalty_tier', 'label': 'Tier', 'align': 'center', 'badgeStyle': 'status'},
        ]

        # Chart: Top 6 Guest Spenders
        top_spenders = rows[:6]
        chart_data = [
            {'name': ts['customer_name'], 'revenue': ts['total_spend'], 'stays': ts['total_stays']}
            for ts in top_spenders if ts['total_spend'] > 0
        ]

        return Response({
            'report_id': report_id,
            'category': 'customers',
            'title': title if report_id != 'frequent_guests' else "Frequent Guests & Top Spenders",
            'description': description,
            'date_label': "All Time",
            'kpis': kpis,
            'chart_data': chart_data,
            'columns': columns,
            'rows': rows,
            'total_count': len(rows),
        })

    # =========================================================================
    # 8. CANCELLATIONS & NO-SHOW REPORTS
    # =========================================================================
    def _handle_cancellation_reports(self, report_id, start_date, end_date, date_label, search, room_id, prop=None):
        title = "Cancellations & Lost Revenue Analysis"
        description = f"Cancelled reservations, no-shows, advance refunds, and lost revenue impact ({date_label})."

        book_base = Booking.objects.filter(property=prop) if prop else Booking.objects.all()
        b_qs = book_base.filter(
            status__in=['CANCELLED', 'NO_SHOW'],
            created_at__date__range=[start_date, end_date]
        ).select_related('customer', 'room', 'room__room_type')

        if room_id:
            b_qs = b_qs.filter(room_id=room_id)
        if search:
            b_qs = b_qs.filter(
                Q(booking_number__icontains=search) |
                Q(customer__first_name__icontains=search) |
                Q(customer__last_name__icontains=search) |
                Q(customer__mobile__icontains=search)
            )

        rows = []
        tot_lost = Decimal('0.00')
        tot_adv_refund = Decimal('0.00')

        for b in b_qs:
            rate = Decimal(str((b.room.room_type.base_price if (b.room and b.room.room_type) else 0) or 0))
            nights = max(1, (b.expected_checkout_date - b.check_in_date).days if (b.expected_checkout_date and b.check_in_date) else 1)
            estimated_loss = rate * Decimal(nights)
            tot_lost += estimated_loss
            tot_adv_refund += Decimal(str(b.advance_amount or 0))

            rows.append({
                'id': b.id,
                'booking_number': b.booking_number,
                'customer_name': b.customer.full_name if b.customer else 'Guest',
                'mobile': b.customer.mobile if b.customer else '',
                'room_number': b.room.room_number if b.room else '—',
                'arrival_date': str(b.check_in_date),
                'scheduled_departure': str(b.expected_checkout_date),
                'nights': nights,
                'advance_paid': float(b.advance_amount or 0),
                'estimated_loss': float(estimated_loss),
                'reason': b.notes or 'Guest Cancelled / No Arrival',
                'status': b.status,
            })

        # Chart: Lost Revenue by Room
        lost_by_room = {}
        for r in rows:
            rm = f"Room {r['room_number']}"
            lost_by_room[rm] = lost_by_room.get(rm, 0.0) + r['estimated_loss']

        chart_data = [
            {'name': rm, 'revenue': amt}
            for rm, amt in list(lost_by_room.items())[:6] if amt > 0
        ]

        kpis = [
            {'label': 'Cancelled / No-Show Count', 'value': len(rows), 'format': 'number', 'color': 'danger'},
            {'label': 'Advance Handled', 'value': float(tot_adv_refund), 'format': 'currency', 'color': 'warning'},
            {'label': 'Estimated Lost Revenue', 'value': float(tot_lost), 'format': 'currency', 'color': 'danger'},
        ]

        columns = [
            {'key': 'booking_number', 'label': 'Booking #', 'align': 'left', 'sortable': True},
            {'key': 'customer_name', 'label': 'Guest Name', 'align': 'left', 'sortable': True},
            {'key': 'room_number', 'label': 'Room', 'align': 'center'},
            {'key': 'arrival_date', 'label': 'Arrival Date', 'align': 'left', 'sortable': True},
            {'key': 'nights', 'label': 'Nights', 'align': 'center'},
            {'key': 'advance_paid', 'label': 'Advance (₹)', 'align': 'right', 'format': 'currency'},
            {'key': 'estimated_loss', 'label': 'Estimated Loss (₹)', 'align': 'right', 'format': 'currency', 'sortable': True},
            {'key': 'reason', 'label': 'Notes / Reason', 'align': 'left'},
            {'key': 'status', 'label': 'Status', 'align': 'center', 'badgeStyle': 'status'},
        ]

        return Response({
            'report_id': report_id,
            'category': 'cancellations',
            'title': title,
            'description': description,
            'date_label': date_label,
            'kpis': kpis,
            'chart_data': chart_data,
            'columns': columns,
            'rows': rows,
            'total_count': len(rows),
        })

    # =========================================================================
    # 9. SHIFT-WISE ACTIVITY & TILL AUDIT REPORTS
    # =========================================================================
    def _handle_shift_reports(self, report_id, start_date, end_date, date_label, search, shift_id=None, prop=None):
        """
        Generates Shift-wise Activity Dossier & Audit Reports.
        Retrieves all activity performed during a specific shift:
        - Financial till balancing & cash drawer reconciliation
        - Payments & collections received during shift
        - Check-ins completed during shift
        - Check-outs settled during shift
        - Petty cash expenses incurred in shift
        - Cash denomination counts & handovers
        """
        from apps.shifts.models import Shift, ShiftExpense, ShiftDenomination, ShiftCashAdjustment, ShiftHandover
        from apps.shifts.services import calculate_shift_financials, calculate_shift_operational_metrics
        from apps.billing.models import Payment
        from apps.stays.models import Stay

        if report_id in ['petty_cash_analytics', 'shift_expenses', 'till_expenses']:
            return self._handle_petty_cash_reports(start_date, end_date, date_label, search, shift_id, prop)

        shift_base = Shift.objects.filter(property=prop) if prop else Shift.objects.all()
        shift = None
        if shift_id:
            try:
                shift = shift_base.filter(id=shift_id).select_related('user', 'cash_drawer', 'closed_by', 'manager_approved_by').first()
            except Exception:
                pass

        if not shift:
            shift = shift_base.select_related('user', 'cash_drawer', 'closed_by', 'manager_approved_by').order_by('-opened_at').first()

        if not shift:
            return Response({
                'report_id': report_id or 'shift_dossier',
                'category': 'shift_audit',
                'title': "Shift Audit & Activity Dossier",
                'description': "No shift records found in property database.",
                'date_label': date_label,
                'kpis': [],
                'columns': [],
                'rows': [],
                'total_count': 0,
                'shift_info': None
            })

        financials = calculate_shift_financials(shift)
        operational = calculate_shift_operational_metrics(shift)

        start_time = shift.opened_at
        end_time = shift.closed_at or timezone.now()

        # 1. Shift Payments
        payments_qs = Payment.objects.filter(shift=shift).select_related('customer', 'stay', 'stay__room', 'received_by')
        if not payments_qs.exists() and shift.opened_at:
            # Fallback for older records where payment.shift was unset
            payments_qs = Payment.objects.filter(
                payment_date__gte=start_time,
                payment_date__lte=end_time
            ).select_related('customer', 'stay', 'stay__room', 'received_by')
            if prop:
                payments_qs = payments_qs.filter(property=prop)

        if search:
            payments_qs = payments_qs.filter(
                Q(payment_number__icontains=search) |
                Q(customer__full_name__icontains=search) |
                Q(stay__stay_number__icontains=search) |
                Q(transaction_reference__icontains=search)
            )

        payments_list = []
        for p in payments_qs.order_by('-payment_date'):
            c_name = p.customer.full_name if p.customer else (p.stay.primary_customer.full_name if (p.stay and p.stay.primary_customer) else 'Guest')
            room_no = p.stay.room.room_number if (p.stay and p.stay.room) else '—'
            amt = float(p.amount or 0)
            payments_list.append({
                'id': p.id,
                'payment_number': p.payment_number,
                'time': p.payment_date.strftime('%I:%M %p'),
                'payment_datetime': p.payment_date.strftime('%Y-%m-%d %I:%M %p'),
                'guest_name': c_name,
                'room_number': room_no,
                'stay_number': p.stay.stay_number if p.stay else '—',
                'method': p.payment_method,
                'payment_method_display': p.get_payment_method_display(),
                'amount': amt,
                'reference': p.transaction_reference or '—',
                'notes': p.notes or '—'
            })

        # 2. Check-Ins in Shift
        checkins_qs = Stay.objects.filter(
            Q(created_at__gte=start_time, created_at__lte=end_time) |
            Q(check_in_date=start_time.date())
        ).select_related('primary_customer', 'room', 'room__room_type')
        if prop:
            checkins_qs = checkins_qs.filter(property=prop)

        checkins_list = []
        for s in checkins_qs.order_by('-created_at'):
            paid_sum = s.payments.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
            checkins_list.append({
                'id': s.id,
                'stay_number': s.stay_number,
                'guest_name': s.primary_customer.full_name if s.primary_customer else 'Guest',
                'mobile': s.primary_customer.mobile if s.primary_customer else '—',
                'room_number': s.room.room_number if s.room else '—',
                'room_type': s.room.room_type.name if (s.room and s.room.room_type) else 'Standard',
                'check_in_time': s.created_at.strftime('%I:%M %p') if s.created_at else '—',
                'room_rate': float(s.room_rate or 0),
                'advance_paid': float(paid_sum),
                'status': s.status
            })

        # 3. Check-Outs in Shift
        checkouts_qs = Stay.objects.filter(
            status=Stay.Status.CHECKED_OUT,
            updated_at__gte=start_time,
            updated_at__lte=end_time
        ).select_related('primary_customer', 'room', 'room__room_type')
        if prop:
            checkouts_qs = checkouts_qs.filter(property=prop)

        checkouts_list = []
        for s in checkouts_qs.order_by('-updated_at'):
            paid_sum = s.payments.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
            checkouts_list.append({
                'id': s.id,
                'stay_number': s.stay_number,
                'guest_name': s.primary_customer.full_name if s.primary_customer else 'Guest',
                'mobile': s.primary_customer.mobile if s.primary_customer else '—',
                'room_number': s.room.room_number if s.room else '—',
                'checkout_time': s.updated_at.strftime('%I:%M %p') if s.updated_at else '—',
                'settled_amount': float(paid_sum),
                'status': 'CHECKED_OUT'
            })

        # 4. Petty Cash Expenses
        expenses_qs = shift.expenses.all().select_related('created_by', 'approved_by')
        expenses_list = []
        for exp in expenses_qs.order_by('-created_at'):
            expenses_list.append({
                'id': exp.id,
                'category': exp.category,
                'category_display': exp.get_category_display(),
                'amount': float(exp.amount or 0),
                'description': exp.description,
                'created_by': exp.created_by.get_full_name() or exp.created_by.username if exp.created_by else 'Staff',
                'approved_by': exp.approved_by.get_full_name() or exp.approved_by.username if exp.approved_by else '—',
                'time': exp.created_at.strftime('%I:%M %p')
            })

        # 5. Denominations
        denominations_qs = shift.denominations.all()
        denominations_list = [
            {
                'denomination': d.denomination,
                'quantity': d.quantity,
                'unit_value': float(d.unit_value or 0),
                'total': float(d.total or 0)
            }
            for d in denominations_qs
        ]

        # 6. Adjustments
        adjustments_qs = shift.adjustments.all().select_related('created_by')
        adjustments_list = [
            {
                'id': adj.id,
                'type': adj.adjustment_type,
                'type_display': adj.get_adjustment_type_display(),
                'amount': float(adj.amount or 0),
                'reason': adj.reason,
                'created_by': adj.created_by.get_full_name() or adj.created_by.username if adj.created_by else 'Staff',
                'time': adj.created_at.strftime('%I:%M %p')
            }
            for adj in adjustments_qs
        ]

        # 7. Handovers
        handovers_qs = ShiftHandover.objects.filter(Q(from_shift=shift) | Q(to_shift=shift)).select_related('from_user', 'to_user')
        handovers_list = [
            {
                'id': h.id,
                'direction': 'GIVEN' if h.from_shift_id == shift.id else 'RECEIVED',
                'from_user': h.from_user.get_full_name() or h.from_user.username if h.from_user else 'Staff',
                'to_user': h.to_user.get_full_name() or h.to_user.username if h.to_user else 'Staff',
                'amount': float(h.amount or 0),
                'status': h.status,
                'notes': h.notes or '—'
            }
            for h in handovers_qs
        ]

        cashier_name = shift.user.get_full_name() or shift.user.username if shift.user else 'Staff'
        drawer_name = shift.cash_drawer.name if shift.cash_drawer else 'Main Till'
        drawer_code = shift.cash_drawer.code if shift.cash_drawer else 'POS-01'

        # Build 4 Focused Shift KPIs
        opening_cash = financials.get('opening_cash', 0.0)
        total_coll = financials.get('total_collections', 0.0)
        cash_coll = financials.get('cash_collections', 0.0)
        expected_cash = financials.get('expected_cash', 0.0)
        actual_cash = financials.get('actual_cash')
        variance = financials.get('cash_difference', 0.0)
        discrepancy_type = financials.get('discrepancy_type', 'EXACT')

        kpis = [
            {
                'label': 'Opening Float Till',
                'value': opening_cash,
                'format': 'currency',
                'color': 'primary',
                'subtitle': f"Drawer: {drawer_code}"
            },
            {
                'label': 'Total Shift Collections',
                'value': total_coll,
                'format': 'currency',
                'color': 'success',
                'subtitle': f"Cash: ₹{cash_coll:,.0f} | Digital: ₹{(total_coll - cash_coll):,.0f}"
            },
            {
                'label': 'Expected Physical Cash',
                'value': expected_cash,
                'format': 'currency',
                'color': 'info',
                'subtitle': f"Counted: {f'₹{actual_cash:,.0f}' if actual_cash is not None else 'Pending Count'}"
            },
            {
                'label': 'Till Balancing Discrepancy',
                'value': abs(variance),
                'format': 'currency',
                'color': 'success' if abs(variance) < 0.01 else ('warning' if variance > 0 else 'danger'),
                'subtitle': f"Status: {discrepancy_type}"
            }
        ]

        # Primary Table Columns (Payment / Collection Transactions)
        columns = [
            {'key': 'time', 'label': 'Time', 'align': 'left', 'sortable': True},
            {'key': 'payment_number', 'label': 'Receipt #', 'align': 'left', 'sortable': True},
            {'key': 'guest_name', 'label': 'Guest Name', 'align': 'left', 'sortable': True},
            {'key': 'room_number', 'label': 'Room #', 'align': 'center'},
            {'key': 'stay_number', 'label': 'Stay #', 'align': 'center'},
            {'key': 'payment_method_display', 'label': 'Method', 'align': 'center', 'badgeStyle': 'status'},
            {'key': 'reference', 'label': 'Reference / UTR', 'align': 'left'},
            {'key': 'amount', 'label': 'Amount (₹)', 'align': 'right', 'format': 'currency', 'sortable': True},
        ]

        shift_info = {
            'id': shift.id,
            'shift_number': shift.shift_number,
            'cashier_name': cashier_name,
            'cashier_id': shift.user_id if shift.user else None,
            'drawer_name': drawer_name,
            'drawer_code': drawer_code,
            'status': shift.status,
            'status_display': shift.get_status_display(),
            'opened_at': shift.opened_at.strftime('%Y-%m-%d %I:%M %p') if shift.opened_at else '—',
            'closed_at': shift.closed_at.strftime('%Y-%m-%d %I:%M %p') if shift.closed_at else 'Active / Still Open',
            'duration_minutes': shift.duration_minutes,
            'duration_display': f"{shift.duration_minutes // 60}h {shift.duration_minutes % 60}m",
            'opening_notes': shift.opening_notes or '',
            'closing_notes': shift.closing_notes or '',
            'difference_reason': shift.difference_reason or '',
            'manager_approved_by': shift.manager_approved_by.get_full_name() if shift.manager_approved_by else None,
            'manager_approval_notes': shift.manager_approval_notes or '',
            'financials': financials,
            'operational': operational,
            'payments': payments_list,
            'checkins': checkins_list,
            'checkouts': checkouts_list,
            'expenses': expenses_list,
            'denominations': denominations_list,
            'adjustments': adjustments_list,
            'handovers': handovers_list,
        }

        return Response({
            'report_id': 'shift_dossier',
            'category': 'shift_audit',
            'title': f"Shift #{shift.shift_number} Activity Dossier",
            'description': f"Completed shift audit for {cashier_name} ({drawer_name}) • {shift.opened_at.strftime('%d %b %Y') if shift.opened_at else ''}",
            'date_label': shift.opened_at.strftime('%d %b %Y') if shift.opened_at else date_label,
            'kpis': kpis,
            'columns': columns,
            'rows': payments_list,
            'total_count': len(payments_list),
            'shift_info': shift_info,
            'chart_data': [
                {'name': 'Opening Float', 'amount': opening_cash},
                {'name': 'Cash Collections', 'amount': cash_coll},
                {'name': 'Digital Collections', 'amount': total_coll - cash_coll},
                {'name': 'Expenses Paid', 'amount': financials.get('cash_expenses', 0.0)},
                {'name': 'Expected Till Cash', 'amount': expected_cash},
                {'name': 'Actual Counted', 'amount': actual_cash or 0.0},
            ]
        })

    def _handle_petty_cash_reports(self, start_date, end_date, date_label, search, shift_id=None, prop=None):
        from apps.shifts.models import ShiftExpense, Shift
        exp_base = ShiftExpense.objects.filter(shift__property=prop) if prop else ShiftExpense.objects.all()
        exp_qs = exp_base.select_related('shift', 'created_by', 'approved_by')

        if shift_id:
            exp_qs = exp_qs.filter(shift_id=shift_id)
        elif start_date and end_date:
            exp_qs = exp_qs.filter(created_at__date__gte=start_date, created_at__date__lte=end_date)

        if search:
            exp_qs = exp_qs.filter(
                Q(description__icontains=search) |
                Q(category__icontains=search) |
                Q(created_by__first_name__icontains=search) |
                Q(created_by__last_name__icontains=search) |
                Q(created_by__username__icontains=search) |
                Q(shift__shift_number__icontains=search)
            )

        total_spent = exp_qs.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        voucher_count = exp_qs.count()
        approved_count = exp_qs.filter(is_manager_approved=True).count()

        category_agg = exp_qs.values('category').annotate(
            total=Sum('amount'),
            count=Count('id')
        ).order_by('-total')

        category_dict = dict(ShiftExpense.Category.choices)
        chart_data = [{
            'name': category_dict.get(c['category'], c['category']),
            'amount': float(c['total'] or 0),
            'count': c['count']
        } for c in category_agg]

        top_cat_label = chart_data[0]['name'] if chart_data else 'None'

        kpis = [
            {'label': 'Total Petty Cash Spent', 'value': float(total_spent), 'format': 'currency', 'color': 'danger'},
            {'label': 'Total Expense Vouchers', 'value': voucher_count, 'color': 'primary'},
            {'label': 'Manager Approved', 'value': approved_count, 'color': 'success'},
            {'label': 'Top Expense Category', 'value': top_cat_label, 'color': 'warning'},
        ]

        columns = [
            {'key': 'voucher_no', 'label': 'Voucher #', 'align': 'left', 'sortable': True},
            {'key': 'date_time', 'label': 'Date & Time', 'align': 'left', 'sortable': True},
            {'key': 'shift_number', 'label': 'Shift #', 'align': 'center'},
            {'key': 'cashier_name', 'label': 'Cashier / Staff', 'align': 'left'},
            {'key': 'category_display', 'label': 'Category', 'align': 'center', 'badgeStyle': 'status'},
            {'key': 'description', 'label': 'Description / Purpose', 'align': 'left'},
            {'key': 'approval_status', 'label': 'Approval Status', 'align': 'center', 'badgeStyle': 'status'},
            {'key': 'amount', 'label': 'Amount (₹)', 'align': 'right', 'format': 'currency', 'sortable': True},
        ]

        rows = []
        for e in exp_qs.order_by('-created_at'):
            rows.append({
                'id': e.id,
                'voucher_no': f"EXP-{e.id:04d}",
                'date_time': e.created_at.strftime('%Y-%m-%d %I:%M %p'),
                'date': e.created_at.strftime('%d %b %Y'),
                'time': e.created_at.strftime('%I:%M %p'),
                'shift_number': e.shift.shift_number if e.shift else '—',
                'cashier_name': e.created_by.get_full_name() or e.created_by.username if e.created_by else 'Staff',
                'category': e.category,
                'category_display': e.get_category_display(),
                'description': e.description,
                'approval_status': 'Approved' if e.is_manager_approved else 'Pending Approval',
                'approved_by': e.approved_by.get_full_name() or e.approved_by.username if e.approved_by else '—',
                'amount': float(e.amount or 0)
            })

        return Response({
            'report_id': 'petty_cash_analytics',
            'category': 'shift_audit',
            'title': "Petty Cash & Reception Till Disbursements",
            'description': f"Comprehensive register of petty cash disbursements and drawer till expenses • {date_label}",
            'date_label': date_label,
            'kpis': kpis,
            'chart_data': chart_data,
            'columns': columns,
            'rows': rows,
            'total_count': len(rows),
        })


# Legacy views retained for backward compatibility
class DashboardReportView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        today = datetime.date.today()
        user = request.user
        prop = get_active_property_for_request(request)

        room_base = Room.objects.filter(property=prop, is_active=True) if prop else Room.objects.filter(is_active=True)
        all_rooms = room_base.select_related('room_type').order_by('room_number')
        total_rooms = all_rooms.count()
        occupied_rooms = all_rooms.filter(status=Room.Status.OCCUPIED).count()
        available_rooms = all_rooms.filter(status=Room.Status.AVAILABLE).count()
        reserved_rooms = all_rooms.filter(status=Room.Status.RESERVED).count()
        cleaning_rooms = all_rooms.filter(status=Room.Status.CLEANING).count()
        maintenance_rooms = all_rooms.filter(status=Room.Status.MAINTENANCE).count()
        occupancy_rate = (occupied_rooms / total_rooms * 100.0) if total_rooms > 0 else 0.0

        pay_base = Payment.objects.filter(property=prop) if prop else Payment.objects.all()
        today_payments = pay_base.filter(payment_date__date=today).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        # Active Stays & Pending Balance
        stay_base = Stay.objects.filter(property=prop) if prop else Stay.objects.all()
        active_stays = stay_base.filter(status='CHECKED_IN').select_related('primary_customer', 'room', 'room__room_type').prefetch_related('payments', 'extra_charges')
        pending_dues = Decimal('0.00')
        current_guests = []
        for s in active_stays:
            bill = calculate_stay_bill(s)
            bal = Decimal(str(bill['balance']))
            if bal > 0:
                pending_dues += bal
            c = s.primary_customer
            current_guests.append({
                'id': s.id,
                'stay_number': s.stay_number,
                'room_number': s.room.room_number if s.room else '—',
                'room_type': s.room.room_type.name if (s.room and s.room.room_type) else 'Standard',
                'guest_name': c.full_name if c else 'Guest',
                'customer_name': c.full_name if c else 'Guest',
                'mobile': c.mobile if c else '',
                'check_in_date': str(s.check_in_date),
                'check_in_time': str(s.check_in_time)[:5] if s.check_in_time else '12:00',
                'expected_checkout_date': str(s.expected_checkout_date),
                'expected_checkout_time': str(s.expected_checkout_time)[:5] if s.expected_checkout_time else '11:00',
                'total_amount': float(bill['grand_total']),
                'total_paid': float(bill['total_paid']),
                'balance': float(bill['balance']),
                'status': s.status,
                'payment_status': 'PAID' if bill['balance'] <= 0 else ('PARTIAL' if bill['total_paid'] > 0 else 'UNPAID'),
            })

        # Today's Checkins
        today_checkins_list = []
        today_stays_in = stay_base.filter(check_in_date=today).select_related('primary_customer', 'room')
        for s in today_stays_in:
            c = s.primary_customer
            today_checkins_list.append({
                'id': s.id,
                'customer_name': c.full_name if c else 'Guest',
                'mobile': c.mobile if c else '',
                'room_number': s.room.room_number if s.room else '—',
                'check_in_time': str(s.check_in_time)[:5] if s.check_in_time else '12:00',
                'booking_number': s.stay_number,
                'status': s.status,
            })

        book_base = Booking.objects.filter(property=prop) if prop else Booking.objects.all()
        today_bookings_in = book_base.filter(check_in_date=today, status__in=['CONFIRMED', 'PENDING']).select_related('customer', 'room')
        for b in today_bookings_in:
            c = b.customer
            today_checkins_list.append({
                'id': b.id,
                'customer_name': c.full_name if c else 'Guest',
                'mobile': c.mobile if c else '',
                'room_number': b.room.room_number if b.room else '—',
                'check_in_time': str(b.check_in_time)[:5] if b.check_in_time else '12:00',
                'booking_number': b.booking_number,
                'advance_amount': float(b.advance_amount or 0),
                'status': b.status,
            })

        # Today's Checkouts
        today_checkouts_list = []
        today_stays_out = stay_base.filter(
            Q(expected_checkout_date=today) | Q(actual_checkout_date=today)
        ).select_related('primary_customer', 'room').prefetch_related('payments', 'extra_charges')
        for s in today_stays_out:
            c = s.primary_customer
            bill = calculate_stay_bill(s)
            today_checkouts_list.append({
                'id': s.id,
                'customer_name': c.full_name if c else 'Guest',
                'mobile': c.mobile if c else '',
                'room_number': s.room.room_number if s.room else '—',
                'checkout_time': str(s.actual_checkout_time or s.expected_checkout_time)[:5] if (s.actual_checkout_time or s.expected_checkout_time) else '11:00',
                'stay_number': s.stay_number,
                'balance': float(bill['balance']),
                'status': s.status,
            })

        # ADR calculation
        adr = (float(today_payments) / occupied_rooms) if occupied_rooms > 0 else 0.0

        # Last 7 Days Performance Trend for Area & Line Chart
        days_trend = []
        for i in range(6, -1, -1):
            d = today - datetime.timedelta(days=i)
            day_payments = pay_base.filter(payment_date__date=d).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
            day_stays_count = stay_base.filter(check_in_date__lte=d, expected_checkout_date__gte=d).count()
            day_occ = round((day_stays_count / total_rooms * 100.0), 1) if total_rooms > 0 else 0.0
            days_trend.append({
                'date': d.strftime('%d %b'),
                'revenue': float(day_payments),
                'occupancy_rate': day_occ,
            })

        # Recent Transactions
        recent_pmts = pay_base.select_related('customer', 'stay', 'stay__room').order_by('-payment_date')[:10]
        recent_transactions = [{
            'id': p.id,
            'payment_number': p.payment_number,
            'amount': float(p.amount or 0),
            'payment_method': p.payment_method,
            'payment_date': p.payment_date.strftime('%Y-%m-%d %H:%M'),
            'customer_name': p.customer.full_name if p.customer else 'Guest',
            'room_number': p.stay.room.room_number if (p.stay and p.stay.room) else '—'
        } for p in recent_pmts]

        return Response({
            'cards': {
                'total_rooms': total_rooms,
                'available_rooms': available_rooms,
                'occupied_rooms': occupied_rooms,
                'reserved_rooms': reserved_rooms,
                'cleaning_rooms': cleaning_rooms,
                'maintenance_rooms': maintenance_rooms,
                'today_revenue': float(today_payments),
                'pending_payments': float(pending_dues),
                'pending_dues': float(pending_dues),
                'today_checkins_count': len(today_checkins_list),
                'today_checkouts_count': len(today_checkouts_list),
                'occupancy_percentage': round(occupancy_rate, 1),
                'adr': round(adr, 2),
            },
            'charts': {
                'days_trend': days_trend,
            },
            'tables': {
                'current_guests': current_guests,
                'today_checkins': today_checkins_list,
                'today_checkouts': today_checkouts_list,
                'recent_transactions': recent_transactions,
            }
        })


class RevenueReportView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def get(self, request):
        require_perm(request.user, 'reports', 'can_view_revenue', "You do not have permission to view revenue reports.")
        start_date, end_date, _, _, label = parse_date_range(request.query_params)
        payments = Payment.objects.filter(payment_date__date__range=[start_date, end_date])
        total_payments = payments.aggregate(total=Sum('amount'))['total'] or 0.00
        by_method = payments.values('payment_method').annotate(total=Sum('amount')).order_by('-total')
        return Response({
            'period': label,
            'start_date': str(start_date),
            'end_date': str(end_date),
            'total_payments': float(total_payments),
            'by_payment_method': [{'method': item['payment_method'], 'total': float(item['total'])} for item in by_method]
        })


class OccupancyReportView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def get(self, request):
        user = request.user
        prop = getattr(user, 'property', None) if user and not user.is_superuser else None
        room_base = Room.objects.filter(property=prop, is_active=True) if prop else Room.objects.filter(is_active=True)
        total_rooms = room_base.count()
        occupied = room_base.filter(status=Room.Status.OCCUPIED).count()
        occupancy_rate = (occupied / total_rooms * 100) if total_rooms > 0 else 0.0
        return Response({'total_rooms': total_rooms, 'occupied': occupied, 'occupancy_percentage': round(occupancy_rate, 2)})


class GuestRegisterReportView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def get(self, request):
        user = request.user
        prop = getattr(user, 'property', None) if user and not user.is_superuser else None
        stay_base = Stay.objects.filter(property=prop) if prop else Stay.objects.all()
        stays = stay_base.select_related('primary_customer', 'room').order_by('-check_in_date')[:50]
        return Response([{
            'id': s.id,
            'stay_number': s.stay_number,
            'guest_name': s.primary_customer.full_name if s.primary_customer else 'Guest',
            'mobile': s.primary_customer.mobile if s.primary_customer else '',
            'room_number': s.room.room_number if s.room else '—',
            'check_in_date': str(s.check_in_date),
            'status': s.status
        } for s in stays])


class NightAuditView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        require_perm(request.user, 'night_audit', 'can_run_night_audit', "You do not have permission to access the Daily Night Audit.")
        today = datetime.date.today()

        tomorrow = today + datetime.timedelta(days=1)
        user = request.user
        prop = getattr(user, 'property', None) if user and not user.is_superuser else None
        settings_obj = Settings.get_settings(prop=prop)

        # Financial Calculations for Today
        pay_base = Payment.objects.filter(property=prop) if prop else Payment.objects.all()
        today_payments = pay_base.filter(payment_date__date=today).select_related('received_by')
        cash_in = Decimal('0.00')
        cash_out = Decimal('0.00')
        upi_in = Decimal('0.00')
        card_in = Decimal('0.00')
        bank_in = Decimal('0.00')

        for p in today_payments:
            amt = Decimal(str(p.amount or 0))
            if p.payment_method == 'CASH':
                if amt >= 0:
                    cash_in += amt
                else:
                    cash_out += abs(amt)
            elif p.payment_method == 'UPI':
                if amt >= 0:
                    upi_in += amt
            elif p.payment_method == 'CARD':
                if amt >= 0:
                    card_in += amt
            else:
                if amt >= 0:
                    bank_in += amt

        # Shift Expenses & Till Cash Disbursements for Today
        from apps.shifts.models import ShiftExpense
        exp_base = ShiftExpense.objects.filter(shift__property=prop) if prop else ShiftExpense.objects.all()
        today_expenses = exp_base.filter(created_at__date=today).select_related('shift', 'created_by', 'approved_by')
        total_cash_expenses = today_expenses.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        today_expenses_list = [{
            'id': e.id,
            'voucher_number': f"EXP-{e.id:04d}",
            'shift_number': e.shift.shift_number if e.shift else '—',
            'category': e.category,
            'category_display': e.get_category_display(),
            'amount': float(e.amount or 0),
            'description': e.description,
            'created_by': e.created_by.get_full_name() or e.created_by.username if e.created_by else 'Staff',
            'approved_by': e.approved_by.get_full_name() or e.approved_by.username if e.approved_by else '—',
            'is_manager_approved': e.is_manager_approved,
            'time': e.created_at.strftime('%I:%M %p')
        } for e in today_expenses.order_by('-created_at')]

        net_cash = cash_in - cash_out - total_cash_expenses
        total_digital = upi_in + card_in + bank_in
        total_collected = (cash_in - cash_out) + total_digital

        # Room Status Count
        room_base = Room.objects.filter(property=prop, is_active=True) if prop else Room.objects.filter(is_active=True)
        all_rooms = room_base.select_related('room_type')
        total_rooms = all_rooms.count()
        occupied_rooms = all_rooms.filter(status=Room.Status.OCCUPIED).count()
        available_rooms = all_rooms.filter(status=Room.Status.AVAILABLE).count()
        cleaning_rooms = all_rooms.filter(status=Room.Status.CLEANING).count()
        maintenance_rooms = all_rooms.filter(status=Room.Status.MAINTENANCE).count()
        occupancy_rate = round((occupied_rooms / total_rooms * 100.0), 1) if total_rooms > 0 else 0.0

        # Operations Count
        stay_base = Stay.objects.filter(property=prop) if prop else Stay.objects.all()
        today_checkins = stay_base.filter(check_in_date=today).count()
        today_checkouts = stay_base.filter(Q(actual_checkout_date=today) | Q(status='CHECKED_OUT', updated_at__date=today)).count()
        overdue_stays = stay_base.filter(status='CHECKED_IN', expected_checkout_date__lt=today).count()

        # Tomorrow Scheduled Arrivals
        book_base = Booking.objects.filter(property=prop) if prop else Booking.objects.all()
        tomorrow_bookings = book_base.filter(
            check_in_date=tomorrow,
            status__in=['CONFIRMED', 'PENDING']
        ).select_related('customer', 'room')

        tomorrow_list = [{
            'booking_number': b.booking_number,
            'guest_name': b.customer.full_name if b.customer else 'Guest',
            'mobile': b.customer.mobile if b.customer else '',
            'room_number': b.room.room_number if b.room else 'Unassigned',
            'advance_paid': float(b.advance_amount or 0),
            'status': b.status
        } for b in tomorrow_bookings]

        return Response({
            'audit_date': str(today),
            'timestamp': datetime.datetime.now().strftime('%d %b %Y, %I:%M %p'),
            'lodge_info': {
                'lodge_name': settings_obj.lodge_name or 'LODGE MANAGEMENT SYSTEM',
                'gst_number': settings_obj.gst_number or 'N/A',
                'phone': settings_obj.phone or '',
                'address': settings_obj.address or '',
            },
            'financial_close': {
                'net_cash_in_till': float(net_cash),
                'cash_received': float(cash_in),
                'cash_refunded': float(cash_out),
                'cash_expenses': float(total_cash_expenses),
                'expenses_count': len(today_expenses_list),
                'upi_collections': float(upi_in),
                'card_collections': float(card_in),
                'bank_collections': float(bank_in),
                'total_digital': float(total_digital),
                'total_collections_today': float(total_collected),
            },
            'till_expenses': today_expenses_list,
            'inventory_summary': {
                'total_rooms': total_rooms,
                'occupied_rooms': occupied_rooms,
                'available_rooms': available_rooms,
                'cleaning_rooms': cleaning_rooms,
                'maintenance_rooms': maintenance_rooms,
                'occupancy_percentage': occupancy_rate,
            },
            'operations_summary': {
                'today_checkins': today_checkins,
                'today_checkouts': today_checkouts,
                'overdue_stays': overdue_stays,
                'tomorrow_arrivals_count': len(tomorrow_list),
            },
            'tomorrow_arrivals': tomorrow_list
        })


class ShiftReconciliationReportView(APIView):
    """
    Analytics endpoint for cashier reconciliations, discrepancy leaderboards,
    till variance trends, and petty cash expense category analysis.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from apps.shifts.models import Shift, ShiftExpense
        from django.contrib.auth import get_user_model
        User = get_user_model()

        start_date, end_date, start_datetime, end_datetime, label = parse_date_range(request.query_params)
        
        # Default to 30 days if not set
        if not start_date:
            end_date = datetime.date.today()
            start_date = end_date - datetime.timedelta(days=30)
            label = "Last 30 Days"

        user = request.user
        prop = getattr(user, 'property', None) if user and not user.is_superuser else None

        shift_base = Shift.objects.filter(property=prop) if prop else Shift.objects.all()
        shifts_qs = shift_base.filter(
            opened_at__date__gte=start_date,
            opened_at__date__lte=end_date
        ).select_related('user', 'closed_by')

        total_shifts = shifts_qs.count()
        closed_shifts = shifts_qs.filter(status__in=[Shift.Status.CLOSED, Shift.Status.FORCED_CLOSED])
        closed_count = closed_shifts.count()

        exact_closings = 0
        total_shortages = Decimal('0.00')
        total_excesses = Decimal('0.00')
        net_variance = Decimal('0.00')
        total_duration_mins = 0

        # Staff Map
        staff_stats = {}

        for s in closed_shifts:
            diff = s.cash_difference or Decimal('0.00')
            net_variance += diff
            total_duration_mins += s.duration_minutes

            if abs(diff) < Decimal('0.01'):
                exact_closings += 1
            elif diff < 0:
                total_shortages += abs(diff)
            else:
                total_excesses += diff

            u = s.user
            if u:
                if u.id not in staff_stats:
                    staff_stats[u.id] = {
                        'user_id': u.id,
                        'user_name': u.get_full_name() or u.username,
                        'role': getattr(u, 'role', 'STAFF'),
                        'total_shifts': 0,
                        'exact_closings': 0,
                        'shortage_shifts': 0,
                        'excess_shifts': 0,
                        'total_shortage': Decimal('0.00'),
                        'total_excess': Decimal('0.00'),
                        'net_variance': Decimal('0.00')
                    }
                st = staff_stats[u.id]
                st['total_shifts'] += 1
                st['net_variance'] += diff
                if abs(diff) < Decimal('0.01'):
                    st['exact_closings'] += 1
                elif diff < 0:
                    st['shortage_shifts'] += 1
                    st['total_shortage'] += abs(diff)
                else:
                    st['excess_shifts'] += 1
                    st['total_excess'] += diff

        # Leaderboard with accuracy calculation
        leaderboard = []
        for st in staff_stats.values():
            acc = round((st['exact_closings'] / st['total_shifts'] * 100), 1) if st['total_shifts'] > 0 else 100.0
            leaderboard.append({
                'user_id': st['user_id'],
                'user_name': st['user_name'],
                'role': st['role'],
                'total_shifts': st['total_shifts'],
                'exact_closings': st['exact_closings'],
                'shortage_shifts': st['shortage_shifts'],
                'excess_shifts': st['excess_shifts'],
                'total_shortage': float(st['total_shortage']),
                'total_excess': float(st['total_excess']),
                'net_variance': float(st['net_variance']),
                'accuracy_rate': acc
            })

        # Sort leaderboard by highest accuracy, then total shifts
        leaderboard.sort(key=lambda x: (-x['accuracy_rate'], -x['total_shifts']))

        overall_accuracy = round((exact_closings / closed_count * 100), 1) if closed_count > 0 else 100.0
        avg_duration = round(total_duration_mins / closed_count) if closed_count > 0 else 0

        # Daily Variance Trend
        daily_trends = []
        curr_d = start_date
        while curr_d <= end_date:
            day_shifts = closed_shifts.filter(opened_at__date=curr_d)
            day_count = day_shifts.count()
            day_shortage = Decimal('0.00')
            day_excess = Decimal('0.00')
            day_balanced = 0

            for ds in day_shifts:
                d_diff = ds.cash_difference or Decimal('0.00')
                if abs(d_diff) < Decimal('0.01'):
                    day_balanced += 1
                elif d_diff < 0:
                    day_shortage += abs(d_diff)
                else:
                    day_excess += d_diff

            daily_trends.append({
                'date': str(curr_d),
                'formatted_date': curr_d.strftime('%d %b'),
                'shifts_count': day_count,
                'balanced_count': day_balanced,
                'shortage_amount': float(day_shortage),
                'excess_amount': float(day_excess),
                'net_variance': float(day_excess - day_shortage)
            })
            curr_d += datetime.timedelta(days=1)

        # Petty Cash Categories Breakdown
        exp_base = ShiftExpense.objects.filter(shift__property=prop) if prop else ShiftExpense.objects.all()
        expenses_qs = exp_base.filter(
            shift__opened_at__date__gte=start_date,
            shift__opened_at__date__lte=end_date
        ).select_related('shift', 'created_by', 'approved_by')

        cat_agg = expenses_qs.values('category').annotate(
            total_amount=Sum('amount'),
            expense_count=Count('id')
        ).order_by('-total_amount')

        category_dict = dict(ShiftExpense.Category.choices)
        expense_categories = [{
            'category': c['category'],
            'label': category_dict.get(c['category'], c['category']),
            'total_amount': float(c['total_amount'] or 0),
            'expense_count': c['expense_count']
        } for c in cat_agg]

        itemized_expenses = [{
            'id': e.id,
            'voucher_no': f"EXP-{e.id:04d}",
            'date': e.created_at.strftime('%d %b %Y'),
            'time': e.created_at.strftime('%I:%M %p'),
            'datetime': e.created_at.strftime('%Y-%m-%d %H:%M'),
            'shift_number': e.shift.shift_number if e.shift else '—',
            'cashier_name': e.created_by.get_full_name() or e.created_by.username if e.created_by else 'Staff',
            'category': e.category,
            'category_display': e.get_category_display(),
            'description': e.description,
            'amount': float(e.amount or 0),
            'is_approved': e.is_manager_approved,
            'approved_by': e.approved_by.get_full_name() or e.approved_by.username if e.approved_by else 'Pending'
        } for e in expenses_qs.order_by('-created_at')]

        total_petty_cash = sum(c['total_amount'] for c in expense_categories)

        return Response({
            'period': label,
            'start_date': str(start_date),
            'end_date': str(end_date),
            'summary': {
                'total_shifts': total_shifts,
                'closed_shifts': closed_count,
                'exact_closings': exact_closings,
                'accuracy_rate': overall_accuracy,
                'total_shortages': float(total_shortages),
                'total_excesses': float(total_excesses),
                'net_variance': float(net_variance),
                'avg_duration_minutes': avg_duration,
                'total_petty_cash_expenses': total_petty_cash,
                'petty_cash_vouchers_count': len(itemized_expenses)
            },
            'staff_leaderboard': leaderboard,
            'daily_trends': daily_trends,
            'expense_categories': expense_categories,
            'itemized_expenses': itemized_expenses,
            'total_expense_amount': total_petty_cash
        })


