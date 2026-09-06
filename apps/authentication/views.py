from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
from django.contrib.auth import get_user_model
from .models import RolePermission, DEFAULT_PERMISSIONS
from .serializers import (
    CustomTokenObtainPairSerializer, UserSerializer, UserCreateUpdateSerializer,
    RolePermissionSerializer
)
from .permissions import IsHotelOwner, IsSuperAdmin

User = get_user_model()

class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

class UserProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)

from apps.settings_app.tenant_views import TenantScopedViewSetMixin
from apps.settings_app.models import Property
from django.db.models import Q
import secrets

class UserViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = User.objects.all().order_by('-date_joined')
    permission_classes = [IsHotelOwner]

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.IsAuthenticated()]
        return [IsHotelOwner()]

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return UserCreateUpdateSerializer
        return UserSerializer

    def get_queryset(self):
        user = getattr(self.request, 'user', None)
        if not user or not user.is_authenticated:
            return User.objects.none()

        if user.is_superuser:
            prop_id = self.request.query_params.get('property')
            if prop_id:
                return User.objects.filter(property_id=prop_id).select_related('property').order_by('-date_joined')
            return User.objects.all().select_related('property').order_by('-date_joined')

        user_prop = getattr(user, 'property', None)
        if not user_prop:
            return User.objects.none()

        root_prop = user_prop.parent_property or user_prop
        prop_ids = list(Property.objects.filter(
            Q(id=root_prop.id) | Q(parent_property=root_prop)
        ).values_list('id', flat=True))

        # Hotel Owner can see staff for their primary property AND any branches
        if user.role in ['HOTEL_OWNER', 'OWNER', 'SUPER_ADMIN']:
            return User.objects.filter(property_id__in=prop_ids).select_related('property').order_by('-date_joined')

        # Manager or other staff sees active users for their hotel and branches
        return User.objects.filter(property_id__in=prop_ids, is_active=True).select_related('property').order_by('-date_joined')

    def perform_create(self, serializer):
        user = self.request.user
        target_property = serializer.validated_data.get('property')

        if user.is_superuser:
            serializer.save()
            return

        user_prop = getattr(user, 'property', None)
        if not user_prop:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("You must be assigned to a property to create staff users.")

        # If property was specified, validate that it belongs to this owner (either primary or their branch)
        if target_property:
            if target_property.id != user_prop.id and getattr(target_property, 'parent_property_id', None) != user_prop.id:
                from rest_framework.exceptions import ValidationError
                raise ValidationError({"property": ["You can only assign staff to your primary hotel or its branches."]})
            serializer.save(property=target_property)
        else:
            serializer.save(property=user_prop)

    @action(detail=True, methods=['post'])
    def reset_password(self, request, pk=None):
        target_user = self.get_object()
        new_password = request.data.get('password')
        if not new_password:
            new_password = f"StaffPass@{secrets.randbelow(8999) + 1000}"

        target_user.set_password(new_password)
        target_user.save()
        return Response({
            'success': True,
            'message': f"Password for {target_user.username} has been reset successfully.",
            'username': target_user.username,
            'new_password': new_password
        })

    @action(detail=True, methods=['patch'])
    def toggle_active(self, request, pk=None):
        target_user = self.get_object()
        if target_user.id == request.user.id:
            return Response({'error': 'You cannot deactivate your own account.'}, status=status.HTTP_400_BAD_REQUEST)
        target_user.is_active = not target_user.is_active
        target_user.save()
        return Response({
            'success': True,
            'message': f"User '{target_user.username}' is now {'ACTIVE' if target_user.is_active else 'DEACTIVATED'}.",
            'is_active': target_user.is_active
        })

class RolePermissionViewSet(viewsets.ViewSet):
    permission_classes = [IsHotelOwner]

    def _get_target_property(self, request):
        user = request.user
        prop = getattr(user, 'property', None)
        if prop and hasattr(prop, 'get_root_property'):
            return prop.get_root_property() or prop
        elif prop and getattr(prop, 'parent_property', None):
            return prop.parent_property
        return prop

    def list(self, request):
        """
        Returns full dynamic permission matrix for MANAGER and RECEPTIONIST roles.
        """
        target_prop = self._get_target_property(request)
        roles = ['MANAGER', 'RECEPTIONIST']
        matrix = {}
        for r in roles:
            matrix[r] = RolePermission.get_permissions_for_role(r, target_prop)
        return Response({
            'success': True,
            'matrix': matrix,
            'default_template': DEFAULT_PERMISSIONS
        })

    def create(self, request):
        """
        Update permissions for a specific role.
        Payload: { role: 'RECEPTIONIST', permissions: { ... } }
        """
        role = request.data.get('role')
        new_perms = request.data.get('permissions', {})
        if role not in ['MANAGER', 'RECEPTIONIST']:
            return Response({'error': 'Role must be MANAGER or RECEPTIONIST'}, status=status.HTTP_400_BAD_REQUEST)

        target_prop = self._get_target_property(request)
        obj, _ = RolePermission.objects.get_or_create(role=role, property=target_prop)
        obj.permissions = new_perms
        obj.save()

        return Response({
            'success': True,
            'message': f'Permissions for {role} updated successfully.',
            'data': RolePermission.get_permissions_for_role(role, target_prop)
        })

    @action(detail=False, methods=['post'])
    def reset_defaults(self, request):
        """
        Reset role permissions back to factory defaults.
        """
        role = request.data.get('role')
        target_prop = self._get_target_property(request)
        qs = RolePermission.objects.filter(property=target_prop) if target_prop else RolePermission.objects.filter(property__isnull=True)
        if role and role in DEFAULT_PERMISSIONS:
            qs.filter(role=role).delete()
        else:
            qs.delete()

        return Response({
            'success': True,
            'message': f'Role permissions for {role or "all roles"} reset to factory defaults.'
        })

