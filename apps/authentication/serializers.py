from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth import get_user_model
from .models import RolePermission

User = get_user_model()

class RolePermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = RolePermission
        fields = ('id', 'role', 'permissions', 'updated_at')
        read_only_fields = ('id', 'updated_at')

def extract_subscription_info(user):
    if not user or user.is_superuser or not getattr(user, 'property', None):
        return None
    prop = user.property
    sub = prop.get_subscription()
    root_prop = prop.get_root_property() if hasattr(prop, 'get_root_property') else (prop.parent_property or prop)
    is_prop_suspended = prop.is_suspended() if hasattr(prop, 'is_suspended') else not prop.is_active

    if not sub:
        return {
            'has_subscription': False,
            'is_expired': True,
            'is_near_expiry': False,
            'urgency_level': 'EXPIRED',
            'days_remaining': 0,
            'valid_until': None,
            'plan_name': 'No Active Plan',
            'plan_code': 'NONE',
            'property_name': prop.name,
            'property_code': prop.code,
            'total_rooms': prop.total_rooms,
            'max_rooms_allowed': prop.get_max_rooms_allowed(),
            'features': {},
            'billing_cycle': 'ANNUAL',
            'is_paid': False,
            'is_suspended': is_prop_suspended,
            'is_active': not is_prop_suspended,
        }

    valid_until_date = sub.get_valid_until_date()
    return {
        'has_subscription': True,
        'is_expired': sub.is_expired(),
        'is_near_expiry': sub.is_near_expiry(15),
        'urgency_level': sub.urgency_level,
        'days_remaining': sub.days_remaining(),
        'valid_until': valid_until_date.strftime('%Y-%m-%d') if valid_until_date else str(sub.valid_until),
        'plan_name': sub.plan.name if sub.plan else 'Custom Plan',
        'plan_code': sub.plan.code if sub.plan else 'CUSTOM',
        'property_name': prop.name,
        'property_code': prop.code,
        'total_rooms': prop.total_rooms,
        'max_rooms_allowed': prop.get_max_rooms_allowed(),
        'features': sub.plan.features if (sub.plan and hasattr(sub.plan, 'features')) else {},
        'billing_cycle': sub.billing_cycle,
        'is_paid': sub.is_paid,
        'is_branch': bool(prop.parent_property_id),
        'master_property_name': root_prop.name if root_prop else prop.name,
        'master_property_code': root_prop.code if root_prop else prop.code,
        'is_inherited': bool(prop.parent_property_id and sub.lodge_id != prop.id),
        'is_suspended': is_prop_suspended,
        'is_active': not is_prop_suspended,
    }

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['username'] = user.username
        token['role'] = user.role
        token['is_superuser'] = user.is_superuser
        token['name'] = user.get_full_name() or user.username
        token['property_id'] = user.property_id
        token['property_name'] = user.property.name if user.property else None
        token['property_code'] = user.property.code if user.property else None
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        data['user'] = {
            'id': self.user.id,
            'username': self.user.username,
            'email': self.user.email,
            'first_name': self.user.first_name,
            'last_name': self.user.last_name,
            'role': self.user.role,
            'is_superuser': self.user.is_superuser,
            'property': self.user.property_id,
            'property_id': self.user.property_id,
            'property_name': self.user.property.name if self.user.property else None,
            'property_code': self.user.property.code if self.user.property else None,
            'is_branch': bool(self.user.property and getattr(self.user.property, 'parent_property_id', None)),
            'operation_mode': self.user.property.get_operation_mode() if (self.user.property and hasattr(self.user.property, 'get_operation_mode')) else 'SHIFT_WISE',
            'is_shift_wise': self.user.property.is_shift_wise if (self.user.property and hasattr(self.user.property, 'is_shift_wise')) else True,
            'subscription': extract_subscription_info(self.user),
            'permissions': RolePermission.get_permissions_for_role(self.user.role, getattr(self.user, 'property', None))
        }
        return data

class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source='get_full_name', read_only=True)
    permissions = serializers.SerializerMethodField()
    property_name = serializers.CharField(source='property.name', read_only=True)
    property_code = serializers.CharField(source='property.code', read_only=True)
    operation_mode = serializers.SerializerMethodField()
    is_shift_wise = serializers.SerializerMethodField()
    is_branch = serializers.SerializerMethodField()
    subscription = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'first_name', 'last_name', 'full_name', 'role', 'is_superuser', 'is_active', 'property', 'property_name', 'property_code', 'operation_mode', 'is_shift_wise', 'is_branch', 'subscription', 'permissions', 'date_joined')
        read_only_fields = ('id', 'date_joined')

    def get_permissions(self, obj):
        return RolePermission.get_permissions_for_role(obj.role, getattr(obj, 'property', None))

    def get_operation_mode(self, obj):
        if obj.property and hasattr(obj.property, 'get_operation_mode'):
            return obj.property.get_operation_mode()
        return 'SHIFT_WISE'

    def get_is_shift_wise(self, obj):
        if obj.property and hasattr(obj.property, 'is_shift_wise'):
            return obj.property.is_shift_wise
        return True

    def get_is_branch(self, obj):
        return bool(obj.property and getattr(obj.property, 'parent_property_id', None))

    def get_subscription(self, obj):
        return extract_subscription_info(obj)

class UserCreateUpdateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'first_name', 'last_name', 'password', 'role', 'is_active', 'property')

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        user = User(**validated_data)
        if password:
            user.set_password(password)
        else:
            user.set_password('Lodge@123')
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance
