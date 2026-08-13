from rest_framework import serializers
from .models import Customer, CustomerDocument

class CustomerDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerDocument
        fields = '__all__'

class CustomerSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    stay_count = serializers.IntegerField(source='stays.count', read_only=True)
    documents = CustomerDocumentSerializer(many=True, read_only=True)

    class Meta:
        model = Customer
        fields = '__all__'

class CustomerHistorySerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    stays = serializers.SerializerMethodField(read_only=True)
    documents = CustomerDocumentSerializer(many=True, read_only=True)

    class Meta:
        model = Customer
        fields = '__all__'

    def get_stays(self, obj):
        from apps.billing.services import calculate_stay_bill
        result = []
        for stay in obj.stays.all().order_by('-created_at'):
            bill = calculate_stay_bill(stay)
            result.append({
                'id': stay.id,
                'stay_number': stay.stay_number,
                'room_number': stay.room.room_number,
                'check_in_date': stay.check_in_date,
                'checkout_date': stay.actual_checkout_date or stay.expected_checkout_date,
                'status': stay.status,
                'grand_total': bill['grand_total'],
                'total_paid': bill['total_paid'],
                'balance': bill['balance'],
            })
        return result
