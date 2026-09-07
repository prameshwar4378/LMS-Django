from rest_framework import serializers
from .models import Customer, CustomerDocument

class CustomerDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerDocument
        fields = '__all__'

class CustomerSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    stay_count = serializers.IntegerField(source='stays.count', read_only=True)
    documents = CustomerDocumentSerializer(many=True, read_only=True)
    total_wallet_credit = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Customer
        fields = '__all__'

    def get_total_wallet_credit(self, obj):
        from apps.billing.services import calculate_stay_bill
        raw_credit = float(obj.advance_credit or 0)
        stay_overpayment = 0.0
        for stay in obj.stays.all():
            bill = calculate_stay_bill(stay)
            bal = float(bill.get('balance', 0))
            if bal < 0:
                stay_overpayment += abs(bal)
        return raw_credit + stay_overpayment

class CustomerHistorySerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    is_checked_in = serializers.SerializerMethodField(read_only=True)
    active_stay = serializers.SerializerMethodField(read_only=True)
    stays = serializers.SerializerMethodField(read_only=True)
    bookings = serializers.SerializerMethodField(read_only=True)
    transactions = serializers.SerializerMethodField(read_only=True)
    documents = CustomerDocumentSerializer(many=True, read_only=True)
    advance_credit = serializers.FloatField(read_only=True)
    overall_pending_balance = serializers.SerializerMethodField(read_only=True)
    overall_account_status = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Customer
        fields = '__all__'

    def get_is_checked_in(self, obj):
        return obj.stays.filter(status='CHECKED_IN').exists()

    def get_active_stay(self, obj):
        active = obj.stays.filter(status='CHECKED_IN').select_related('room', 'room__room_type').order_by('-created_at').first()
        if not active:
            return None
        return {
            'id': active.id,
            'stay_number': active.stay_number,
            'room_id': active.room.id if active.room else None,
            'room_number': active.room.room_number if active.room else 'N/A',
            'room_type': active.room.room_type.name if active.room and active.room.room_type else 'Standard',
            'check_in_date': active.check_in_date,
            'expected_checkout_date': active.expected_checkout_date,
        }

    def get_bookings(self, obj):
        res = []
        for b in obj.bookings.all().select_related('room', 'room__room_type').prefetch_related('stays').order_by('-created_at'):
            b_status = b.status
            # If linked stay is checked out, booking is completed
            linked_stays = list(b.stays.all())
            if linked_stays and all(s.status == 'CHECKED_OUT' for s in linked_stays):
                if b_status == 'CHECKED_IN':
                    b_status = 'COMPLETED'
                    b.status = 'COMPLETED'
                    b.save(update_fields=['status'])

            res.append({
                'id': b.id,
                'booking_number': b.booking_number,
                'room_id': b.room.id if b.room else None,
                'room_number': b.room.room_number if b.room else 'N/A',
                'room_type': b.room.room_type.name if b.room and b.room.room_type else 'Standard',
                'check_in_date': b.check_in_date,
                'check_in_time': str(b.check_in_time) if b.check_in_time else '12:00',
                'expected_checkout_date': b.expected_checkout_date,
                'expected_checkout_time': str(b.expected_checkout_time) if b.expected_checkout_time else '11:00',
                'adults': b.adults,
                'children': b.children,
                'room_rate': float(b.room_rate or 0),
                'discount_type': b.discount_type,
                'discount_value': float(b.discount_value or 0),
                'advance_amount': float(b.advance_amount or 0),
                'status': b_status,
                'notes': b.notes or '',
                'created_at': b.created_at,
            })
        return res

    def get_overall_pending_balance(self, obj):
        from apps.billing.services import calculate_stay_bill
        total_pending = 0.0
        for stay in obj.stays.all():
            bill = calculate_stay_bill(stay)
            bal = float(bill.get('balance', 0))
            if bal > 0:
                total_pending += bal
        return total_pending

    def get_overall_account_status(self, obj):
        from apps.billing.services import calculate_stay_bill
        pending = 0.0
        stay_credits = 0.0
        for stay in obj.stays.all():
            bill = calculate_stay_bill(stay)
            bal = float(bill.get('balance', 0))
            if bal > 0:
                pending += bal
            elif bal < 0:
                stay_credits += abs(bal)

        total_wallet = float(obj.advance_credit or 0) + stay_credits
        net = pending - total_wallet
        if net > 0:
            return {'type': 'PENDING', 'amount': net, 'pending_due': pending, 'advance_credit': total_wallet}
        elif total_wallet > 0:
            return {'type': 'ADVANCE', 'amount': total_wallet, 'pending_due': pending, 'advance_credit': total_wallet}
        else:
            return {'type': 'SETTLED', 'amount': 0.0, 'pending_due': 0.0, 'advance_credit': 0.0}

    def get_stays(self, obj):
        from apps.billing.services import calculate_stay_bill
        result = []
        for stay in obj.stays.all().select_related('room', 'room__room_type').order_by('-created_at'):
            bill = calculate_stay_bill(stay)
            raw_bal = bill['balance']
            pending_bal = max(0.0, raw_bal)
            credit_bal = abs(raw_bal) if raw_bal < 0 else 0.0

            stay_status = stay.status
            if stay.actual_checkout_date and stay_status != 'CHECKED_OUT':
                stay_status = 'CHECKED_OUT'
                stay.status = 'CHECKED_OUT'
                stay.save(update_fields=['status'])

            result.append({
                'id': stay.id,
                'stay_number': stay.stay_number,
                'room_id': stay.room.id if stay.room else None,
                'room_number': stay.room.room_number if stay.room else 'N/A',
                'room_type': stay.room.room_type.name if stay.room and stay.room.room_type else 'Standard',
                'check_in_date': stay.check_in_date,
                'check_in_time': str(stay.check_in_time) if stay.check_in_time else '12:00',
                'expected_checkout_date': stay.expected_checkout_date,
                'expected_checkout_time': str(stay.expected_checkout_time) if stay.expected_checkout_time else '11:00',
                'actual_checkout_date': stay.actual_checkout_date,
                'actual_checkout_time': str(stay.actual_checkout_time) if stay.actual_checkout_time else None,
                'checkout_date': stay.actual_checkout_date or stay.expected_checkout_date,
                'status': stay_status,
                'grand_total': bill['grand_total'],
                'total_paid': bill['total_paid'],
                'balance': pending_bal,
                'raw_balance': raw_bal,
                'credit_balance': credit_bal,
            })
        return result

    def get_transactions(self, obj):
        from apps.billing.models import Payment
        from django.db.models import Q
        payments = Payment.objects.filter(
            Q(stay__primary_customer=obj) | Q(customer=obj)
        ).select_related('stay', 'stay__room', 'received_by', 'customer').order_by('-payment_date', '-id').distinct()
        res = []
        for p in payments:
            received_by_name = ""
            if p.received_by:
                received_by_name = f"{p.received_by.first_name} {p.received_by.last_name}".strip() or p.received_by.username

            stay_id = p.stay.id if p.stay else None
            stay_number = p.stay.stay_number if p.stay else 'Wallet Deposit'
            room_number = p.stay.room.room_number if p.stay and p.stay.room else 'N/A'

            res.append({
                'id': p.id,
                'payment_number': p.payment_number,
                'stay_id': stay_id,
                'stay_number': stay_number,
                'room_number': room_number,
                'amount': float(p.amount),
                'payment_method': p.payment_method,
                'transaction_reference': p.transaction_reference or 'N/A',
                'payment_date': p.payment_date,
                'received_by': received_by_name or 'System/Staff',
                'notes': p.notes or ''
            })
        return res
