from rest_framework import serializers
from .models import HotelCatalogueConfig, RoomTypePhoto, CatalogueInquiry, HotelGalleryPhoto
from apps.rooms.models import RoomType
from apps.settings_app.models import Property

class HotelGalleryPhotoSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = HotelGalleryPhoto
        fields = ['id', 'property', 'image', 'image_url', 'caption', 'display_order', 'created_at']
        read_only_fields = ['property']

    def get_image_url(self, obj):
        request = self.context.get('request')
        if obj.image:
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None

class RoomTypePhotoSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoomTypePhoto
        fields = ['id', 'room_type', 'image', 'caption', 'display_order', 'is_primary', 'created_at']

class CatalogueRoomTypeSerializer(serializers.ModelSerializer):
    photos = RoomTypePhotoSerializer(many=True, read_only=True)
    primary_photo = serializers.SerializerMethodField()

    class Meta:
        model = RoomType
        fields = [
            'id', 'name', 'description', 'base_price',
            'max_adults', 'max_children', 'amenities',
            'show_in_catalogue', 'catalogue_badge', 'is_active',
            'photos', 'primary_photo'
        ]

    def get_primary_photo(self, obj):
        request = self.context.get('request')
        primary = obj.photos.filter(is_primary=True).first() or obj.photos.first()
        if primary and primary.image:
            if request:
                return request.build_absolute_uri(primary.image.url)
            return primary.image.url
        return None

class HotelCatalogueConfigSerializer(serializers.ModelSerializer):
    property = serializers.PrimaryKeyRelatedField(read_only=True)
    property_name = serializers.CharField(source='property.name', read_only=True)
    property_code = serializers.CharField(source='property.code', read_only=True)
    hero_banner_url = serializers.SerializerMethodField()

    class Meta:
        model = HotelCatalogueConfig
        fields = '__all__'

    def to_internal_value(self, data):
        if hasattr(data, 'copy'):
            data = data.copy()
        else:
            data = dict(data)

        from django.http import QueryDict
        import json

        list_fields = [
            'facilities_json', 'faqs_json', 'reviews_json',
            'nearby_places_json', 'stats_json', 'direct_privileges_json'
        ]
        dict_fields = ['rating_summary_json']

        is_querydict = isinstance(data, QueryDict)

        for jf in list_fields:
            if jf in data:
                val = data[jf]
                if val == '' or val is None:
                    data[jf] = '[]' if is_querydict else []
                elif isinstance(val, list):
                    if is_querydict:
                        data[jf] = json.dumps(val)
                elif isinstance(val, str):
                    try:
                        parsed = json.loads(val)
                        if not isinstance(parsed, list):
                            data[jf] = '[]' if is_querydict else []
                    except Exception:
                        data[jf] = '[]' if is_querydict else []

        for jf in dict_fields:
            if jf in data:
                val = data[jf]
                if val == '' or val is None:
                    data[jf] = '{}' if is_querydict else {}
                elif isinstance(val, dict):
                    if is_querydict:
                        data[jf] = json.dumps(val)
                elif isinstance(val, str):
                    try:
                        parsed = json.loads(val)
                        if not isinstance(parsed, dict):
                            data[jf] = '{}' if is_querydict else {}
                    except Exception:
                        data[jf] = '{}' if is_querydict else {}

        # Robustly parse boolean strings from FormData
        for bool_field in ['is_published', 'show_reviews']:
            if bool_field in data:
                val = str(data[bool_field]).lower().strip()
                data[bool_field] = val in ['true', '1', 'yes']

        # Handle empty URLs & Emails cleanly
        for url_field in ['google_maps_directions_url', 'instagram_url', 'facebook_url', 'website_url', 'contact_email']:
            if url_field in data and not data[url_field]:
                data[url_field] = ''

        return super().to_internal_value(data)

    def get_hero_banner_url(self, obj):
        request = self.context.get('request')
        if obj.hero_banner:
            if request:
                return request.build_absolute_uri(obj.hero_banner.url)
            return obj.hero_banner.url
        return None

class CatalogueInquirySerializer(serializers.ModelSerializer):
    requested_room_type_name = serializers.CharField(source='requested_room_type.name', read_only=True)

    class Meta:
        model = CatalogueInquiry
        fields = '__all__'

class PublicBranchOptionSerializer(serializers.ModelSerializer):
    min_price = serializers.SerializerMethodField()
    room_count = serializers.SerializerMethodField()
    banner_url = serializers.SerializerMethodField()

    class Meta:
        model = Property
        fields = ['id', 'name', 'code', 'city', 'address', 'owner_phone', 'min_price', 'room_count', 'banner_url']

    def get_min_price(self, obj):
        cheapest = RoomType.objects.filter(property=obj, is_active=True, show_in_catalogue=True).order_by('base_price').first()
        return cheapest.base_price if cheapest else None

    def get_room_count(self, obj):
        return RoomType.objects.filter(property=obj, is_active=True, show_in_catalogue=True).count()

    def get_banner_url(self, obj):
        request = self.context.get('request')
        cfg = getattr(obj, 'catalogue_config', None)
        if cfg and cfg.hero_banner:
            if request:
                return request.build_absolute_uri(cfg.hero_banner.url)
            return cfg.hero_banner.url
        return None
