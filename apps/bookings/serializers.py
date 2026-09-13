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
    stay_id = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Booking
        fields = '__all__'
        read_only_fields = ('booking_number', 'created_by', 'created_at', 'updated_at')

    def get_stay_id(self, obj):
        stay = obj.stays.first()
        return stay.id if stay else None

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
        from apps.billing.services import generate_unique_booking_number
        from django.db import transaction, IntegrityError
        excess_advance = validated_data.pop('excess_advance', 0.0)
        validated_data.pop('chargeable_nights', None)
        validated_data.pop('_history_user', None)

        if 'request' in self.context and self.context['request'].user.is_authenticated:
            validated_data['created_by'] = self.context['request'].user

        if not validated_data.get('property'):
            room = validated_data.get('room')
            if room and getattr(room, 'property', None):
                validated_data['property'] = room.property
            elif 'request' in self.context and getattr(self.context['request'].user, 'property', None):
                validated_data['property'] = self.context['request'].user.property

        prop = validated_data.get('property')
        settings_obj = Settings.get_settings(prop=prop)
        prefix = settings_obj.booking_prefix or "BK-"

        for attempt in range(10):
            validated_data['booking_number'] = generate_unique_booking_number(prop, prefix)
            try:
                with transaction.atomic():
                    instance = super().create(validated_data)
                    instance._excess_advance = excess_advance
                    return instance
            except IntegrityError:
                continue

        instance = super().create(validated_data)
        instance._excess_advance = excess_advance
        return instance

    def update(self, instance, validated_data):
        excess_advance = validated_data.pop('excess_advance', 0.0)
        validated_data.pop('chargeable_nights', None)
        validated_data.pop('_history_user', None)
        updated_instance = super().update(instance, validated_data)
        updated_instance._excess_advance = excess_advance
        return updated_instance
