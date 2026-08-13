from rest_framework import serializers
from .models import Booking
from apps.customers.serializers import CustomerSerializer
from apps.rooms.serializers import RoomSerializer
from apps.settings_app.models import Settings
import datetime

class BookingSerializer(serializers.ModelSerializer):
    customer_detail = CustomerSerializer(source='customer', read_only=True)
    room_detail = RoomSerializer(source='room', read_only=True)
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    check_in_datetime_str = serializers.CharField(source='check_in_datetime', read_only=True)
    expected_checkout_datetime_str = serializers.CharField(source='expected_checkout_datetime', read_only=True)

    class Meta:
        model = Booking
        fields = '__all__'
        read_only_fields = ('booking_number', 'created_by', 'created_at', 'updated_at')

    def validate(self, attrs):
        from .services import validate_booking_payload
        user = self.context['request'].user if 'request' in self.context else None
        is_walkin = self.context.get('is_walkin', False)
        validated_attrs, errors = validate_booking_payload(
            attrs,
            user=user,
            instance=self.instance,
            is_walkin=is_walkin
        )
        if errors:
            raise serializers.ValidationError(errors)
        attrs.update(validated_attrs)
        return attrs

    def create(self, validated_data):
        import uuid
        settings_obj = Settings.get_settings()
        prefix = settings_obj.booking_prefix or "BK-"
        today_str = datetime.date.today().strftime('%Y%m%d')
        
        # Ensure unique booking_number under concurrent/batch group requests
        for attempt in range(50):
            count = Booking.objects.filter(booking_number__startswith=f"{prefix}{today_str}").count() + 1 + attempt
            b_num = f"{prefix}{today_str}-{count:03d}"
            if not Booking.objects.filter(booking_number=b_num).exists():
                validated_data['booking_number'] = b_num
                break
        else:
            validated_data['booking_number'] = f"{prefix}{today_str}-{uuid.uuid4().hex[:4].upper()}"

        if 'request' in self.context and self.context['request'].user.is_authenticated:
            validated_data['created_by'] = self.context['request'].user

        return super().create(validated_data)
