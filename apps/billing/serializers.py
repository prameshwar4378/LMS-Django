from rest_framework import serializers
from .models import ChargeType, ExtraCharge, Payment, Invoice
from apps.settings_app.models import Settings
import datetime

class ChargeTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChargeType
        fields = '__all__'

    def validate_name(self, value):
        name = value.strip()
        if not name:
            raise serializers.ValidationError("Category Name is required.")
        qs = ChargeType.objects.filter(name__iexact=name)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Category already exists.")
        return name

class ExtraChargeSerializer(serializers.ModelSerializer):
    charge_type_name = serializers.SerializerMethodField(read_only=True)
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    charge_date = serializers.DateTimeField(required=False)

    class Meta:
        model = ExtraCharge
        fields = '__all__'
        read_only_fields = ('amount', 'created_by', 'created_at')

    def get_charge_type_name(self, obj):
        if obj.charge_type:
            return obj.charge_type.name
        return obj.description or 'Custom Charge'

    def create(self, validated_data):
        if 'request' in self.context and self.context['request'].user.is_authenticated:
            validated_data['created_by'] = self.context['request'].user
        return super().create(validated_data)

class PaymentSerializer(serializers.ModelSerializer):
    received_by_name = serializers.CharField(source='received_by.get_full_name', read_only=True)
    stay_number = serializers.CharField(source='stay.stay_number', read_only=True)
    room_number = serializers.CharField(source='stay.room.room_number', read_only=True)
    customer_name = serializers.CharField(source='stay.primary_customer.full_name', read_only=True)
    payment_date = serializers.DateTimeField(required=False)

    class Meta:
        model = Payment
        fields = '__all__'
        read_only_fields = ('payment_number', 'received_by', 'created_at')

    def create(self, validated_data):
        import uuid
        pay_prefix = "PAY-"
        today_str = datetime.date.today().strftime('%Y%m%d')
        for attempt in range(50):
            pay_count = Payment.objects.filter(payment_number__startswith=f"{pay_prefix}{today_str}").count() + 1 + attempt
            p_num = f"{pay_prefix}{today_str}-{pay_count:03d}"
            if not Payment.objects.filter(payment_number=p_num).exists():
                validated_data['payment_number'] = p_num
                break
        else:
            validated_data['payment_number'] = f"{pay_prefix}{today_str}-{uuid.uuid4().hex[:4].upper()}"

        if 'request' in self.context and self.context['request'].user.is_authenticated:
            validated_data['received_by'] = self.context['request'].user
        return super().create(validated_data)

class InvoiceSerializer(serializers.ModelSerializer):
    stay_number = serializers.CharField(source='stay.stay_number', read_only=True)
    customer_name = serializers.CharField(source='stay.primary_customer.full_name', read_only=True)
    room_number = serializers.CharField(source='stay.room.room_number', read_only=True)

    class Meta:
        model = Invoice
        fields = '__all__'
