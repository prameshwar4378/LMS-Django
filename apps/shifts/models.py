from django.db import models
from django.conf import settings
from django.utils import timezone
from decimal import Decimal
from apps.settings_app.tenant_models import TenantModel

class CashDrawer(TenantModel):
    name = models.CharField(max_length=100, help_text="e.g. Main Front Desk Till #1")
    code = models.CharField(max_length=30, db_index=True, help_text="e.g. POS-MAIN-01")
    location = models.CharField(max_length=100, blank=True, null=True, help_text="e.g. Reception Lobby")
    default_float = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('1000.00'))
    is_active = models.BooleanField(default=True)
    allow_shared_users = models.BooleanField(default=False, help_text="Allow multiple cashiers to operate simultaneously")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(fields=['property', 'code'], name='unique_property_drawer_code')
        ]

    def __str__(self):
        return f"{self.name} ({self.code})"


class Shift(TenantModel):
    class Status(models.TextChoices):
        OPEN = 'OPEN', 'Open'
        CLOSING = 'CLOSING', 'Closing'
        PENDING_APPROVAL = 'PENDING_APPROVAL', 'Pending Manager Approval'
        PENDING_REVIEW = 'PENDING_REVIEW', 'Stale - Pending Manager Review'
        CLOSED = 'CLOSED', 'Closed'
        FORCED_CLOSED = 'FORCED_CLOSED', 'Admin Force Closed'

    shift_number = models.CharField(max_length=50, unique=True, db_index=True)
    cash_drawer = models.ForeignKey(
        CashDrawer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='shifts',
        help_text="Physical POS Register / Cash Drawer assigned"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='shifts',
        help_text="Receptionist / Cashier assigned to this shift"
    )
    opened_at = models.DateTimeField(default=timezone.now, db_index=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    opening_balance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    expected_cash = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    actual_cash = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    cash_difference = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00')) # actual - expected

    status = models.CharField(max_length=30, choices=Status.choices, default=Status.OPEN, db_index=True)

    opening_notes = models.TextField(blank=True, null=True)
    closing_notes = models.TextField(blank=True, null=True)
    difference_reason = models.TextField(blank=True, null=True)

    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='closed_shifts'
    )
    manager_approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_shifts'
    )
    manager_approval_notes = models.TextField(blank=True, null=True)
    manager_approved_at = models.DateTimeField(null=True, blank=True)

    reopened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reopened_shifts'
    )
    reopened_at = models.DateTimeField(null=True, blank=True)
    reopen_reason = models.TextField(blank=True, null=True)

    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='updated_shifts'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-opened_at']

    @property
    def duration_minutes(self):
        end_time = self.closed_at or timezone.now()
        if self.opened_at:
            return max(0, int((end_time - self.opened_at).total_seconds() // 60))
        return 0

    @property
    def is_stale(self):
        if self.status in [self.Status.OPEN, self.Status.CLOSING, self.Status.PENDING_REVIEW]:
            return self.duration_minutes >= 960 # 16 hours
        return False

    @property
    def is_long_running(self):
        if self.status in [self.Status.OPEN, self.Status.CLOSING]:
            return self.duration_minutes >= 720 # 12 hours
        return False

    def __str__(self):
        return f"Shift #{self.shift_number} - {self.user.get_full_name() or self.user.username} [{self.get_status_display()}]"


class ShiftDenomination(models.Model):
    shift = models.ForeignKey(Shift, on_delete=models.CASCADE, related_name='denominations')
    denomination = models.CharField(max_length=20, help_text="Denomination value e.g. 500, 200, 100, 50, 20, 10, 5, 1, COINS")
    unit_value = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    quantity = models.PositiveIntegerField(default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))

    def save(self, *args, **kwargs):
        self.total = Decimal(str(self.quantity)) * Decimal(str(self.unit_value))
        super().save(*args, **kwargs)

    def __str__(self):
        return f"₹{self.denomination} x {self.quantity} = ₹{self.total} (Shift #{self.shift.shift_number})"


class ShiftExpense(models.Model):
    class Category(models.TextChoices):
        CLEANING_SUPPLIES = 'CLEANING_SUPPLIES', 'Cleaning Supplies'
        REFRESHMENTS = 'REFRESHMENTS', 'Tea / Refreshments'
        MAINTENANCE = 'MAINTENANCE', 'Small Maintenance'
        TRANSPORT = 'TRANSPORT', 'Local Transport'
        PRINTING_STATIONERY = 'PRINTING_STATIONERY', 'Printing & Stationery'
        OTHER = 'OTHER', 'Other Operational Expense'

    shift = models.ForeignKey(Shift, on_delete=models.CASCADE, related_name='expenses')
    category = models.CharField(max_length=50, choices=Category.choices, default=Category.OTHER)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.CharField(max_length=255)
    receipt = models.FileField(upload_to='shifts/receipts/', null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_shift_expenses'
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='updated_shift_expenses'
    )
    is_manager_approved = models.BooleanField(default=False)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_shift_expenses'
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Expense: ₹{self.amount} - {self.description} (Shift #{self.shift.shift_number})"


class ShiftCashAdjustment(models.Model):
    class AdjustmentType(models.TextChoices):
        ADD_CASH = 'ADD_CASH', 'Add Cash (Float In)'
        REMOVE_CASH = 'REMOVE_CASH', 'Remove Cash (Float Out / Drop)'

    shift = models.ForeignKey(Shift, on_delete=models.CASCADE, related_name='adjustments')
    adjustment_type = models.CharField(max_length=20, choices=AdjustmentType.choices)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    reason = models.CharField(max_length=255)
    notes = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_shift_adjustments'
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='updated_shift_adjustments'
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_shift_adjustments'
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_adjustment_type_display()}: ₹{self.amount} - {self.reason}"


class ShiftHandover(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending Acceptance'
        ACCEPTED = 'ACCEPTED', 'Accepted'
        REJECTED = 'REJECTED', 'Rejected'

    from_shift = models.ForeignKey(Shift, on_delete=models.CASCADE, related_name='handovers_sent')
    from_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='handovers_given')
    to_shift = models.ForeignKey(Shift, on_delete=models.SET_NULL, null=True, blank=True, related_name='handovers_received')
    to_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='handovers_accepted')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    notes = models.TextField(blank=True, null=True)
    rejection_reason = models.TextField(blank=True, null=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='updated_shift_handovers'
    )
    is_opening_handover = models.BooleanField(default=False, help_text="True if this handover served as the opening float for to_shift")
    handed_over_at = models.DateTimeField(default=timezone.now)
    received_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-handed_over_at']

    def __str__(self):
        return f"Handover: ₹{self.amount} from {self.from_user.username} to {self.to_user.username} [{self.status}]"


class ShiftAuditLog(models.Model):
    shift = models.ForeignKey(Shift, on_delete=models.CASCADE, related_name='audit_logs')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=100, db_index=True)
    description = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.created_at.strftime('%Y-%m-%d %H:%M')}] {self.action} on Shift #{self.shift.shift_number}"
