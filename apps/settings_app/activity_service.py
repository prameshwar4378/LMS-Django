import datetime
from decimal import Decimal
from django.utils import timezone
from django.db.models import Q

from apps.rooms.models import Room, RoomType, RoomDeletionRequest
from apps.bookings.models import Booking
from apps.stays.models import Stay
from apps.billing.models import Payment, ExtraCharge
from apps.customers.models import Customer
from apps.shifts.models import Shift, CashDrawer

# Master list of models tracked by django-simple-history
TRACKED_MODELS = [
    {
        'model': Booking,
        'name': 'Booking',
        'label': 'Booking / Reservation',
        'icon': 'CalendarDays',
        'tenant_field': 'property_id',
    },
    {
        'model': Stay,
        'name': 'Stay',
        'label': 'Stay / Check-In',
        'icon': 'KeyRound',
        'tenant_field': 'property_id',
    },
    {
        'model': Payment,
        'name': 'Payment',
        'label': 'Billing & Payment',
        'icon': 'CreditCard',
        'tenant_field': 'property_id',
    },
    {
        'model': ExtraCharge,
        'name': 'ExtraCharge',
        'label': 'Folio Extra Charge',
        'icon': 'DollarSign',
        'tenant_field': 'stay__property_id',
    },
    {
        'model': Room,
        'name': 'Room',
        'label': 'Room Inventory',
        'icon': 'DoorOpen',
        'tenant_field': 'property_id',
    },
    {
        'model': RoomType,
        'name': 'RoomType',
        'label': 'Room Category',
        'icon': 'BedDouble',
        'tenant_field': 'property_id',
    },
    {
        'model': RoomDeletionRequest,
        'name': 'RoomDeletionRequest',
        'label': 'Room Deletion Request',
        'icon': 'Trash2',
        'tenant_field': 'property_id',
    },
    {
        'model': Customer,
        'name': 'Customer',
        'label': 'Guest Profile',
        'icon': 'Users',
        'tenant_field': 'property_id',
    },
    {
        'model': Shift,
        'name': 'Shift',
        'label': 'Shift & Till',
        'icon': 'Clock',
        'tenant_field': 'property_id',
    },
    {
        'model': CashDrawer,
        'name': 'CashDrawer',
        'label': 'Cash Register',
        'icon': 'Building2',
        'tenant_field': 'property_id',
    },
]

EXCLUDED_DIFF_FIELDS = {
    'updated_at',
    'created_at',
    'history_id',
    'history_date',
    'history_change_reason',
    'history_type',
    'history_user',
    'history_user_id',
}

def format_field_label(field_name):
    """Converts field_name (e.g. check_in_date) into a friendly label (Check In Date)."""
    custom_labels = {
        'room_number': 'Room Number',
        'check_in_date': 'Check-In Date',
        'check_in_time': 'Check-In Time',
        'expected_checkout_date': 'Expected Checkout Date',
        'expected_checkout_time': 'Expected Checkout Time',
        'actual_checkout_date': 'Actual Checkout Date',
        'actual_checkout_time': 'Actual Checkout Time',
        'base_price': 'Base Tariff',
        'room_rate': 'Room Rate',
        'discount_type': 'Discount Type',
        'discount_value': 'Discount Value',
        'discount_reason': 'Discount Reason',
        'payment_method': 'Payment Method',
        'transaction_reference': 'Transaction Ref / UTR',
        'opening_balance': 'Opening Float',
        'expected_cash': 'Expected Cash',
        'actual_cash': 'Actual Cash Counted',
        'cash_difference': 'Cash Discrepancy',
        'is_active': 'Active Status',
        'first_name': 'First Name',
        'last_name': 'Last Name',
        'id_number': 'ID Card Number',
        'id_type': 'ID Card Type',
    }
    if field_name in custom_labels:
        return custom_labels[field_name]
    return field_name.replace('_', ' ').title()

def format_field_val(val):
    """Formats values for clean display in diffs."""
    if val is None:
        return '-'
    if isinstance(val, bool):
        return 'Yes' if val else 'No'
    if isinstance(val, (datetime.date, datetime.datetime)):
        return val.strftime('%d %b %Y, %I:%M %p') if isinstance(val, datetime.datetime) else val.strftime('%d %b %Y')
    if isinstance(val, (Decimal, float)):
        return f"{val:,.2f}"
    return str(val)

