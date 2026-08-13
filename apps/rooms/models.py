from django.db import models

class RoomType(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    base_price = models.DecimalField(max_digits=10, decimal_places=2)
    max_adults = models.PositiveIntegerField(default=2)
    max_children = models.PositiveIntegerField(default=2)
    amenities = models.TextField(blank=True, null=True, help_text="Comma-separated or listed amenities")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} (₹{self.base_price})"

class Room(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = 'AVAILABLE', 'Available'
        RESERVED = 'RESERVED', 'Reserved'
        OCCUPIED = 'OCCUPIED', 'Occupied'
        CLEANING = 'CLEANING', 'Cleaning'
        MAINTENANCE = 'MAINTENANCE', 'Maintenance'

    room_number = models.CharField(max_length=50, unique=True)
    room_type = models.ForeignKey(RoomType, on_delete=models.CASCADE, related_name='rooms')
    floor = models.CharField(max_length=50, blank=True, default='Ground Floor')
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.AVAILABLE
    )
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Room {self.room_number} - {self.room_type.name} [{self.status}]"
