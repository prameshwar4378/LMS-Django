from rest_framework import viewsets, status, exceptions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.db.models import Q
from django.shortcuts import get_object_or_404

from .models import HotelCatalogueConfig, RoomTypePhoto, CatalogueInquiry, HotelGalleryPhoto
from .serializers import (
    HotelCatalogueConfigSerializer,
    RoomTypePhotoSerializer,
    CatalogueRoomTypeSerializer,
    CatalogueInquirySerializer,
    PublicBranchOptionSerializer,
    HotelGalleryPhotoSerializer
)
from apps.settings_app.models import Property
from apps.rooms.models import RoomType
from apps.settings_app.tenant_views import TenantScopedViewSetMixin, get_active_property_for_request


class PublicCatalogueView(APIView):
    """
    Public unauthenticated endpoint to load complete hotel & branch catalogue.
    Accessed by guests via QR codes or shared links.
    """
    permission_classes = [AllowAny]

    def get(self, request, property_code):
        # 1. Resolve property by code (case-insensitive)
        prop = Property.objects.filter(code__iexact=property_code, is_active=True).first()
        if not prop:
            return Response(
                {"detail": f"Hotel property with code '{property_code}' not found or inactive."},
                status=status.HTTP_404_NOT_FOUND
            )

        # 2. Check if a specific branch was requested via ?branch=code
        branch_code = request.query_params.get('branch')
        if branch_code and branch_code.lower() != prop.code.lower():
            branch_prop = Property.objects.filter(code__iexact=branch_code, is_active=True).first()
            if branch_prop:
                root_curr = prop.get_root_property() if hasattr(prop, 'get_root_property') else prop
                root_branch = branch_prop.get_root_property() if hasattr(branch_prop, 'get_root_property') else branch_prop
                if root_curr and root_branch and root_curr.id == root_branch.id:
                    prop = branch_prop

        # 3. Resolve or initialize catalogue config for this property/branch
        config, _ = HotelCatalogueConfig.objects.get_or_create(
            property=prop,
            defaults={
                'hero_headline': prop.name,
                'hero_tagline': f"Welcome to {prop.name}, {prop.city or 'your premium stay'}",
                'contact_phone': prop.owner_phone or "",
                'contact_email': prop.owner_email or "",
                'address_override': prop.address or "",
                'city_override': prop.city or "",
            }
        )

        if not config.is_published:
            return Response(
                {
                    "detail": f"{prop.name} digital catalogue is currently unpublished or undergoing maintenance.",
                    "is_published": False,
                    "hotel_name": prop.name
                },
                status=status.HTTP_403_FORBIDDEN
            )

        # 4. Multi-branch intelligence: find sibling branches under the root brand
        root_prop = prop.get_root_property() if hasattr(prop, 'get_root_property') else prop
        sibling_branches = Property.objects.filter(
            Q(id=root_prop.id) | Q(parent_property=root_prop),
            is_active=True
        ).distinct().order_by('name')

        is_multi_branch = sibling_branches.count() > 1
        branches_data = PublicBranchOptionSerializer(sibling_branches, many=True, context={'request': request}).data if is_multi_branch else []

        # 5. Room types available at this property/branch
        room_types = RoomType.objects.filter(
            property=prop,
            is_active=True,
            show_in_catalogue=True
        ).prefetch_related('photos').order_by('base_price')

        room_types_data = CatalogueRoomTypeSerializer(
            room_types,
            many=True,
            context={'request': request}
        ).data

        # 6. Logo resolution
        logo_url = None
        if hasattr(prop, 'logo') and prop.logo:
            logo_url = request.build_absolute_uri(prop.logo.url)
        elif root_prop and hasattr(root_prop, 'logo') and root_prop.logo:
            logo_url = request.build_absolute_uri(root_prop.logo.url)

        # 7. Banner resolution
        hero_banner_url = None
        if config.hero_banner:
            hero_banner_url = request.build_absolute_uri(config.hero_banner.url)

        config_data = HotelCatalogueConfigSerializer(config, context={'request': request}).data
        config_data['hero_banner_url'] = hero_banner_url

        # 8. Hotel gallery photos
        gallery_photos_qs = HotelGalleryPhoto.objects.filter(property=prop).order_by('display_order', 'id')
        gallery_photos_data = HotelGalleryPhotoSerializer(gallery_photos_qs, many=True, context={'request': request}).data

        return Response({
            "hotel": {
                "id": prop.id,
                "name": prop.name,
                "code": prop.code,
                "city": config.city_override or prop.city or "",
                "state": prop.state or "",
                "address": config.address_override or prop.address or "",
                "pincode": prop.pincode or "",
                "phone": config.contact_phone or prop.owner_phone or "",
                "whatsapp": config.whatsapp_number or config.contact_phone or prop.owner_phone or "",
                "email": config.contact_email or prop.owner_email or "",
                "logo_url": logo_url,
                "is_root": prop.parent_property is None,
                "parent_name": prop.parent_property.name if prop.parent_property else None,
            },
            "is_multi_branch": is_multi_branch,
            "branches": branches_data,
            "config": config_data,
            "room_types": room_types_data,
            "gallery_photos": gallery_photos_data,
        })


