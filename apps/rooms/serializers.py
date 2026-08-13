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
