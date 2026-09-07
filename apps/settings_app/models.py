from django.db import models

class Settings(models.Model):
    lodge_name = models.CharField(max_length=200, default="Lodge Management System")
    logo = models.ImageField(upload_to="lodge/", blank=True, null=True)
    address = models.TextField(default="123 Main Street, Station Road, City", blank=True)
    phone = models.CharField(max_length=50, default="+91 98765 43210", blank=True)
    email = models.EmailField(default="info@lodgemanagement.com", blank=True)
    website = models.CharField(max_length=100, default="www.lodgemanagement.com", blank=True)
    gst_number = models.CharField(max_length=50, default="", blank=True)
    
    currency = models.CharField(max_length=10, default="₹", blank=True)
    tax_enabled = models.BooleanField(default=True)
    tax_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=12.00)
    
    default_checkin_time = models.TimeField(default="12:00:00")
    default_checkout_time = models.TimeField(default="11:00:00")
    
    invoice_prefix = models.CharField(max_length=20, default="INV-", blank=True)
    booking_prefix = models.CharField(max_length=20, default="BK-", blank=True)
    stay_prefix = models.CharField(max_length=20, default="STAY-", blank=True)

    # Configurable Rules
    min_stay_duration_hours = models.IntegerField(default=1)
    max_advance_booking_days = models.IntegerField(default=90)
    room_turnaround_minutes = models.IntegerField(default=0)
    max_receptionist_discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=10.00)
    require_guest_id_on_booking = models.BooleanField(default=False)
    require_guest_id_on_checkin = models.BooleanField(default=True)
    allow_checkout_with_balance = models.BooleanField(default=True)

    # Shift & Cashier Operating Mode
    class ShiftOperationMode(models.TextChoices):
        STRICT_SHIFT = 'STRICT_SHIFT', 'Multi-Cashier Shift Mode'
        SINGLE_OPERATOR = 'SINGLE_OPERATOR', 'Single-User / Owner-Managed Mode'

    shift_operation_mode = models.CharField(
        max_length=30,
        choices=ShiftOperationMode.choices,
        default=ShiftOperationMode.STRICT_SHIFT,
        help_text="Operating mode: Strict Shift-wise vs Single-Operator / Owner Mode"
    )
    auto_rollover_daily_till = models.BooleanField(
        default=True,
        help_text="Automatically roll over physical cash drawer daily in single-operator mode"
    )

    # Automated Shift Closing Notifications & Security
    enable_blind_till_closing = models.BooleanField(default=False, help_text="Hide expected cash ledger from receptionists during shift closing")
    notify_shift_close_email = models.BooleanField(default=True)
    notify_shift_close_whatsapp = models.BooleanField(default=True)
    shift_alert_emails = models.CharField(max_length=500, blank=True, default="", help_text="Comma-separated manager emails for shift alerts")
    shift_alert_phones = models.CharField(max_length=500, blank=True, default="", help_text="Comma-separated mobile numbers with country code for WhatsApp alerts")
    whatsapp_api_url = models.URLField(blank=True, null=True, help_text="Custom WhatsApp Gateway API URL (optional)")
    whatsapp_api_key = models.CharField(max_length=255, blank=True, default="", help_text="WhatsApp Gateway Token / Key (optional)")

    # Petty Cash Limits & Manager Governance
    manager_override_pin = models.CharField(max_length=20, default="1234", blank=True, help_text="Manager PIN for approving high expenses")
    daily_petty_cash_cap = models.DecimalField(max_digits=10, decimal_places=2, default=5000.00, blank=True, null=True, help_text="Maximum aggregate petty cash allowed per day/shift across property")
    max_cash_expense_without_approval = models.DecimalField(max_digits=10, decimal_places=2, default=1000.00, blank=True, null=True, help_text="Maximum cash expense without requiring manager PIN authorization")

    property = models.OneToOneField(
        'settings_app.Property',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='settings'
    )

    @classmethod
    def get_settings(cls, prop=None):
        if prop:
            obj, _ = cls.objects.get_or_create(
                property=prop,
                defaults={
                    'lodge_name': prop.name,
                    'address': prop.address or "123 Main Street, Station Road, City",
                    'phone': prop.owner_phone or "+91 98765 43210",
                    'email': prop.owner_email or "info@lodgemanagement.com",
                    'gst_number': prop.gstin or ""
                }
            )
            return obj
        obj = cls.objects.first()
        if not obj:
            obj = cls.objects.create()
        return obj

    def __str__(self):
        return f"{self.lodge_name} ({self.property.code if self.property else 'Default'})"


