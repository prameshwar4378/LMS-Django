from django.urls import path
from .views import DashboardReportView, RevenueReportView, OccupancyReportView, GuestRegisterReportView

urlpatterns = [
    path('reports/dashboard/', DashboardReportView.as_view(), name='report_dashboard'),
    path('reports/revenue/', RevenueReportView.as_view(), name='report_revenue'),
    path('reports/occupancy/', OccupancyReportView.as_view(), name='report_occupancy'),
    path('reports/guest-register/', GuestRegisterReportView.as_view(), name='report_guest_register'),
]
