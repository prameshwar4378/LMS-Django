from rest_framework import serializers
from .models import ChargeType, ExtraCharge, Payment, Invoice
from apps.settings_app.models import Settings
import datetime

class ChargeTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChargeType
        fields = '__all__'
        read_only_fields = ('property',)

    def validate(self, attrs):
        name = attrs.get('name') or (self.instance.name if self.instance else None)
        if not name or not str(name).strip():
            raise serializers.ValidationError({'name': ["Category Name is required."]})

        name = str(name).strip()
        attrs['name'] = name

        request = self.context.get('request')
        prop = attrs.get('property')
        if not prop and self.instance:
            prop = self.instance.property
        if not prop and request:
            from apps.settings_app.tenant_views import get_active_property_for_request
            prop = get_active_property_for_request(request)

        qs = ChargeType.objects.all()
        if prop:
            qs = qs.filter(property=prop)
        else:
            qs = qs.filter(property__isnull=True)

        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.filter(name__iexact=name).exists():
            raise serializers.ValidationError({'name': ["Category already exists in this hotel."]})

        return attrs

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
    received_by_name = serializers.SerializerMethodField(read_only=True)
    created_by_name = serializers.SerializerMethodField(read_only=True)
    updated_by_name = serializers.SerializerMethodField(read_only=True)
    stay_number = serializers.SerializerMethodField(read_only=True)
    room_number = serializers.SerializerMethodField(read_only=True)
    customer_name = serializers.SerializerMethodField(read_only=True)
    customer_mobile = serializers.SerializerMethodField(read_only=True)
    customer_id = serializers.SerializerMethodField(read_only=True)
    shift_number = serializers.SerializerMethodField(read_only=True)
    payment_date = serializers.DateTimeField(required=False)

    class Meta:
        model = Payment
        fields = '__all__'
        read_only_fields = ('payment_number', 'received_by', 'created_by', 'updated_by', 'created_at', 'updated_at')

    def get_received_by_name(self, obj):
        if obj.received_by:
            return obj.received_by.get_full_name() or obj.received_by.username
        if obj.created_by:
            return obj.created_by.get_full_name() or obj.created_by.username
        return 'Front Desk'

    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name() or obj.created_by.username
        return None

    def get_updated_by_name(self, obj):
        if obj.updated_by:
            return obj.updated_by.get_full_name() or obj.updated_by.username
        return None

    def get_stay_number(self, obj):
        return obj.stay.stay_number if obj.stay else None

    def get_room_number(self, obj):
        return obj.stay.room.room_number if obj.stay and obj.stay.room else None

    def get_customer_name(self, obj):
        if obj.stay and obj.stay.primary_customer:
            return obj.stay.primary_customer.full_name
        if obj.customer:
            return obj.customer.full_name
        return 'Walk-in Guest'

    def get_customer_mobile(self, obj):
        if obj.stay and obj.stay.primary_customer:
            return obj.stay.primary_customer.mobile
        if obj.customer:
            return obj.customer.mobile
        return None

    def get_customer_id(self, obj):
        if obj.stay and obj.stay.primary_customer:
            return obj.stay.primary_customer.id
        if obj.customer:
            return obj.customer.id
        return None

    def get_shift_number(self, obj):
        return obj.shift.shift_number if obj.shift else None

    def create(self, validated_data):
        from apps.billing.services import generate_unique_payment_number
        from django.db import transaction, IntegrityError
        pay_prefix = "PAY-"

        if 'request' in self.context and self.context['request'].user.is_authenticated:
            user = self.context['request'].user
            if not validated_data.get('received_by'):
                validated_data['received_by'] = user
            if not validated_data.get('created_by'):
                validated_data['created_by'] = user
            validated_data['updated_by'] = user

        for _ in range(10):
            validated_data['payment_number'] = generate_unique_payment_number(pay_prefix)
            try:
                with transaction.atomic():
                    return super().create(validated_data)
            except IntegrityError:
                continue

        return super().create(validated_data)

    def update(self, instance, validated_data):
        if 'request' in self.context and self.context['request'].user.is_authenticated:
            validated_data['updated_by'] = self.context['request'].user
        return super().update(instance, validated_data)

class InvoiceSerializer(serializers.ModelSerializer):
    stay_number = serializers.CharField(source='stay.stay_number', read_only=True)
    customer_name = serializers.CharField(source='stay.primary_customer.full_name', read_only=True)
    room_number = serializers.CharField(source='stay.room.room_number', read_only=True)

    class Meta:
        model = Invoice
        fields = '__all__'
