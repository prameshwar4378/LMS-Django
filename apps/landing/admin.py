from django.contrib import admin
from .models import LandingInquiry

@admin.register(LandingInquiry)
class LandingInquiryAdmin(admin.ModelAdmin):
    list_display = ('property_name', 'full_name', 'phone', 'email', 'room_count', 'service_interest', 'is_contacted', 'created_at')
    list_filter = ('is_contacted', 'service_interest', 'created_at')
    search_fields = ('property_name', 'full_name', 'phone', 'email', 'city')
    list_editable = ('is_contacted',)
    readonly_fields = ('created_at', 'ip_address')
    date_hierarchy = 'created_at'
