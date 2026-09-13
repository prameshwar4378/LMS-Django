from django.db import models
from apps.settings_app.tenant_models import TenantModel

DEFAULT_FACILITIES = [
    {"key": "wifi", "label": "Free High-Speed Wi-Fi", "icon": "Wifi", "enabled": True},
    {"key": "ac", "label": "Air Conditioning", "icon": "Wind", "enabled": True},
    {"key": "power_backup", "label": "24/7 Power Backup", "icon": "Zap", "enabled": True},
    {"key": "lift", "label": "Elevator / Lift", "icon": "ArrowUpDown", "enabled": True},
    {"key": "parking", "label": "Free Secure Parking", "icon": "Car", "enabled": True},
    {"key": "restaurant", "label": "In-House Dining / Food", "icon": "Utensils", "enabled": True},
    {"key": "cctv", "label": "CCTV & 24/7 Security", "icon": "ShieldCheck", "enabled": True},
    {"key": "room_service", "label": "24/7 Room Service", "icon": "Bell", "enabled": True},
    {"key": "hot_water", "label": "24h Hot & Cold Water", "icon": "Droplets", "enabled": True},
    {"key": "doctor", "label": "Doctor on Call", "icon": "HeartPulse", "enabled": True},
]

DEFAULT_FAQS = [
    {
        "id": "checkin-timings",
        "category": "checkin",
        "icon": "Clock",
        "q": "What are the standard Check-in and Check-out timings?",
        "a": "Standard Check-in begins at 12:00 PM onwards, and Check-out is until 11:00 AM. Early check-in and late check-out can be arranged upon request, subject to room availability upon arrival. Our front desk concierge also provides secure, complimentary luggage holding so you can explore the city without burden.",
        "highlights": ["Standard Check-In: 12:00 PM", "Check-Out: 11:00 AM", "Free Luggage Storage", "24/7 Front Desk Active"]
    },
    {
        "id": "gov-id-docs",
        "category": "checkin",
        "icon": "ShieldCheck",
        "q": "What government identification documents are required at Check-in?",
        "a": "In accordance with local hospitality and government regulations, all adult occupants must present an original, valid government-issued photo ID at check-in (Aadhaar Card, Passport, Voter ID, or Driving License). Please note that PAN cards are not accepted as valid residential address proof.",
        "highlights": ["Aadhaar / Passport / DL Accepted", "Mandatory for All Adults", "Instant Front Desk Verification"]
    },
    {
        "id": "wifi-power-amenities",
        "category": "amenities",
        "icon": "Wifi",
        "q": "Are high-speed Wi-Fi, power backup, and vehicle parking complimentary?",
        "a": "Yes! All registered guests enjoy complimentary high-speed dual-band fiber Wi-Fi across all suites and public lounges. The property is equipped with 24/7 heavy-duty automatic generator backup so air conditioning and power never get interrupted. We also provide free guarded parking for four-wheelers and two-wheelers.",
        "highlights": ["Free Ultra-Fast Fiber Wi-Fi", "24/7 Heavy Generator Backup", "Complimentary Guarded Parking"]
    },
    {
        "id": "dining-room-service",
        "category": "dining",
        "icon": "Utensils",
        "q": "Is in-room dining and 24-hour room service available?",
        "a": "Yes, our kitchen and guest room service operate around the clock. You can order fresh multi-cuisine specialties, regional delicacies, hot tea/coffee, snacks, and late-night meals delivered directly to your door with a single call to reception.",
        "highlights": ["24-Hour Kitchen & Room Service", "Fresh Multi-Cuisine Menu", "Quick Contact Dial"]
    },
    {
        "id": "best-rate-guarantee",
        "category": "booking",
        "icon": "Sparkles",
        "q": "Why should I book directly through this digital catalogue?",
        "a": "Direct bookings through our official digital showcase come with our 100% Best Rate Guarantee. Unlike third-party booking portals (OTA) that add high commissions and hidden processing fees, direct booking ensures the lowest available tariff, complimentary room upgrade priority, and priority check-in handling.",
        "highlights": ["Best Rate Guarantee (0% Commission)", "Priority Room Upgrades", "Direct Reception Confirmation"]
    },
    {
        "id": "cancellation-refund",
        "category": "booking",
        "icon": "CheckCircle2",
        "q": "What is the cancellation and refund policy for reservations?",
        "a": "We understand plans change. Direct reservations enjoy free cancellation up to 24 hours prior to standard check-in time with a full 100% instant refund. For last-minute modifications or emergency date changes, our front desk team is always ready to assist you flexibly.",
        "highlights": ["Free Cancellation (up to 24h)", "100% Refund Assurance", "Flexible Date Rescheduling"]
    },
    {
        "id": "location-transit",
        "category": "location",
        "icon": "Car",
        "q": "How accessible is the hotel from railway stations and transit hubs?",
        "a": "Our property is strategically located with quick access to the central railway junction, primary intercity bus terminal, and major highway routes. Ride-hailing cabs, auto-rickshaws, and express transit options are available directly outside our main entrance 24/7.",
        "highlights": ["Prime Central Location", "Easy Transit & Cab Access", "One-Tap Google Maps Navigation"]
    },
    {
        "id": "groups-corporate",
        "category": "booking",
        "icon": "Building",
        "q": "Can I book multiple suites for corporate events or family gatherings?",
        "a": "Absolutely! We offer specialized group tariff packages, corporate billing vouchers, and coordinated adjacent room arrangements for family weddings, business conferences, and group tours. Contact our manager directly via WhatsApp or the direct reservation form for tailored group quotes.",
        "highlights": ["Group Discounts Available", "Corporate Invoicing & GST", "Dedicated Concierge Coordinator"]
    }
]

