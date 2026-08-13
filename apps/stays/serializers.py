from rest_framework import serializers
import datetime
from .models import Stay, StayGuest
from apps.customers.serializers import CustomerSerializer
from apps.rooms.serializers import RoomSerializer
from apps.billing.serializers import ExtraChargeSerializer, PaymentSerializer
from apps.billing.services import calculate_stay_bill

class StayGuestSerializer(serializers.ModelSerializer):
    class Meta:
        model = StayGuest
        fields = '__all__'

class StaySerializer(serializers.ModelSerializer):
    primary_customer_detail = CustomerSerializer(source='primary_customer', read_only=True)
    room_detail = RoomSerializer(source='room', read_only=True)
    guests = StayGuestSerializer(many=True, read_only=True)
    extra_charges = ExtraChargeSerializer(many=True, read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)
    bill_summary = serializers.SerializerMethodField(read_only=True)
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)

    class Meta:
        model = Stay
        fields = '__all__'
        read_only_fields = ('stay_number', 'created_by', 'created_at', 'updated_at')

    def validate(self, attrs):
        check_in_d = attrs.get('check_in_date') or (self.instance.check_in_date if self.instance else None)
        check_in_t = attrs.get('check_in_time') or (self.instance.check_in_time if self.instance else datetime.time(12, 0))
        
        checkout_d = attrs.get('expected_checkout_date') or (self.instance.expected_checkout_date if self.instance else None)
        checkout_t = attrs.get('expected_checkout_time') or (self.instance.expected_checkout_time if self.instance else datetime.time(11, 0))

        if check_in_d and checkout_d:
            dt_in = datetime.datetime.combine(check_in_d, check_in_t)
            dt_out = datetime.datetime.combine(checkout_d, checkout_t)

            if dt_out <= dt_in:
                raise serializers.ValidationError({'expected_checkout_date': 'Check-out datetime must be strictly after check-in datetime.'})

        return attrs

    def get_bill_summary(self, obj):
        return calculate_stay_bill(obj)