def get_object_display(model_name, rec):
    """Generates an intuitive representation of the object instance."""
    try:
        if model_name == 'Room':
            return f"Room {getattr(rec, 'room_number', rec.id)}"
        if model_name == 'RoomType':
            return f"Category '{getattr(rec, 'name', rec.id)}'"
        if model_name == 'Booking':
            num = getattr(rec, 'booking_number', rec.id)
            return f"Booking #{num}"
        if model_name == 'Stay':
            num = getattr(rec, 'stay_number', rec.id)
            return f"Stay #{num}"
        if model_name == 'Payment':
            num = getattr(rec, 'payment_number', rec.id)
            amt = getattr(rec, 'amount', 0)
            method = getattr(rec, 'payment_method', '')
            return f"Payment #{num} (₹{amt:,.2f} via {method})"
        if model_name == 'ExtraCharge':
            desc = getattr(rec, 'description', 'Charge')
            amt = getattr(rec, 'amount', 0)
            return f"Charge '{desc}' (₹{amt:,.2f})"
        if model_name == 'Customer':
            name = f"{getattr(rec, 'first_name', '')} {getattr(rec, 'last_name', '')}".strip()
            mob = getattr(rec, 'mobile', '')
            return f"Guest {name} ({mob})" if mob else f"Guest {name}"
        if model_name == 'Shift':
            num = getattr(rec, 'shift_number', rec.id)
            st = getattr(rec, 'status', '')
            return f"Shift #{num} [{st}]"
        if model_name == 'CashDrawer':
            return f"Cash Register '{getattr(rec, 'name', rec.id)}' ({getattr(rec, 'code', '')})"
        if model_name == 'RoomDeletionRequest':
            return f"Deletion Request for Room {getattr(rec, 'room_number', '')}"
    except Exception:
        pass
    return f"{model_name} #{getattr(rec, 'id', '')}"

def humanize_time_ago(dt):
    """Returns friendly relative time."""
    now = timezone.now()
    diff = now - dt
    total_seconds = int(diff.total_seconds())

    if total_seconds < 60:
        return 'just now'
    minutes = total_seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    if days == 1:
        return '1 day ago'
    return f"{days} days ago"

def cleanup_old_history(days=15):
    """
    Automatically deletes historical records older than `days` across all tracked models.
    Guarantees that past records older than 15 days are automatically pruned.
    """
    cutoff = timezone.now() - datetime.timedelta(days=days)
    total_deleted = 0
    details = {}

    for item in TRACKED_MODELS:
        model = item['model']
        if hasattr(model, 'history'):
            try:
                cnt, _ = model.history.filter(history_date__lt=cutoff).delete()
                if cnt > 0:
                    details[item['name']] = cnt
                    total_deleted += cnt
            except Exception as e:
                pass

    return {
        'total_deleted': total_deleted,
        'details': details,
        'retention_days': days,
        'cutoff': cutoff.isoformat(),
    }

