from django.db import models
from django.conf import settings
from django.utils import timezone
from apps.stays.models import Stay
from apps.settings_app.tenant_models import TenantModel

class ChargeType(TenantModel):
    name = models.CharField(max_length=100)
    default_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['property', 'name'], name='unique_property_charge_type_name')
        ]

    def __str__(self):
        return f"{self.name} (₹{self.default_price})"

class ExtraCharge(models.Model):
    stay = models.ForeignKey(Stay, on_delete=models.CASCADE, related_name='extra_charges')
    charge_type = models.ForeignKey(ChargeType, on_delete=models.SET_NULL, null=True, blank=True, related_name='extra_charges')
    description = models.CharField(max_length=255)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    charge_date = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_extra_charges'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        self.amount = self.quantity * self.unit_price
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.description} x{self.quantity} - ₹{self.amount} (Stay #{self.stay.stay_number})"

class Payment(TenantModel):
    class PaymentMethod(models.TextChoices):
        CASH = 'CASH', 'Cash'
        UPI = 'UPI', 'UPI'
        CARD = 'CARD', 'Card'
        BANK_TRANSFER = 'BANK_TRANSFER', 'Bank Transfer'
        OTHER = 'OTHER', 'Other'

    payment_number = models.CharField(max_length=50, unique=True)
    customer = models.ForeignKey('customers.Customer', on_delete=models.SET_NULL, null=True, blank=True, related_name='payments')
    stay = models.ForeignKey(Stay, on_delete=models.CASCADE, null=True, blank=True, related_name='payments')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices, default=PaymentMethod.CASH)
    transaction_reference = models.CharField(max_length=100, blank=True, null=True)
    payment_date = models.DateTimeField(default=timezone.now)
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='received_payments'
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_payments'
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='updated_payments'
    )
    shift = models.ForeignKey(
        'shifts.Shift',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payments'
    )
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.created_by and self.received_by:
            self.created_by = self.received_by
        elif not self.received_by and self.created_by:
            self.received_by = self.created_by

        if not self.shift:
            responsible_user = self.received_by or self.created_by
            if responsible_user:
                try:
                    from apps.shifts.services import get_active_shift_for_user
                    active_shift = get_active_shift_for_user(responsible_user, auto_create_in_single_mode=False)
                    if active_shift:
                        self.shift = active_shift
                except Exception:
                    pass
        if not self.property:
            if self.shift and getattr(self.shift, 'property', None):
                self.property = self.shift.property
            elif self.stay and getattr(self.stay, 'property', None):
                self.property = self.stay.property
            elif self.received_by and getattr(self.received_by, 'property', None):
                self.property = self.received_by.property

        super().save(*args, **kwargs)

    def __str__(self):
        return f"Payment #{self.payment_number} - ₹{self.amount} via {self.get_payment_method_display()}"

class Invoice(TenantModel):
    invoice_number = models.CharField(max_length=50, unique=True)
    stay = models.OneToOneField(Stay, on_delete=models.CASCADE, related_name='invoice')
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    discount = models.DecimalField(max_digits=10, decimal_places=2)
    tax = models.DecimalField(max_digits=10, decimal_places=2)
    grand_total = models.DecimalField(max_digits=10, decimal_places=2)
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2)
    balance = models.DecimalField(max_digits=10, decimal_places=2)
    generated_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Invoice #{self.invoice_number} - Stay #{self.stay.stay_number}"
