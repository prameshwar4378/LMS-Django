from django.db import models

class Settings(models.Model):
    lodge_name = models.CharField(max_length=200, default="Lodge Management System")
    logo = models.ImageField(upload_to="lodge/", blank=True, null=True)
    address = models.TextField(default="123 Main Street, Station Road, City")
    phone = models.CharField(max_length=50, default="+91 98765 43210")
    email = models.EmailField(default="info@lodgemanagement.com")
    website = models.CharField(max_length=100, default="www.lodgemanagement.com")
    gst_number = models.CharField(max_length=50, default="27AAAAA0000A1Z5")
    
    currency = models.CharField(max_length=10, default="₹")
    tax_enabled = models.BooleanField(default=True)
    tax_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=12.00)
    
    default_checkin_time = models.TimeField(default="12:00:00")
    default_checkout_time = models.TimeField(default="11:00:00")
    
    invoice_prefix = models.CharField(max_length=20, default="INV-")
    booking_prefix = models.CharField(max_length=20, default="BK-")
    stay_prefix = models.CharField(max_length=20, default="STAY-")

    # Configurable Rules
    min_stay_duration_hours = models.IntegerField(default=1)
    max_advance_booking_days = models.IntegerField(default=90)
    room_turnaround_minutes = models.IntegerField(default=0)
    max_receptionist_discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=10.00)
    require_guest_id_on_booking = models.BooleanField(default=False)
    require_guest_id_on_checkin = models.BooleanField(default=True)
    allow_checkout_with_balance = models.BooleanField(default=True)

    @classmethod
    def get_settings(cls):
        obj, _ = cls.objects.get_or_create(id=1)
        return obj

    def __str__(self):
        return self.lodge_name