def generate_activity_summary(model_name, action_name, rec, changes, change_reason):
    """
    Generates an intuitive, readable summary sentence for an activity record.
    """
    if change_reason and change_reason.strip():
        return change_reason.strip()

    # Room
    if model_name == 'Room':
        r_num = getattr(rec, 'room_number', rec.id)
        if action_name == 'CREATED':
            return f"Room {r_num} added to inventory."
        elif action_name == 'DELETED':
            return f"Room {r_num} deleted."
        elif action_name == 'UPDATED':
            st_ch = next((c for c in changes if c.get('field') == 'status'), None)
            if st_ch:
                old_v = st_ch.get('old_value', '')
                new_v = st_ch.get('new_value', '')
                if new_v == 'OCCUPIED':
                    return f"Room {r_num} checked in / occupied."
                elif new_v in ['CLEANING', 'DIRTY']:
                    return f"Room {r_num} set to {new_v}."
                elif new_v == 'AVAILABLE':
                    return f"Room {r_num} marked AVAILABLE."
                return f"Room {r_num} status updated from {old_v} to {new_v}."
            if changes:
                labels = ", ".join(c.get('field_label', '') for c in changes[:3])
                return f"Room {r_num} updated ({labels})."
            return f"Room {r_num} updated."

    # Stay
    elif model_name == 'Stay':
        s_num = getattr(rec, 'stay_number', rec.id)
        if action_name == 'CREATED':
            return f"Stay #{s_num} checked in."
        elif action_name == 'UPDATED':
            st = getattr(rec, 'status', '')
            if st == 'CHECKED_OUT':
                return f"Stay #{s_num} checked out."
            return f"Stay #{s_num} updated ({st})."
        elif action_name == 'DELETED':
            return f"Stay #{s_num} removed."

    # Booking
    elif model_name == 'Booking':
        b_num = getattr(rec, 'booking_number', rec.id)
        if action_name == 'CREATED':
            adv = getattr(rec, 'advance_amount', 0)
            adv_txt = f" with ₹{adv:,.2f} advance" if adv and float(adv) > 0 else ""
            return f"Booking #{b_num} created{adv_txt}."
        elif action_name == 'UPDATED':
            st = getattr(rec, 'status', '')
            if st == 'CHECKED_IN':
                return f"Booking #{b_num} checked in."
            elif st == 'CANCELLED':
                return f"Booking #{b_num} cancelled."
            return f"Booking #{b_num} status updated to {st}."
        elif action_name == 'DELETED':
            return f"Booking #{b_num} deleted."

    # Payment
    elif model_name == 'Payment':
        p_num = getattr(rec, 'payment_number', rec.id)
        amt = getattr(rec, 'amount', 0)
        method = getattr(rec, 'payment_method', 'CASH')
        if action_name == 'CREATED':
            return f"Payment #{p_num} of ₹{amt:,.2f} recorded via {method}."
        return f"Payment #{p_num} updated (₹{amt:,.2f} via {method})."

    # ExtraCharge
    elif model_name == 'ExtraCharge':
        desc = getattr(rec, 'description', 'Charge')
        amt = getattr(rec, 'amount', 0)
        return f"Charge '{desc}' of ₹{amt:,.2f} recorded."

    # Customer
    elif model_name == 'Customer':
        name = f"{getattr(rec, 'first_name', '')} {getattr(rec, 'last_name', '')}".strip() or 'Guest'
        if action_name == 'CREATED':
            return f"Guest profile for {name} created."
        return f"Guest profile for {name} updated."

    # Shift
    elif model_name == 'Shift':
        num = getattr(rec, 'shift_number', rec.id)
        st = getattr(rec, 'status', '')
        return f"Shift #{num} [{st}]."

    # CashDrawer
    elif model_name == 'CashDrawer':
        name = getattr(rec, 'name', rec.id)
        return f"Cash register '{name}' updated."

    # Fallback
    if changes:
        lbls = ", ".join(c.get('field_label', '') for c in changes[:3])
        return f"{model_name} {action_name.lower()} ({lbls})."
    return f"{model_name} #{getattr(rec, 'id', '')} {action_name.lower()}."