DEFAULT_REVIEWS = [
    {
        "id": "rev-1",
        "guest_name": "Rohit Sharma",
        "stay_type": "Corporate Traveler",
        "rating": 5,
        "stay_date": "Recent Stay",
        "review_text": "Outstanding cleanliness, courteous front desk, and high-speed Wi-Fi that made remote meetings seamless. The 24/7 power backup gave total peace of mind. Highly recommended!"
    },
    {
        "id": "rev-2",
        "guest_name": "Pooja & Ankit Deshmukh",
        "stay_type": "Family Vacation",
        "rating": 5,
        "stay_date": "Recent Stay",
        "review_text": "We stayed for three nights with kids. Spacious suites, spotless washrooms, and very prompt room service. Booking directly through this digital catalogue gave us the best price!"
    },
    {
        "id": "rev-3",
        "guest_name": "Vikramaditya Rao",
        "stay_type": "Verified Direct Guest",
        "rating": 5,
        "stay_date": "Recent Stay",
        "review_text": "Effortless direct booking, immediate WhatsApp voucher, and zero hidden platform fees. Truly 5-star hospitality at unbeatable direct tariffs."
    }
]

DEFAULT_RATING_SUMMARY = {
    "overall_rating": 4.9,
    "total_reviews_text": "Based on 420+ authentic verified guest stay experiences",
    "categories": [
        {"label": "Cleanliness & Hygiene Standards", "score": 4.9, "progress": 98, "color": "success"},
        {"label": "Staff Hospitality & Service", "score": 4.9, "progress": 97, "color": "primary"},
        {"label": "Prime Location & Accessibility", "score": 4.8, "progress": 96, "color": "warning"},
        {"label": "Room Comfort & Bedding Quality", "score": 4.9, "progress": 98, "color": "info"}
    ]
}

DEFAULT_NEARBY_PLACES = [
    {"id": "place-1", "icon": "train", "name": "Central Railway Station", "distance": "~ 2.5 km", "duration": "7 mins"},
    {"id": "place-2", "icon": "bus", "name": "Main Bus Terminal", "distance": "~ 1.2 km", "duration": "4 mins"},
    {"id": "place-3", "icon": "monument", "name": "Heritage & Temple Site", "distance": "~ 1.0 km", "duration": "3 mins"}
]

DEFAULT_STATS = [
    {"label": "Direct Booking Guarantee", "value": "100%", "color": "primary"},
    {"label": "Front Desk & Concierge", "value": "24 / 7", "color": "success"}
]

DEFAULT_PRIVILEGES = [
    "Best Rate Guarantee (0% Commission)",
    "Priority Room Upgrades on Direct Booking",
    "Complimentary Dual-Band Fiber Wi-Fi",
    "Instant WhatsApp Confirmation Voucher"
]

def default_facilities_list():
    import copy
    return copy.deepcopy(DEFAULT_FACILITIES)

def default_faqs_list():
    import copy
    return copy.deepcopy(DEFAULT_FAQS)

def default_reviews_list():
    import copy
    return copy.deepcopy(DEFAULT_REVIEWS)

def default_rating_summary():
    import copy
    return copy.deepcopy(DEFAULT_RATING_SUMMARY)

def default_nearby_places():
    import copy
    return copy.deepcopy(DEFAULT_NEARBY_PLACES)

def default_stats_list():
    import copy
    return copy.deepcopy(DEFAULT_STATS)

def default_privileges_list():
    import copy
    return copy.deepcopy(DEFAULT_PRIVILEGES)

