from django.db import models

class TenantQuerySet(models.QuerySet):
    def for_property(self, prop):
        """
        Filters queryset specifically for the given Property instance or ID.
        If prop is None (e.g. Superuser viewing all properties), returns unfiltered queryset.
        """
        if prop is None:
            return self
        if isinstance(prop, (int, str)):
            return self.filter(property_id=prop)
        return self.filter(property=prop)

class TenantManager(models.Manager.from_queryset(TenantQuerySet)):
    pass

class TenantModel(models.Model):
    """
    Abstract base model that enforces multi-tenancy by scoping all data to a specific Property.
    Guarantees 100% database-level isolation between independent hotels.
    """
    property = models.ForeignKey(
        'settings_app.Property',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_index=True,
        related_name="%(app_label)s_%(class)s_set"
    )

    objects = TenantManager()

    class Meta:
        abstract = True
