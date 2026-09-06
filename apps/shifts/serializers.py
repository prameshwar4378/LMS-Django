from rest_framework import serializers
from .models import Shift, ShiftDenomination, ShiftExpense, ShiftCashAdjustment, ShiftHandover, ShiftAuditLog, CashDrawer
from .services import calculate_shift_financials
from apps.billing.serializers import PaymentSerializer

class CashDrawerSerializer(serializers.ModelSerializer):
    is_in_use = serializers.SerializerMethodField()
    current_shift_id = serializers.SerializerMethodField()
    current_cashier_name = serializers.SerializerMethodField()

    class Meta:
        model = CashDrawer
        fields = [
            'id', 'name', 'code', 'location', 'default_float', 'is_active',
            'allow_shared_users', 'is_in_use', 'current_shift_id', 'current_cashier_name'
        ]

    def get_is_in_use(self, obj):
        return obj.shifts.filter(status__in=[Shift.Status.OPEN, Shift.Status.CLOSING]).exists()

    def get_current_shift_id(self, obj):
        active = obj.shifts.filter(status__in=[Shift.Status.OPEN, Shift.Status.CLOSING]).first()
        return active.id if active else None

    def get_current_cashier_name(self, obj):
        active = obj.shifts.filter(status__in=[Shift.Status.OPEN, Shift.Status.CLOSING]).first()
        if active and active.user:
            return active.user.get_full_name() or active.user.username
        return None

class ShiftDenominationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShiftDenomination
        fields = ['id', 'shift', 'denomination', 'unit_value', 'quantity', 'total']
        read_only_fields = ['id', 'total']


class ShiftExpenseSerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()
    approved_by_name = serializers.SerializerMethodField()
    updated_by_name = serializers.SerializerMethodField()
    category_display = serializers.CharField(source='get_category_display', read_only=True)

    class Meta:
        model = ShiftExpense
        fields = [
            'id', 'shift', 'category', 'category_display', 'amount', 'description',
            'receipt', 'is_manager_approved', 'approved_by', 'approved_by_name',
            'created_by', 'created_by_name', 'updated_by', 'updated_by_name',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_by', 'updated_by', 'approved_by', 'created_at', 'updated_at']

    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name() or obj.created_by.username
        return 'System'

    def get_updated_by_name(self, obj):
        if obj.updated_by:
            return obj.updated_by.get_full_name() or obj.updated_by.username
        return None

    def get_approved_by_name(self, obj):
        if obj.approved_by:
            return obj.approved_by.get_full_name() or obj.approved_by.username
        return None


class ShiftCashAdjustmentSerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()
    approved_by_name = serializers.SerializerMethodField()
    updated_by_name = serializers.SerializerMethodField()
    adjustment_type_display = serializers.CharField(source='get_adjustment_type_display', read_only=True)

    class Meta:
        model = ShiftCashAdjustment
        fields = [
            'id', 'shift', 'adjustment_type', 'adjustment_type_display', 'amount', 'reason', 'notes',
            'created_by', 'created_by_name', 'updated_by', 'updated_by_name',
            'approved_by', 'approved_by_name', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_by', 'updated_by', 'approved_by', 'created_at', 'updated_at']

    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name() or obj.created_by.username
        return 'Staff'

    def get_updated_by_name(self, obj):
        if obj.updated_by:
            return obj.updated_by.get_full_name() or obj.updated_by.username
        return None

    def get_approved_by_name(self, obj):
        if obj.approved_by:
            return obj.approved_by.get_full_name() or obj.approved_by.username
        return None


class ShiftHandoverSerializer(serializers.ModelSerializer):
    from_user_name = serializers.SerializerMethodField()
    to_user_name = serializers.SerializerMethodField()
    updated_by_name = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = ShiftHandover
        fields = [
            'id', 'from_shift', 'from_user', 'from_user_name', 'to_shift', 'to_user', 'to_user_name',
            'amount', 'status', 'status_display', 'is_opening_handover', 'notes', 'rejection_reason',
            'updated_by', 'updated_by_name', 'handed_over_at', 'received_at', 'updated_at'
        ]
        read_only_fields = ['id', 'from_user', 'is_opening_handover', 'updated_by', 'handed_over_at', 'updated_at']

    def get_from_user_name(self, obj):
        if obj.from_user:
            return obj.from_user.get_full_name() or obj.from_user.username
        return 'Staff'

    def get_to_user_name(self, obj):
        if obj.to_user:
            return obj.to_user.get_full_name() or obj.to_user.username
        return 'Staff'

    def get_updated_by_name(self, obj):
        if obj.updated_by:
            return obj.updated_by.get_full_name() or obj.updated_by.username
        return None


class ShiftAuditLogSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = ShiftAuditLog
        fields = ['id', 'shift', 'user', 'user_name', 'action', 'description', 'metadata', 'created_at']
        read_only_fields = ['id', 'created_at']

    def get_user_name(self, obj):
        if obj.user:
            return obj.user.get_full_name() or obj.user.username
        return 'System'


class ShiftSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    closed_by_name = serializers.SerializerMethodField()
    manager_approved_by_name = serializers.SerializerMethodField()
    updated_by_name = serializers.SerializerMethodField()
    cash_drawer_name = serializers.CharField(source='cash_drawer.name', read_only=True)
    cash_drawer_code = serializers.CharField(source='cash_drawer.code', read_only=True)
    cash_drawer_location = serializers.CharField(source='cash_drawer.location', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    expected_cash = serializers.SerializerMethodField()
    financials = serializers.SerializerMethodField()
    duration_minutes = serializers.SerializerMethodField()
    operational_metrics = serializers.SerializerMethodField()

    class Meta:
        model = Shift
        fields = [
            'id', 'shift_number', 'cash_drawer', 'cash_drawer_name', 'cash_drawer_code', 'cash_drawer_location',
            'user', 'user_name', 'opened_at', 'closed_at',
            'opening_balance', 'expected_cash', 'actual_cash', 'cash_difference',
            'status', 'status_display', 'opening_notes', 'closing_notes', 'difference_reason',
            'closed_by', 'closed_by_name', 'manager_approved_by', 'manager_approved_by_name',
            'manager_approval_notes', 'manager_approved_at', 'reopened_by', 'reopened_at', 'reopen_reason',
            'updated_by', 'updated_by_name',
            'financials', 'duration_minutes', 'operational_metrics', 'is_stale', 'is_long_running',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'shift_number', 'opened_at', 'closed_at', 'expected_cash',
            'actual_cash', 'cash_difference', 'status', 'closed_by',
            'manager_approved_by', 'manager_approved_at', 'reopened_by', 'reopened_at',
            'updated_by', 'created_at', 'updated_at'
        ]

    def get_user_name(self, obj):
        if obj.user:
            return obj.user.get_full_name() or obj.user.username
        return 'Staff'

    def get_closed_by_name(self, obj):
        if obj.closed_by:
            return obj.closed_by.get_full_name() or obj.closed_by.username
        return None

    def get_manager_approved_by_name(self, obj):
        if obj.manager_approved_by:
            return obj.manager_approved_by.get_full_name() or obj.manager_approved_by.username
        return None

    def get_updated_by_name(self, obj):
        if obj.updated_by:
            return obj.updated_by.get_full_name() or obj.updated_by.username
        return None

    def get_financials(self, obj):
        if not hasattr(obj, '_cached_financials'):
            obj._cached_financials = calculate_shift_financials(obj)
        return obj._cached_financials

    def get_expected_cash(self, obj):
        if obj.status in [Shift.Status.OPEN, Shift.Status.CLOSING]:
            fin = self.get_financials(obj)
            return fin.get('expected_cash', float(obj.expected_cash or 0))
        return float(obj.expected_cash or 0)

    def get_operational_metrics(self, obj):
        from .services import calculate_shift_operational_metrics
        return calculate_shift_operational_metrics(obj)

    def get_duration_minutes(self, obj):
        end_time = obj.closed_at or obj.updated_at
        if obj.opened_at and end_time:
            diff = end_time - obj.opened_at
            return int(diff.total_seconds() // 60)
        return 0


class ShiftDetailSerializer(ShiftSerializer):
    denominations = ShiftDenominationSerializer(many=True, read_only=True)
    expenses = ShiftExpenseSerializer(many=True, read_only=True)
    adjustments = ShiftCashAdjustmentSerializer(many=True, read_only=True)
    handovers_sent = ShiftHandoverSerializer(many=True, read_only=True)
    handovers_received = ShiftHandoverSerializer(many=True, read_only=True)
    audit_logs = ShiftAuditLogSerializer(many=True, read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)

    class Meta(ShiftSerializer.Meta):
        fields = ShiftSerializer.Meta.fields + [
            'denominations', 'expenses', 'adjustments',
            'handovers_sent', 'handovers_received', 'audit_logs', 'payments'
        ]