class PublicInquiryCreateView(APIView):
    """
    Public unauthenticated endpoint allowing guests to submit booking inquiries from the catalogue.
    """
    permission_classes = [AllowAny]

    def post(self, request, property_code):
        prop = Property.objects.filter(code__iexact=property_code, is_active=True).first()
        if not prop:
            return Response({"detail": "Property not found"}, status=status.HTTP_404_NOT_FOUND)

        data = request.data.copy()
        room_type_id = data.get('requested_room_type')
        room_type = None
        if room_type_id:
            room_type = RoomType.objects.filter(id=room_type_id, property=prop).first()

        guest_name = data.get('guest_name', '').strip()
        guest_mobile = data.get('guest_mobile', '').strip()

        if not guest_name or not guest_mobile:
            return Response(
                {"detail": "Guest Name and Mobile Number are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        inquiry = CatalogueInquiry.objects.create(
            property=prop,
            guest_name=guest_name,
            guest_mobile=guest_mobile,
            guest_email=data.get('guest_email', '').strip(),
            requested_room_type=room_type,
            check_in_date=data.get('check_in_date') or None,
            check_out_date=data.get('check_out_date') or None,
            adults=int(data.get('adults', 2) or 2),
            children=int(data.get('children', 0) or 0),
            message=data.get('message', '').strip(),
            status=CatalogueInquiry.Status.NEW
        )

        serializer = CatalogueInquirySerializer(inquiry)
        return Response({
            "message": "Inquiry submitted successfully! Hotel desk has been notified.",
            "inquiry": serializer.data
        }, status=status.HTTP_201_CREATED)


class HotelCatalogueConfigViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """
    Authenticated management ViewSet for Hotel Owners and Managers.
    """
    serializer_class = HotelCatalogueConfigSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    queryset = HotelCatalogueConfig.objects.all()

    def get_queryset(self):
        prop = self.get_property_for_request()
        if not prop:
            return HotelCatalogueConfig.objects.none()
        return HotelCatalogueConfig.objects.filter(property=prop)

    @action(detail=False, methods=['get', 'post', 'patch', 'put'])
    def current(self, request):
        prop = self.get_property_for_request()
        if not prop:
            # Fallback to user's direct property or first active property
            user = getattr(request, 'user', None)
            if user and getattr(user, 'property', None):
                prop = user.property
            else:
                prop = Property.objects.filter(is_active=True).first()

        if not prop:
            return Response({"detail": "Active property not selected"}, status=status.HTTP_400_BAD_REQUEST)

        config, created = HotelCatalogueConfig.objects.get_or_create(
            property=prop,
            defaults={
                'hero_headline': prop.name,
                'hero_tagline': f"Welcome to {prop.name}",
                'contact_phone': prop.owner_phone or "",
                'contact_email': prop.owner_email or "",
                'address_override': prop.address or "",
                'city_override': prop.city or "",
            }
        )

        if request.method in ['POST', 'PATCH', 'PUT']:
            data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
            
            # Handle facilities_json string parsing if sent via FormData
            if 'facilities_json' in data and isinstance(data['facilities_json'], str):
                import json
                try:
                    data['facilities_json'] = json.loads(data['facilities_json'])
                except Exception:
                    pass

            # Handle boolean strings from FormData
            if 'is_published' in data:
                val = str(data['is_published']).lower().strip()
                data['is_published'] = val in ['true', '1', 'yes']

            serializer = self.get_serializer(config, data=data, partial=True)
            serializer.is_valid(raise_exception=True)
            config = serializer.save()

        serializer = self.get_serializer(config)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def copy_brand_defaults(self, request):
        """
        In multi-branch mode: copies global branding, policies, and facilities
        from the root hotel property into this branch.
        """
        prop = self.get_property_for_request()
        if not prop:
            return Response({"detail": "Property not found"}, status=status.HTTP_400_BAD_REQUEST)

        root_prop = prop.get_root_property() if hasattr(prop, 'get_root_property') else prop
        if not root_prop or root_prop.id == prop.id:
            return Response(
                {"detail": "This is already the primary hotel. Nothing to copy from."},
                status=status.HTTP_400_BAD_REQUEST
            )

        root_config = HotelCatalogueConfig.objects.filter(property=root_prop).first()
        if not root_config:
            return Response({"detail": "Primary hotel catalogue config not found."}, status=status.HTTP_404_NOT_FOUND)

        branch_config, _ = HotelCatalogueConfig.objects.get_or_create(property=prop)
        branch_config.accent_theme = root_config.accent_theme
        branch_config.facilities_json = root_config.facilities_json
        branch_config.about_title = root_config.about_title
        branch_config.stats_json = root_config.stats_json
        branch_config.direct_privileges_json = root_config.direct_privileges_json
        branch_config.faqs_json = root_config.faqs_json
        branch_config.show_reviews = root_config.show_reviews
        branch_config.rating_summary_json = root_config.rating_summary_json
        branch_config.reviews_json = root_config.reviews_json
        branch_config.check_in_time = root_config.check_in_time
        branch_config.check_out_time = root_config.check_out_time
        branch_config.cancellation_policy = root_config.cancellation_policy
        branch_config.house_rules = root_config.house_rules
        branch_config.instagram_url = root_config.instagram_url
        branch_config.facebook_url = root_config.facebook_url
        branch_config.website_url = root_config.website_url
        branch_config.save()

        return Response({
            "message": "Brand policies, theme, and facilities copied from primary hotel successfully!",
            "config": self.get_serializer(branch_config).data
        })


class HotelGalleryPhotoViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """
    ViewSet for uploading, reordering, and deleting general hotel gallery photos.
    """
    serializer_class = HotelGalleryPhotoSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        prop = self.get_property_for_request()
        if not prop:
            return HotelGalleryPhoto.objects.none()
        return HotelGalleryPhoto.objects.filter(property=prop).order_by('display_order', 'id')

    def perform_create(self, serializer):
        prop = self.get_property_for_request()
        if not prop:
            raise exceptions.PermissionDenied("Active property is required.")
        serializer.save(property=prop)



class RoomTypePhotoViewSet(viewsets.ModelViewSet):
    """
    ViewSet for uploading, reordering, and deleting photos attached to RoomTypes.
    """
    serializer_class = RoomTypePhotoSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        prop = get_active_property_for_request(self.request)
        room_type_id = self.request.query_params.get('room_type')
        qs = RoomTypePhoto.objects.all()
        if prop:
            qs = qs.filter(room_type__property=prop)
        if room_type_id:
            qs = qs.filter(room_type_id=room_type_id)
        return qs.order_by('display_order', '-is_primary', 'id')

    def perform_create(self, serializer):
        prop = get_active_property_for_request(self.request)
        room_type = serializer.validated_data.get('room_type')
        if prop and room_type and room_type.property_id != prop.id:
            raise exceptions.PermissionDenied("You cannot add photos to a room type from another property.")
        serializer.save()

    @action(detail=True, methods=['post'])
    def set_primary(self, request, pk=None):
        photo = self.get_object()
        # Reset any other primary photo for this room type
        RoomTypePhoto.objects.filter(room_type=photo.room_type, is_primary=True).update(is_primary=False)
        photo.is_primary = True
        photo.save()
        return Response({"message": "Photo set as primary thumbnail successfully!"})


class CatalogueInquiryViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """
    Authenticated ViewSet for managing incoming leads from the digital catalogue.
    """
    serializer_class = CatalogueInquirySerializer

    def get_queryset(self):
        prop = self.get_property_for_request()
        if not prop:
            return CatalogueInquiry.objects.none()
        qs = CatalogueInquiry.objects.filter(property=prop)
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs.order_by('-created_at')

    @action(detail=True, methods=['post'])
    def update_status(self, request, pk=None):
        inquiry = self.get_object()
        new_status = request.data.get('status')
        if new_status in CatalogueInquiry.Status.values:
            inquiry.status = new_status
            if 'notes' in request.data:
                inquiry.notes = request.data.get('notes')
            inquiry.save()
            return Response(self.get_serializer(inquiry).data)
        return Response({"detail": "Invalid status"}, status=status.HTTP_400_BAD_REQUEST)
