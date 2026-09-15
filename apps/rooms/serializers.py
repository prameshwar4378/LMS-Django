from rest_framework import serializers
from .models import RoomType, Room, RoomDeletionRequest

class RoomTypeSerializer(serializers.ModelSerializer):
    room_count = serializers.SerializerMethodField()

    def get_room_count(self, obj):
        return getattr(obj, 'room_count', None) if hasattr(obj, 'room_count') else obj.rooms.count()

    class Meta:
        model = RoomType
        fields = '__all__'

class RoomSerializer(serializers.ModelSerializer):
    room_type_name = serializers.CharField(source='room_type.name', read_only=True)
    base_price = serializers.DecimalField(source='room_type.base_price', max_digits=10, decimal_places=2, read_only=True)
    max_adults = serializers.IntegerField(source='room_type.max_adults', read_only=True)
    max_children = serializers.IntegerField(source='room_type.max_children', read_only=True)

    class Meta:
        model = Room
        fields = '__all__'

    def validate(self, attrs):
        request = self.context.get('request')
        view = self.context.get('view')
        user = getattr(request, 'user', None) if request else None

        # 1. First priority: explicitly passed property in attrs
        prop = attrs.get('property')

        # 2. Second priority: active property resolved from request / view context
        if not prop and view and hasattr(view, 'get_property_for_request'):
            prop = view.get_property_for_request()
        elif not prop and request:
            from apps.settings_app.tenant_views import get_active_property_for_request
            prop = get_active_property_for_request(request)

        # 3. Third priority: existing instance property if updating
        if not prop and self.instance:
            prop = getattr(self.instance, 'property', None)

        # 4. Fourth priority: user's assigned property (if not superuser)
        if not prop and user and not user.is_superuser:
            prop = getattr(user, 'property', None)

        room_number = attrs.get('room_number')
        if room_number:
            room_number = str(room_number).strip()
            attrs['room_number'] = room_number

            # STRICTLY validate room_number uniqueness WITHIN THE CURRENT BRANCH / PROPERTY ONLY
            if prop:
                qs = Room.objects.filter(property=prop)
                if self.instance:
                    qs = qs.exclude(pk=self.instance.pk)
                if qs.filter(room_number__iexact=room_number).exists():
                    branch_label = f"branch '{prop.name}'" if getattr(prop, 'parent_property', None) else f"property '{prop.name}'"
                    raise serializers.ValidationError({
                        'room_number': [f"Room '{room_number}' already exists in {branch_label}. Please enter a unique room number for this branch."]
                    })
            elif self.instance and self.instance.property:
                qs = Room.objects.filter(property=self.instance.property).exclude(pk=self.instance.pk)
                if qs.filter(room_number__iexact=room_number).exists():
                    raise serializers.ValidationError({
                        'room_number': [f"Room '{room_number}' already exists in this branch. Please enter a different room number."]
                    })

        return attrs


class RoomDeletionRequestSerializer(serializers.ModelSerializer):
    requested_by_name = serializers.SerializerMethodField()
    requested_by_role = serializers.CharField(source='requested_by.role', read_only=True)
    reviewed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = RoomDeletionRequest
        fields = [
            'id', 'property', 'room', 'room_number', 'room_type_name', 'floor',
            'requested_by', 'requested_by_name', 'requested_by_role', 'reason',
            'activity_summary', 'status', 'reviewed_by', 'reviewed_by_name',
            'review_notes', 'reviewed_at', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'status', 'reviewed_by', 'reviewed_at', 'created_at', 'updated_at']

    def get_requested_by_name(self, obj):
        if not obj.requested_by:
            return 'Staff'
        return obj.requested_by.get_full_name() or obj.requested_by.username

    def get_reviewed_by_name(self, obj):
        if not obj.reviewed_by:
            return None
        return obj.reviewed_by.get_full_name() or obj.reviewed_by.username


