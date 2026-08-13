from django.db import models
from django.conf import settings
import datetime
from apps.customers.models import Customer
from apps.rooms.models import Room

class Booking(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        CONFIRMED = 'CONFIRMED', 'Confirmed'
        CHECKED_IN = 'CHECKED_IN', 'Checked In'
        COMPLETED = 'COMPLETED', 'Completed'
        CANCELLED = 'CANCELLED', 'Cancelled'
        NO_SHOW = 'NO_SHOW', 'No Show'

    class DiscountType(models.TextChoices):
        PERCENTAGE = 'PERCENTAGE', 'Percentage'
        FIXED = 'FIXED', 'Fixed Amount'

    booking_number = models.CharField(max_length=50, unique=True)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='bookings')
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='bookings')
    
    check_in_date = models.DateField()
    check_in_time = models.TimeField(default=datetime.time(12, 0))
    expected_checkout_date = models.DateField()
    expected_checkout_time = models.TimeField(default=datetime.time(11, 0))
    
    adults = models.PositiveIntegerField(default=1)
    children = models.PositiveIntegerField(default=0)
    
    room_rate = models.DecimalField(max_digits=10, decimal_places=2)
    discount_type = models.CharField(max_length=20, choices=DiscountType.choices, default=DiscountType.FIXED, blank=True, null=True)
    discount_value = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    advance_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.CONFIRMED)
    notes = models.TextField(blank=True, null=True)
    
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_bookings'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def check_in_datetime(self):
        d = self.check_in_date
        if isinstance(d, str):
            try:
                d = datetime.datetime.strptime(d, '%Y-%m-%d').date()
            except ValueError:
                d = datetime.date.today()
        t = self.check_in_time or datetime.time(12, 0)
        if isinstance(t, str):
            try:
                parts = [int(x) for x in t.split(':')]
                t = datetime.time(parts[0], parts[1])
            except Exception:
                t = datetime.time(12, 0)
        return datetime.datetime.combine(d, t)

    @property
    def expected_checkout_datetime(self):
        d = self.expected_checkout_date
        if isinstance(d, str):
            try:
                d = datetime.datetime.strptime(d, '%Y-%m-%d').date()
            except ValueError:
                d = datetime.date.today()
        t = self.expected_checkout_time or datetime.time(11, 0)
        if isinstance(t, str):
            try:
                parts = [int(x) for x in t.split(':')]
                t = datetime.time(parts[0], parts[1])
            except Exception:
                t = datetime.time(11, 0)
        return datetime.datetime.combine(d, t)

    def __str__(self):
        return f"Booking #{self.booking_number} - {self.customer.full_name} (Room {self.room.room_number})"