import secrets
import string
from django.utils import timezone
from datetime import timedelta

def generate_crypto_license_key():
    chars = string.ascii_uppercase + string.digits
    seg1 = ''.join(secrets.choice(chars) for _ in range(4))
    seg2 = ''.join(secrets.choice(chars) for _ in range(4))
    seg3 = ''.join(secrets.choice(chars) for _ in range(4))
    return f"LMS-{seg1}-{seg2}-{seg3}"

class Property(models.Model):
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50, unique=True, db_index=True)
    subdomain = models.CharField(max_length=100, blank=True, null=True, unique=True)
    owner_name = models.CharField(max_length=150)
    owner_email = models.EmailField()
    owner_phone = models.CharField(max_length=30)
    address = models.TextField(blank=True, default="")
    city = models.CharField(max_length=100, blank=True, default="")
    state = models.CharField(max_length=100, blank=True, default="")
    pincode = models.CharField(max_length=20, blank=True, default="")
    gstin = models.CharField(max_length=50, blank=True, default="")
    total_rooms = models.IntegerField(default=10)
    is_active = models.BooleanField(default=True)
    class OperationMode(models.TextChoices):
        SHIFT_WISE = 'SHIFT_WISE', 'Shift-Wise (Multi-Staff Shifts)'
        SINGLE_OWNER = 'SINGLE_OWNER', 'Single Owner (No Shifts / Direct)'

    operation_mode = models.CharField(
        max_length=30,
        choices=OperationMode.choices,
        default=OperationMode.SHIFT_WISE,
        help_text="Operational mode set by platform developer: Shift-Wise vs Single Owner"
    )
    parent_property = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='branches'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def get_operation_mode(self):
        if self.parent_property and not self.operation_mode:
            return self.parent_property.get_operation_mode()
        return self.operation_mode or self.OperationMode.SHIFT_WISE

    @property
    def is_shift_wise(self):
        return self.get_operation_mode() != self.OperationMode.SINGLE_OWNER

    @property
    def is_single_owner(self):
        return self.get_operation_mode() == self.OperationMode.SINGLE_OWNER

    def get_root_property(self):
        """
        Returns the top-level parent (main hotel) for this branch or property.
        """
        curr = self
        visited = set()
        while curr.parent_property and curr.id not in visited:
            visited.add(curr.id)
            curr = curr.parent_property
        return curr

    def get_subscription(self):
        """
        Returns active subscription object for this property or its parent brand property.
        If no direct subscription exists on this property, it resolves the root parent hotel's subscription.
        """
        # 1. Direct subscription on this specific property
        direct_sub = PropertySubscription.objects.filter(lodge=self).first()
        if direct_sub:
            return direct_sub

        # 2. Inherit from root/parent property
        root_prop = self.get_root_property()
        if root_prop and root_prop != self:
            parent_sub = PropertySubscription.objects.filter(lodge=root_prop).first()
            if parent_sub:
                return parent_sub

        # 3. Fallback: If primary hotel has no subscription record in DB, self-heal with active starter plan
        if not self.parent_property:
            starter_plan = SubscriptionPlan.objects.filter(code='STARTER').first() or SubscriptionPlan.objects.first()
            if starter_plan:
                sub = PropertySubscription.objects.create(
                    lodge=self,
                    plan=starter_plan,
                    valid_from=timezone.now().date(),
                    valid_until=timezone.now().date() + timedelta(days=365),
                    billing_cycle='ANNUAL',
                    is_paid=True
                )
                return sub

        return None

    def is_subscription_expired(self):
        sub = self.get_subscription()
        if not sub:
            return True
        return sub.is_expired()

    def subscription_days_remaining(self):
        sub = self.get_subscription()
        if not sub:
            return 0
        return sub.days_remaining()

    def get_max_rooms_allowed(self):
        """
        Returns the maximum number of rooms permitted for this hotel.
        Prioritizes the exact room capacity explicitly configured by the platform administrator (self.total_rooms).
        If not set, falls back to the active subscription plan limit (sub.plan.max_rooms).
        """
        if self.total_rooms and self.total_rooms > 0:
            return self.total_rooms
        sub = self.get_subscription()
        if sub and sub.plan and sub.plan.max_rooms:
            return sub.plan.max_rooms
        return 15

    def is_suspended(self):
        """
        A property is considered suspended if:
        1. It is directly marked inactive (self.is_active is False), OR
        2. Its root parent hotel is marked inactive (root.is_active is False).
        """
        if not self.is_active:
            return True
        root = self.get_root_property()
        if root and not root.is_active:
            return True
        return False

    def is_operational(self):
        """
        Returns True only if the property and its root parent are fully active.
        """
        return not self.is_suspended()

    def __str__(self):
        return f"{self.name} ({self.code})"


