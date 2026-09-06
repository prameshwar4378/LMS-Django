from django.contrib.auth.models import AbstractUser
from django.db import models

DEFAULT_PERMISSIONS = {
    'MANAGER': {
        'rooms': {'can_view': True, 'can_create': True, 'can_edit_tariffs': True, 'can_change_status': True},
        'bookings': {'can_view': True, 'can_create': True, 'can_edit': True, 'can_cancel': True, 'can_delete': True},
        'stays': {'can_checkin': True, 'can_checkout': True, 'can_checkout_with_balance': True, 'can_extend': True},
        'billing': {'can_collect_payment': True, 'can_give_discount': True, 'max_discount_percent': 25.0, 'can_refund': True, 'can_void': True},
        'counter_till': {'can_record_expense': True, 'max_expense_limit': 2000.0, 'can_adjust_float': True, 'can_close_till': True},
        'reports': {'can_view_revenue': True, 'can_view_police_gazette': True, 'can_export_excel': True},
        'night_audit': {'can_run_night_audit': True, 'can_rollback_audit': True}
    },
    'RECEPTIONIST': {
        'rooms': {'can_view': True, 'can_create': False, 'can_edit_tariffs': False, 'can_change_status': True},
        'bookings': {'can_view': True, 'can_create': True, 'can_edit': True, 'can_cancel': True, 'can_delete': False},
        'stays': {'can_checkin': True, 'can_checkout': True, 'can_checkout_with_balance': False, 'can_extend': True},
        'billing': {'can_collect_payment': True, 'can_give_discount': True, 'max_discount_percent': 10.0, 'can_refund': False, 'can_void': False},
        'counter_till': {'can_record_expense': True, 'max_expense_limit': 500.0, 'can_adjust_float': False, 'can_close_till': True},
        'reports': {'can_view_revenue': False, 'can_view_police_gazette': True, 'can_export_excel': False},
        'night_audit': {'can_run_night_audit': False, 'can_rollback_audit': False}
    }
}

class User(AbstractUser):
    class Role(models.TextChoices):
        SUPERUSER = 'SUPERUSER', 'Superuser (Developer / SaaS Platform Owner)'
        HOTEL_OWNER = 'HOTEL_OWNER', 'Hotel Owner'
        SUPER_ADMIN = 'SUPER_ADMIN', 'Super Admin (Owner)'
        MANAGER = 'MANAGER', 'Manager'
        RECEPTIONIST = 'RECEPTIONIST', 'Receptionist'

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.RECEPTIONIST
    )
    property = models.ForeignKey(
        'settings_app.Property',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='staff_users',
        help_text="Assigned lodge property for multi-tenant isolation"
    )

    def is_hotel_owner(self):
        return self.is_superuser or self.role in [self.Role.HOTEL_OWNER, self.Role.SUPER_ADMIN, self.Role.SUPERUSER]

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"


class RolePermission(models.Model):
    role = models.CharField(max_length=20, db_index=True)
    property = models.ForeignKey(
        'settings_app.Property',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='role_permissions',
        help_text="Hotel property this permission matrix applies to (or null for global defaults)"
    )
    permissions = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['role', 'property'], name='unique_role_property')
        ]

    def __str__(self):
        prop_str = f" for {self.property.name}" if self.property else " (Global)"
        return f"Permissions for {self.role}{prop_str}"

    @classmethod
    def get_permissions_for_role(cls, role, prop=None):
        import copy
        if role in ['SUPERUSER', 'HOTEL_OWNER', 'SUPER_ADMIN']:
            return {
                'rooms': {'can_view': True, 'can_create': True, 'can_edit_tariffs': True, 'can_change_status': True},
                'bookings': {'can_view': True, 'can_create': True, 'can_edit': True, 'can_cancel': True, 'can_delete': True},
                'stays': {'can_checkin': True, 'can_checkout': True, 'can_checkout_with_balance': True, 'can_extend': True},
                'billing': {'can_collect_payment': True, 'can_give_discount': True, 'max_discount_percent': 100.0, 'can_refund': True, 'can_void': True},
                'counter_till': {'can_record_expense': True, 'max_expense_limit': 1000000.0, 'can_adjust_float': True, 'can_close_till': True},
                'reports': {'can_view_revenue': True, 'can_view_police_gazette': True, 'can_export_excel': True},
                'night_audit': {'can_run_night_audit': True, 'can_rollback_audit': True}
            }

        defaults = copy.deepcopy(DEFAULT_PERMISSIONS.get(role, {}))

        root_prop = prop
        if prop and hasattr(prop, 'get_root_property'):
            root_prop = prop.get_root_property() or prop
        elif prop and getattr(prop, 'parent_property', None):
            root_prop = prop.parent_property

        obj = None
        if root_prop:
            obj = cls.objects.filter(role=role, property=root_prop).first()
        if not obj:
            obj = cls.objects.filter(role=role, property__isnull=True).first()

        if obj and obj.permissions:
            for mod, perms in obj.permissions.items():
                if mod in defaults and isinstance(perms, dict):
                    defaults[mod].update(perms)
                else:
                    defaults[mod] = perms
            return defaults

        return defaults


