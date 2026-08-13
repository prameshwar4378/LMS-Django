from django.db import models
from django.conf import settings
import datetime
from apps.customers.models import Customer
from apps.rooms.models import Room
from apps.bookings.models import Booking

class Stay(models.Model):
    class Status(models.TextChoices):
        RESERVED = 'RESERVED', 'Reserved'
        CHECKED_IN = 'CHECKED_IN', 'Checked In'
        CHECKED_OUT = 'CHECKED_OUT', 'Checked Out'
        CANCELLED = 'CANCELLED', 'Cancelled'

    class DiscountType(models.TextChoices):
        PERCENTAGE = 'PERCENTAGE', 'Percentage'
        FIXED = 'FIXED', 'Fixed Amount'

    stay_number = models.CharField(max_length=50, unique=True)
    booking = models.ForeignKey(Booking, on_delete=models.SET_NULL, null=True, blank=True, related_name='stays')
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='stays')
    primary_customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='stays')
    
    check_in_date = models.DateField()
    check_in_time = models.TimeField(default=datetime.time(12, 0))
    expected_checkout_date = models.DateField()
    expected_checkout_time = models.TimeField(default=datetime.time(11, 0))
    actual_checkout_date = models.DateField(null=True, blank=True)
    actual_checkout_time = models.TimeField(null=True, blank=True)
    
    adults = models.PositiveIntegerField(default=1)
    children = models.PositiveIntegerField(default=0)
    room_rate = models.DecimalField(max_digits=10, decimal_places=2)
    
    discount_type = models.CharField(max_length=20, choices=DiscountType.choices, default=DiscountType.FIXED)
    discount_value = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    discount_reason = models.CharField(max_length=255, blank=True, null=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.CHECKED_IN)
    
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_stays'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def check_in_datetime(self):
        t = self.check_in_time or datetime.time(12, 0)
        return datetime.datetime.combine(self.check_in_date, t)

    @property
    def expected_checkout_datetime(self):
        t = self.expected_checkout_time or datetime.time(11, 0)
        return datetime.datetime.combine(self.expected_checkout_date, t)

    @property
    def actual_checkout_datetime(self):
        if self.actual_checkout_date:
            t = self.actual_checkout_time or datetime.time(11, 0)
            return datetime.datetime.combine(self.actual_checkout_date, t)
        return self.expected_checkout_datetime

    def __str__(self):
        return f"Stay #{self.stay_number} - Room {self.room.room_number} ({self.primary_customer.full_name})"

class StayGuest(models.Model):
    stay = models.ForeignKey(Stay, on_delete=models.CASCADE, related_name='guests')
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, related_name='guest_stays')
    guest_name = models.CharField(max_length=200)
    age = models.PositiveIntegerField(null=True, blank=True)
    gender = models.CharField(max_length=10, choices=Customer.Gender.choices, default=Customer.Gender.MALE)
    mobile = models.CharField(max_length=20, blank=True, null=True)
    relationship = models.CharField(max_length=100, blank=True, null=True)
    
    id_type = models.CharField(max_length=50, choices=Customer.IDType.choices, blank=True, null=True)
    id_number = models.CharField(max_length=100, blank=True, null=True)
    id_document = models.FileField(upload_to='guests/documents/', blank=True, null=True)
    id_document_back = models.FileField(upload_to='guests/documents/', blank=True, null=True)
    photo = models.ImageField(upload_to='guests/photos/', blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.guest_name} ({self.relationship or 'Guest'}) - Stay #{self.stay.stay_number}"