class SubscriptionPlan(models.Model):
    class PlanTier(models.TextChoices):
        FREE_TRIAL = 'FREE_TRIAL', 'Free Trial (14 Days)'
        STARTER = 'STARTER', 'Starter (Up to 15 Rooms)'
        GROWTH = 'GROWTH', 'Growth (Up to 40 Rooms)'
        ENTERPRISE = 'ENTERPRISE', 'Enterprise (Unlimited Rooms)'
        CUSTOM = 'CUSTOM', 'Custom / Bespoke Plan'

    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50, unique=True)
    max_rooms = models.IntegerField(default=15)
    price_monthly = models.DecimalField(max_digits=10, decimal_places=2, default=999.00)
    price_annually = models.DecimalField(max_digits=10, decimal_places=2, default=9999.00)
    features = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class PropertySubscription(models.Model):
    class BillingCycle(models.TextChoices):
        MONTHLY = 'MONTHLY', 'Monthly'
        ANNUAL = 'ANNUAL', 'Annual'
        LIFETIME = 'LIFETIME', 'Lifetime / Custom'

    lodge = models.OneToOneField(Property, on_delete=models.CASCADE, related_name='subscription')
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.SET_NULL, null=True, blank=True, related_name='subscriptions')
    billing_cycle = models.CharField(max_length=20, choices=BillingCycle.choices, default=BillingCycle.ANNUAL)
    billing_amount = models.DecimalField(max_digits=10, decimal_places=2, default=9999.00)
    payment_status = models.CharField(max_length=20, default='PAID')
    valid_from = models.DateField(default=timezone.now)
    valid_until = models.DateField()
    is_paid = models.BooleanField(default=True)
    license_key = models.CharField(max_length=50, null=True, blank=True, default=None)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def get_valid_until_date(self):
        if not self.valid_until:
            return None
        target = self.valid_until
        if isinstance(target, str):
            from datetime import datetime
            try:
                return datetime.strptime(target.split('T')[0], '%Y-%m-%d').date()
            except Exception:
                return None
        if hasattr(target, 'date') and not isinstance(target, type(timezone.now().date())):
            return target.date()
        return target

    def save(self, *args, **kwargs):
        if self.payment_status:
            self.is_paid = (str(self.payment_status).strip().upper() == 'PAID')
        target = self.get_valid_until_date()
        if target:
            self.valid_until = target
        super().save(*args, **kwargs)

    def is_expired(self):
        target = self.get_valid_until_date()
        if not target:
            return False
        return timezone.now().date() > target

    def days_remaining(self):
        target = self.get_valid_until_date()
        if not target:
            return 0
        diff = (target - timezone.now().date()).days
        return max(0, diff)

    def is_near_expiry(self, days=15):
        if self.is_expired():
            return False
        return 0 < self.days_remaining() <= days

    @property
    def urgency_level(self):
        if self.is_expired():
            return 'EXPIRED'
        rem = self.days_remaining()
        if rem <= 5:
            return 'CRITICAL'
        elif rem <= 10:
            return 'HIGH'
        elif rem <= 15:
            return 'MODERATE'
        return 'NORMAL'

    def __str__(self):
        return f"{self.lodge.name} - {self.plan.name if self.plan else 'No Plan'} (Exp: {self.valid_until})"

