from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from .models import Settings
from .serializers import SettingsSerializer
from apps.authentication.permissions import IsSuperAdmin

class SettingsViewSet(viewsets.ModelViewSet):
    queryset = Settings.objects.all()
    serializer_class = SettingsSerializer
    permission_classes = [permissions.IsAuthenticated]

    def list(self, request, *args, **kwargs):
        settings_obj = Settings.get_settings()
        serializer = self.get_serializer(settings_obj)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        settings_obj = Settings.get_settings()
        serializer = self.get_serializer(settings_obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
