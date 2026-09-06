from django.urls import path
from .views import (
    DashboardReportView,
    RevenueReportView,
    OccupancyReportView,
    GuestRegisterReportView,
    ReportDataView,
    ReportFilterOptionsView,
    NightAuditView,
    ShiftReconciliationReportView
)

urlpatterns = [
    # Main Central Reports Engine Endpoints
    path('reports/data/', ReportDataView.as_view(), name='report_data'),
    path('reports/filter-options/', ReportFilterOptionsView.as_view(), name='report_filter_options'),
    path('reports/night-audit/', NightAuditView.as_view(), name='report_night_audit'),
    path('reports/shift-reconciliations/', ShiftReconciliationReportView.as_view(), name='report_shift_reconciliations'),

    # Legacy endpoints retained for backward compatibility
    path('reports/dashboard/', DashboardReportView.as_view(), name='report_dashboard'),
    path('reports/revenue/', RevenueReportView.as_view(), name='report_revenue'),
    path('reports/occupancy/', OccupancyReportView.as_view(), name='report_occupancy'),
    path('reports/guest-register/', GuestRegisterReportView.as_view(), name='report_guest_register'),
]
