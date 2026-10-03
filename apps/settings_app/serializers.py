from rest_framework import serializers
from .models import Settings, WhatsAppMessageLog

class SettingsSerializer(serializers.ModelSerializer):
    gst_number = serializers.CharField(required=False, allow_blank=True, default="")
    website = serializers.CharField(required=False, allow_blank=True, default="")
    phone = serializers.CharField(required=False, allow_blank=True, default="")
    email = serializers.CharField(required=False, allow_blank=True, default="")
    address = serializers.CharField(required=False, allow_blank=True, default="")
    invoice_prefix = serializers.CharField(required=False, allow_blank=True, default="INV-")
    booking_prefix = serializers.CharField(required=False, allow_blank=True, default="BK-")
    stay_prefix = serializers.CharField(required=False, allow_blank=True, default="STAY-")
    manager_override_pin = serializers.CharField(required=False, allow_blank=True, default="1234")
    shift_alert_emails = serializers.CharField(required=False, allow_blank=True, default="")
    shift_alert_phones = serializers.CharField(required=False, allow_blank=True, default="")
    whatsapp_api_url = serializers.CharField(required=False, allow_blank=True, allow_null=True, default="")
    whatsapp_api_key = serializers.CharField(required=False, allow_blank=True, default="")
    whatsapp_default_country_code = serializers.CharField(required=False, allow_blank=True, default="+91")
    whatsapp_open_mode = serializers.CharField(required=False, allow_blank=True, default="universal")
    whatsapp_auto_close_tab = serializers.BooleanField(required=False, default=True)
    whatsapp_close_delay_seconds = serializers.IntegerField(required=False, default=2)
    whatsapp_booking_template = serializers.CharField(required=False, allow_blank=True)
    whatsapp_checkin_template = serializers.CharField(required=False, allow_blank=True)
    whatsapp_payment_template = serializers.CharField(required=False, allow_blank=True)
    whatsapp_checkout_template = serializers.CharField(required=False, allow_blank=True)
    whatsapp_cancellation_template = serializers.CharField(required=False, allow_blank=True)
    whatsapp_extra_charge_template = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = Settings
        fields = '__all__'
        extra_kwargs = {
            'logo': {'required': False, 'allow_null': True},
        }

    def to_internal_value(self, data):
        if hasattr(data, 'copy'):
            data = data.copy()
        else:
            data = dict(data)
        
        # If logo is a string (e.g. existing image URL) or None, do not treat as an uploaded file
        if 'logo' in data and (isinstance(data['logo'], str) or data['logo'] is None):
            data.pop('logo', None)

        return super().to_internal_value(data)


class WhatsAppMessageLogSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = WhatsAppMessageLog
        fields = '__all__'
