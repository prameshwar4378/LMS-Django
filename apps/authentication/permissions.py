from rest_framework.permissions import BasePermission
from .models import RolePermission

from rest_framework.exceptions import PermissionDenied

def user_has_perm(user, module, action):
    """
    Evaluates whether a user has permission to perform a specific action on a module.
    Hotel Owners, Super Admins, and Superusers have unrestricted permission across all modules.
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser or user.role in ['SUPERUSER', 'HOTEL_OWNER', 'SUPER_ADMIN']:
        return True

    perms = RolePermission.get_permissions_for_role(user.role, getattr(user, 'property', None))
    mod_perms = perms.get(module, {})
    return bool(mod_perms.get(action, False))


def get_perm_limit(user, module, key, fallback=0):
    """
    Returns numeric limit (e.g. max_discount_percent or max_expense_limit) for the user's role.
    Hotel Owners, Super Admins, and Superusers have float('inf') (unrestricted).
    """
    if not user or not user.is_authenticated:
        return fallback
    if user.is_superuser or user.role in ['SUPERUSER', 'HOTEL_OWNER', 'SUPER_ADMIN']:
        return float('inf')

    perms = RolePermission.get_permissions_for_role(user.role, getattr(user, 'property', None))
    mod_perms = perms.get(module, {})
    val = mod_perms.get(key)
    try:
        return float(val) if val is not None else float(fallback)
    except (TypeError, ValueError):
        return float(fallback)


def require_perm(user, module, action, error_message=None):
    """
    Raises PermissionDenied if the user does not have the specified permission.
    """
    if not user_has_perm(user, module, action):
        action_name = action.replace('can_', '').replace('_', ' ').capitalize()
        role_name = getattr(user, 'role', 'Staff')
        msg = error_message or f"Staff role '{role_name}' does not have permission to perform '{action_name}' in {module}."
        raise PermissionDenied({
            'detail': msg,
            'code': 'permission_denied',
            'module': module,
            'action': action,
            'role': role_name
        })



class IsSuperUser(BasePermission):
    """Platform Developer / SaaS Owner"""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and (request.user.is_superuser or request.user.role == 'SUPERUSER'))


class IsHotelOwner(BasePermission):
    """Hotel / Lodge Property Owner (Full unrestricted rights)"""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and (
            request.user.is_superuser or request.user.role in ['HOTEL_OWNER', 'SUPER_ADMIN', 'SUPERUSER']
        ))


class IsSuperAdmin(IsHotelOwner):
    """Backward compatibility alias for IsHotelOwner"""
    pass


class IsManager(BasePermission):
    """Operations Manager or above"""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and (
            request.user.is_superuser or request.user.role in ['HOTEL_OWNER', 'SUPER_ADMIN', 'SUPERUSER', 'MANAGER']
        ))


class IsReceptionist(BasePermission):
    """Receptionist or above"""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and (
            request.user.is_superuser or request.user.role in ['HOTEL_OWNER', 'SUPER_ADMIN', 'SUPERUSER', 'MANAGER', 'RECEPTIONIST']
        ))


class HasModelPermission(BasePermission):
    """
    Dynamic model permission evaluator.
    Usage: permission_classes = [HasModelPermission('bookings', 'can_create')]
    """
    def __init__(self, module, action):
        self.module = module
        self.action = action

    def __call__(self):
        return self

    def has_permission(self, request, view):
        return user_has_perm(request.user, self.module, self.action)

