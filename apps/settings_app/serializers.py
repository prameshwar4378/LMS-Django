from rest_framework import serializers
from .models import Settings

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
