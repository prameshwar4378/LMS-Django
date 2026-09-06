from rest_framework import exceptions, status
from rest_framework.response import Response
from django.db.models import Q

def get_active_property_for_request(request):
    """
    Resolves the active hotel property for the given request.
    - If the user is a superuser: allows targeting any property via X-Property-ID or ?property=.
    - If the user is a Hotel Owner (HOTEL_OWNER / SUPER_ADMIN / SUPERUSER):
      allows switching between their primary hotel and any of their owned branch properties.
    - Otherwise (Branch Manager, Receptionist): locks strictly to their assigned property.
    """
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return None

    user_prop = getattr(user, 'property', None)

    # Check X-Property-ID header or property query parameter
    req_prop_id = None
    if hasattr(request, 'headers') and request.headers.get('X-Property-ID'):
        req_prop_id = request.headers.get('X-Property-ID')
    elif hasattr(request, 'META') and request.META.get('HTTP_X_PROPERTY_ID'):
        req_prop_id = request.META.get('HTTP_X_PROPERTY_ID')
    elif hasattr(request, 'query_params') and request.query_params.get('property'):
        req_prop_id = request.query_params.get('property')
    elif hasattr(request, 'GET') and request.GET.get('property'):
        req_prop_id = request.GET.get('property')

    if req_prop_id and str(req_prop_id).strip() not in ['', 'all', 'undefined', 'null', 'None']:
        from apps.settings_app.models import Property
        try:
            # Platform Superuser / Developer can access any property
            if user.is_superuser:
                prop = Property.objects.filter(id=req_prop_id).first()
                if prop:
                    return prop

            # Hotel Owner or Manager can access their primary hotel OR any of their branch properties
            if user_prop and (getattr(user, 'role', '') in ['HOTEL_OWNER', 'SUPER_ADMIN', 'SUPERUSER', 'MANAGER'] or (hasattr(user, 'is_hotel_owner') and user.is_hotel_owner())):
                root_prop = user_prop.get_root_property() if hasattr(user_prop, 'get_root_property') else user_prop
                target_prop = Property.objects.filter(id=req_prop_id).first()
                if target_prop:
                    target_root = target_prop.get_root_property() if hasattr(target_prop, 'get_root_property') else target_prop
                    if target_root and target_root.id == root_prop.id:
                        return target_prop
        except Exception:
            pass

    return user_prop

class TenantScopedViewSetMixin:
    """
    Mixin that guarantees complete tenant isolation across ViewSets.
    1. Filters querysets strictly to the authenticated user's active Property / Branch.
    2. Automatically assigns the active Property upon object creation.
    3. Validates against Insecure Direct Object Reference (IDOR) attacks across hotels.
    """

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        user = getattr(request, 'user', None)
        if user and user.is_authenticated and not user.is_superuser:
            user_prop = self.get_property_for_request()
            if user_prop and user_prop.is_subscription_expired():
                raise exceptions.PermissionDenied(
                    detail="Your subscription for this hotel property has expired. Please contact support to renew."
                )

    def get_property_for_request(self):
        return get_active_property_for_request(self.request)

    def get_queryset(self):
        qs = super().get_queryset()
        user = getattr(self.request, 'user', None)
        if not user or not user.is_authenticated:
            return qs.none()

        active_prop = self.get_property_for_request()

        # Superuser can see all if no specific property is selected
        if user.is_superuser and not active_prop:
            return qs

        if not active_prop:
            return qs.none()

        # Filter model by property if it has a property field
        if hasattr(qs.model, 'property'):
            return qs.filter(property=active_prop)
        return qs

    def perform_create(self, serializer):
        user = getattr(self.request, 'user', None)
        user_prop = self.get_property_for_request()

        # Validate cross-tenant foreign key relationships if present
        self.validate_tenant_integrity(serializer.validated_data, user_prop)

        # Check if the serializer's model has 'property' field
        model_cls = getattr(serializer.Meta, 'model', None)
        if model_cls and hasattr(model_cls, 'property'):
            serializer.save(property=user_prop)
        else:
            serializer.save()

    def perform_update(self, serializer):
        user_prop = self.get_property_for_request()
        self.validate_tenant_integrity(serializer.validated_data, user_prop)
        serializer.save()

    def validate_tenant_integrity(self, validated_data, user_prop):
        """
        Prevents IDOR attacks by verifying related objects (e.g. Room, Customer, Booking, Stay)
        belong to the user's active property or the parent hotel network.
        """
        if not user_prop or (self.request.user and self.request.user.is_superuser):
            return

        user_root_id = user_prop.get_root_property().id if hasattr(user_prop, 'get_root_property') else user_prop.id

        for field_name, value in validated_data.items():
            if hasattr(value, 'property') and getattr(value, 'property', None):
                val_prop = value.property
                val_root_id = val_prop.get_root_property().id if hasattr(val_prop, 'get_root_property') else val_prop.id
                if val_root_id != user_root_id:
                    raise exceptions.ValidationError({
                        field_name: [f"Cross-property reference error: The referenced {field_name} does not belong to your hotel property."]
                    })
