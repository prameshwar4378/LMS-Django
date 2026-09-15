from django.db import models
from django.conf import settings
from apps.settings_app.tenant_models import TenantModel
from simple_history.models import HistoricalRecords

class RoomType(TenantModel):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    base_price = models.DecimalField(max_digits=10, decimal_places=2)
    max_adults = models.PositiveIntegerField(default=2)
    max_children = models.PositiveIntegerField(default=2)
    amenities = models.TextField(blank=True, null=True, help_text="Comma-separated or listed amenities")
    show_in_catalogue = models.BooleanField(default=True, help_text="Display this room type on the public digital catalogue")
    catalogue_badge = models.CharField(max_length=50, blank=True, default="", help_text="Promotional chip e.g. Best Value, Most Popular, Luxury")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    def __str__(self):
        return f"{self.name} (₹{self.base_price})"

class Room(TenantModel):
    class Status(models.TextChoices):
        AVAILABLE = 'AVAILABLE', 'Available'
        RESERVED = 'RESERVED', 'Reserved'
        OCCUPIED = 'OCCUPIED', 'Occupied'
        CLEANING = 'CLEANING', 'Cleaning'
        MAINTENANCE = 'MAINTENANCE', 'Maintenance'

    room_number = models.CharField(max_length=50)
    room_type = models.ForeignKey(RoomType, on_delete=models.CASCADE, related_name='rooms')
    floor = models.CharField(max_length=50, blank=True, default='Ground Floor')
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.AVAILABLE,
        db_index=True
    )
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['property', 'room_number'], name='unique_property_room_number')
        ]

    def __str__(self):
        return f"Room {self.room_number} - {self.room_type.name} [{self.status}]"


class RoomDeletionRequest(TenantModel):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending Owner Approval'
        APPROVED = 'APPROVED', 'Approved & Deleted'
        REJECTED = 'REJECTED', 'Rejected by Owner'
        CANCELLED = 'CANCELLED', 'Cancelled'

    room = models.ForeignKey(Room, on_delete=models.SET_NULL, null=True, blank=True, related_name='deletion_requests')
    room_number = models.CharField(max_length=50)
    room_type_name = models.CharField(max_length=100, blank=True)
    floor = models.CharField(max_length=50, blank=True, default='')

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='room_deletion_requests'
    )
    reason = models.TextField(blank=True, default='')
    activity_summary = models.JSONField(default=dict, blank=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_room_deletion_requests'
    )
    review_notes = models.TextField(blank=True, default='')
    reviewed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Deletion Request: Room {self.room_number} [{self.status}]"