class HotelCatalogueConfig(TenantModel):
    class Theme(models.TextChoices):
        BLUE = 'BLUE', 'Royal Blue'
        EMERALD = 'EMERALD', 'Emerald Luxury'
        GOLD = 'GOLD', 'Golden Amber'
        ROSE = 'ROSE', 'Rose Elegance'
        SLATE = 'SLATE', 'Modern Dark Slate'

    is_published = models.BooleanField(default=True, help_text="Whether this hotel/branch catalogue is publicly accessible")
    hero_headline = models.CharField(max_length=200, blank=True, default="", help_text="Custom banner headline (defaults to hotel name if blank)")
    hero_tagline = models.CharField(max_length=250, blank=True, default="", help_text="Subtitle or marketing tagline")
    about_title = models.CharField(max_length=200, blank=True, default="Our Heritage & Signature Hospitality")
    about_text = models.TextField(blank=True, default="", help_text="Detailed story or welcome message")
    hero_banner = models.ImageField(upload_to="catalogue/banners/", blank=True, null=True)
    accent_theme = models.CharField(max_length=20, choices=Theme.choices, default=Theme.BLUE)

    # Quick Stats & Direct Privileges
    stats_json = models.JSONField(default=default_stats_list, blank=True)
    direct_privileges_json = models.JSONField(default=default_privileges_list, blank=True)

    # Public Contacts
    contact_phone = models.CharField(max_length=30, blank=True, default="")
    whatsapp_number = models.CharField(max_length=30, blank=True, default="")
    contact_email = models.EmailField(blank=True, default="")

    # Physical Location, Google Maps & Nearby Transit
    address_override = models.TextField(blank=True, default="")
    city_override = models.CharField(max_length=100, blank=True, default="")
    google_maps_embed_url = models.TextField(blank=True, default="", help_text="Google Maps iframe embed src URL")
    google_maps_directions_url = models.URLField(blank=True, default="", help_text="Shareable Google Maps link for navigation")
    landmark = models.CharField(max_length=200, blank=True, default="")
    nearby_places_json = models.JSONField(default=default_nearby_places, blank=True)

    # Facilities checklist
    facilities_json = models.JSONField(default=default_facilities_list, blank=True)

    # Policies & Timings
    check_in_time = models.CharField(max_length=20, default="12:00 PM")
    check_out_time = models.CharField(max_length=20, default="11:00 AM")
    cancellation_policy = models.TextField(
        blank=True,
        default="Free cancellation up to 24 hours prior to check-in. Cancellations after that are subject to one night's charge."
    )
    house_rules = models.TextField(
        blank=True,
        default="Valid government ID required at check-in (Aadhaar / Passport / Voter ID). Couples and families welcome."
    )

    # Dynamic FAQs
    faqs_json = models.JSONField(default=default_faqs_list, blank=True)

    # Dynamic Ratings & Reviews
    show_reviews = models.BooleanField(default=True)
    rating_summary_json = models.JSONField(default=default_rating_summary, blank=True)
    reviews_json = models.JSONField(default=default_reviews_list, blank=True)

    # Social links
    instagram_url = models.URLField(blank=True, default="")
    facebook_url = models.URLField(blank=True, default="")
    website_url = models.URLField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['property'], name='unique_catalogue_property')
        ]

    def __str__(self):
        prop_name = self.property.name if self.property else "Global"
        return f"Catalogue Config for {prop_name}"


class HotelGalleryPhoto(TenantModel):
    image = models.ImageField(upload_to="catalogue/gallery/")
    caption = models.CharField(max_length=150, blank=True, default="")
    display_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['display_order', 'id']

    def __str__(self):
        prop_name = self.property.name if self.property else "Global"
        return f"Gallery Photo for {prop_name} ({self.caption or 'No caption'})"


class RoomTypePhoto(models.Model):
    room_type = models.ForeignKey('rooms.RoomType', on_delete=models.CASCADE, related_name='photos')
    image = models.ImageField(upload_to="catalogue/rooms/")
    caption = models.CharField(max_length=150, blank=True, default="")
    display_order = models.PositiveIntegerField(default=0)
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['display_order', '-is_primary', 'id']

    def __str__(self):
        return f"Photo for {self.room_type.name} (order: {self.display_order})"


class CatalogueInquiry(TenantModel):
    class Status(models.TextChoices):
        NEW = 'NEW', 'New Lead'
        CONTACTED = 'CONTACTED', 'Contacted / In Progress'
        CONVERTED = 'CONVERTED', 'Converted to Booking'
        DECLINED = 'DECLINED', 'Declined / Closed'

    guest_name = models.CharField(max_length=150)
    guest_mobile = models.CharField(max_length=30)
    guest_email = models.EmailField(blank=True, default="")
    requested_room_type = models.ForeignKey('rooms.RoomType', on_delete=models.SET_NULL, null=True, blank=True)
    check_in_date = models.DateField(null=True, blank=True)
    check_out_date = models.DateField(null=True, blank=True)
    adults = models.PositiveIntegerField(default=2)
    children = models.PositiveIntegerField(default=0)
    message = models.TextField(blank=True, default="")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Inquiry from {self.guest_name} ({self.guest_mobile}) - {self.status}"
