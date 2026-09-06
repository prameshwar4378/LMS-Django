from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Settings, Property
from .serializers import SettingsSerializer
from apps.authentication.permissions import IsSuperAdmin

class SettingsViewSet(viewsets.ModelViewSet):
    serializer_class = SettingsSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_property_for_request(self):
        user = getattr(self.request, 'user', None)
        if not user or not user.is_authenticated:
            return None
        return getattr(user, 'property', None)

    def get_queryset(self):
        user = getattr(self.request, 'user', None)
        if not user or not user.is_authenticated:
            return Settings.objects.none()
        if user.is_superuser:
            prop_id = self.request.query_params.get('property')
            if prop_id:
                return Settings.objects.filter(property_id=prop_id)
            return Settings.objects.all()
        prop = self.get_property_for_request()
        if not prop:
            return Settings.objects.none()
        return Settings.objects.filter(property=prop)

    def get_object(self):
        prop = self.get_property_for_request()
        return Settings.get_settings(prop=prop)

    def list(self, request, *args, **kwargs):
        prop = self.get_property_for_request()
        settings_obj = Settings.get_settings(prop=prop)
        serializer = self.get_serializer(settings_obj)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        prop = self.get_property_for_request()
        settings_obj = Settings.get_settings(prop=prop)
        serializer = self.get_serializer(settings_obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        saved_obj = serializer.save()
        if prop:
            # Sync core fields back to property model
            if 'lodge_name' in request.data:
                prop.name = saved_obj.lodge_name
            if 'address' in request.data:
                prop.address = saved_obj.address
            if 'phone' in request.data:
                prop.owner_phone = saved_obj.phone
            if 'email' in request.data:
                prop.owner_email = saved_obj.email
            if 'gst_number' in request.data:
                prop.gstin = saved_obj.gst_number
            prop.save()
        return Response(serializer.data)

    def update(self, request, *args, **kwargs):
        return self.create(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        return self.create(request, *args, **kwargs)

    @action(detail=False, methods=['get'])
    def branches(self, request):
        """
        Allows Hotel Owner to retrieve their active branches for user assignments and viewing.
        Note: Hotel Owner CANNOT create or delete branches (read-only here).
        """
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return Response([], status=status.HTTP_200_OK)

        prop = getattr(user, 'property', None)
        if user.is_superuser:
            prop_id = request.query_params.get('property')
            if prop_id:
                prop = Property.objects.filter(id=prop_id).first()
            else:
                prop = Property.objects.first()

        parent = prop.parent_property if (prop and prop.parent_property) else prop
        if not parent:
            return Response([], status=status.HTTP_200_OK)

        branches = Property.objects.filter(parent_property=parent, is_active=True).order_by('name')

        data = [
            {
                'id': parent.id,
                'name': parent.name,
                'code': parent.code,
                'property_code': parent.code,
                'city': parent.city,
                'state': parent.state,
                'address': parent.address,
                'total_rooms': parent.total_rooms,
                'is_primary': True,
                'is_branch': False,
                'is_active': parent.is_active,
                'operation_mode': parent.get_operation_mode(),
                'is_shift_wise': parent.is_shift_wise,
                'created_at': parent.created_at.strftime('%Y-%m-%d') if parent.created_at else None
            }
        ]
        for b in branches:
            data.append({
                'id': b.id,
                'name': b.name,
                'code': b.code,
                'property_code': b.code,
                'city': b.city,
                'state': b.state,
                'address': b.address,
                'total_rooms': b.total_rooms,
                'is_primary': False,
                'is_branch': True,
                'is_active': b.is_active,
                'operation_mode': b.get_operation_mode(),
                'is_shift_wise': b.is_shift_wise,
                'created_at': b.created_at.strftime('%Y-%m-%d') if b.created_at else None
            })
        return Response(data, status=status.HTTP_200_OK)