def get_activity_logs(
    prop=None,
    page=1,
    page_size=20,
    model_filter='ALL',
    action_filter='ALL',
    search_query='',
    days=15
):
    """
    Retrieves, formats, and paginates system activity logs within the 15-day retention window.
    Extracts who did, when did, what did, and exact field-level diffs (previous value vs updated value).
    """
    # 1. Enforce 15-day auto-cleanup
    cleanup_old_history(days=days)

    cutoff = timezone.now() - datetime.timedelta(days=days)

    # 2. Collect matching models
    models_to_query = []
    for item in TRACKED_MODELS:
        if model_filter and model_filter.upper() != 'ALL':
            if item['name'].lower() != model_filter.lower():
                continue
        models_to_query.append(item)

    collected_records = []

    # Map action filter: 'ALL', 'CREATED' (+), 'UPDATED' (~), 'DELETED' (-)
    action_symbol_map = {
        'CREATED': '+',
        'UPDATED': '~',
        'DELETED': '-',
    }
    target_symbol = action_symbol_map.get(action_filter.upper(), None)

    for item in models_to_query:
        model = item['model']
        if not hasattr(model, 'history'):
            continue

        qs = model.history.filter(history_date__gte=cutoff).select_related('history_user')

        # Multi-tenant property filter
        if prop is not None:
            tenant_f = item.get('tenant_field', 'property_id')
            qs = qs.filter(**{tenant_f: prop.id})

        # Action filter
        if target_symbol:
            qs = qs.filter(history_type=target_symbol)

        # Pull recent entries (capped to avoid memory exhaustion)
        records = list(qs.order_by('-history_date')[:150])

        for rec in records:
            collected_records.append({
                'rec': rec,
                'meta': item,
                'history_date': rec.history_date,
            })

    # 3. Sort all records across models by timestamp descending
    collected_records.sort(key=lambda x: x['history_date'], reverse=True)

    # 4. Filter by search query if provided
    if search_query:
        q_lower = search_query.strip().lower()
        filtered = []
        for item in collected_records:
            rec = item['rec']
            meta = item['meta']
            obj_repr = get_object_display(meta['name'], rec).lower()
            username = getattr(rec.history_user, 'username', '').lower()
            full_name = f"{getattr(rec.history_user, 'first_name', '')} {getattr(rec.history_user, 'last_name', '')}".lower()
            reason = getattr(rec, 'history_change_reason', '') or ''
            
            if q_lower in obj_repr or q_lower in username or q_lower in full_name or q_lower in reason.lower():
                filtered.append(item)
        collected_records = filtered

    total_count = len(collected_records)
    total_pages = max(1, (total_count + page_size - 1) // page_size)
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    paged_items = collected_records[start_idx:end_idx]

    # 5. Format results and compute field diffs for the current page only (highly performant)
    results = []
    for item in paged_items:
        rec = item['rec']
        meta = item['meta']
        model_name = meta['name']

        # Action resolution
        action_code = rec.history_type
        if action_code == '+':
            action_name = 'CREATED'
            action_display = 'Created'
            action_badge = 'success'
        elif action_code == '~':
            action_name = 'UPDATED'
            action_display = 'Updated'
            action_badge = 'primary'
        elif action_code == '-':
            action_name = 'DELETED'
            action_display = 'Deleted'
            action_badge = 'danger'
        else:
            action_name = 'UNKNOWN'
            action_display = 'Modified'
            action_badge = 'secondary'

        # User details (Who did)
        user_obj = None
        if rec.history_user:
            u = rec.history_user
            full_name = u.get_full_name() or u.username
            user_obj = {
                'id': u.id,
                'username': u.username,
                'full_name': full_name,
                'role': getattr(u, 'role', 'STAFF'),
            }
        else:
            user_obj = {
                'id': None,
                'username': 'System',
                'full_name': 'Automated / System',
                'role': 'SYSTEM',
            }

        # Field-Level Diffs (What did, and if data update: previous value vs updated value)
        changes = []
        if action_name == 'UPDATED':
            try:
                prev = rec.prev_record
                if prev:
                    delta = rec.diff_against(prev)
                    for c in delta.changes:
                        if c.field in EXCLUDED_DIFF_FIELDS:
                            continue
                        changes.append({
                            'field': c.field,
                            'field_label': format_field_label(c.field),
                            'old_value': format_field_val(c.old),
                            'new_value': format_field_val(c.new),
                        })
            except Exception as diff_err:
                pass

            # If no previous snapshot exists or diff was empty, synthesize meaningful attribute display
            if not changes:
                if model_name == 'Room' and getattr(rec, 'status', None):
                    changes.append({
                        'field': 'status',
                        'field_label': 'Status',
                        'old_value': 'Previous',
                        'new_value': rec.status,
                    })
                elif model_name in ['Stay', 'Booking'] and getattr(rec, 'status', None):
                    changes.append({
                        'field': 'status',
                        'field_label': 'Status',
                        'old_value': 'Previous',
                        'new_value': rec.status,
                    })

        summary_text = generate_activity_summary(model_name, action_name, rec, changes, rec.history_change_reason)

        results.append({
            'id': f"{model_name}-{rec.history_id}",
            'history_id': rec.history_id,
            'model': model_name,
            'model_label': meta['label'],
            'model_icon': meta['icon'],
            'action': action_name,
            'action_display': action_display,
            'action_badge': action_badge,
            'action_symbol': action_code,
            'object_id': getattr(rec, 'id', None),
            'object_repr': get_object_display(model_name, rec),
            'user': user_obj,
            'timestamp': rec.history_date.isoformat(),
            'time_ago': humanize_time_ago(rec.history_date),
            'changes': changes,
            'changes_count': len(changes),
            'change_reason': rec.history_change_reason or '',
            'summary': summary_text,
        })

    return {
        'count': total_count,
        'page': page,
        'page_size': page_size,
        'total_pages': total_pages,
        'retention_days': days,
        'results': results,
    }
