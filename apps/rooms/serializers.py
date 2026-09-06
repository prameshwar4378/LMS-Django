from rest_framework import serializers
from .models import RoomType, Room

class RoomTypeSerializer(serializers.ModelSerializer):
    room_count = serializers.IntegerField(source='rooms.count', read_only=True)

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
        user = getattr(request, 'user', None) if request else None
        user_prop = getattr(user, 'property', None) if user and not user.is_superuser else None

        prop = attrs.get('property') or user_prop
        room_number = attrs.get('room_number')

        if room_number:
            room_number = str(room_number).strip()
            attrs['room_number'] = room_number
            qs = Room.objects.all()
            if prop:
                qs = qs.filter(property=prop)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.filter(room_number__iexact=room_number).exists():
                raise serializers.ValidationError({
                    'room_number': [f"Room '{room_number}' already exists in this property. Please enter a different room number."]
                })

        return attrs

