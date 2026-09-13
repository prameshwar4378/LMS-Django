from django.db import models

class LandingInquiry(models.Model):
    INTEREST_CHOICES = [
        ('all', 'Full Cloud PMS Suite (All Features)'),
        ('frontdesk', 'Front-Desk & Stay Lifecycle Engine'),
        ('calendar', 'Interactive Room Tape Chart & Calendar'),
        ('shifts', 'Cash Drawer & Shift Handover Audit'),
        ('catalogue', 'Dynamic Room QR Catalogue & Room Service'),
        ('billing', 'Split GST Billing & 80mm Thermal Invoicing'),
        ('chain', 'Multi-Branch Hotel Chain Management'),
    ]

    full_name = models.CharField(max_length=150, verbose_name="Contact Name")
    property_name = models.CharField(max_length=200, verbose_name="Property / Lodge Name")
    room_count = models.PositiveIntegerField(default=15, verbose_name="Total Rooms")
    phone = models.CharField(max_length=25, verbose_name="Phone Number")
    email = models.EmailField(verbose_name="Email Address")
    city = models.CharField(max_length=100, blank=True, verbose_name="City / Location")
    service_interest = models.CharField(
        max_length=50,
        choices=INTEREST_CHOICES,
        default='all',
        verbose_name="Primary Solution Interest"
    )
    message = models.TextField(blank=True, verbose_name="Inquiry Details / Specific Requirements")
    is_contacted = models.BooleanField(default=False, verbose_name="Followed Up / Contacted")
    admin_notes = models.TextField(blank=True, verbose_name="Internal Admin Notes")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Received At")

    class Meta:
        verbose_name = "Demo & Lead Inquiry"
        verbose_name_plural = "Demo & Lead Inquiries"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.property_name} ({self.full_name}) - {self.phone}"
