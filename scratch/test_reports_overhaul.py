import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS.settings')
django.setup()

from rest_framework.test import APIRequestFactory, force_authenticate
from django.contrib.auth import get_user_model
from apps.reports.views import ReportDataView, ReportFilterOptionsView
from apps.shifts.models import Shift

User = get_user_model()
admin_user = User.objects.filter(is_superuser=True).first() or User.objects.first()

factory = APIRequestFactory()

print("=== STARTING REPORTS OVERHAUL VERIFICATION TESTS ===")

# Test 1: ReportFilterOptionsView returns shifts
req1 = factory.get('/api/reports/filter-options/')
force_authenticate(req1, user=admin_user)
res1 = ReportFilterOptionsView.as_view()(req1)
assert res1.status_code == 200, f"Expected 200, got {res1.status_code}"
shifts = res1.data.get('shifts', [])
print(f"[PASS] Test 1: ReportFilterOptionsView returned {len(shifts)} shifts")
assert len(shifts) > 0, "No shifts returned in filter options"
first_shift = shifts[0]
print(f"       Sample shift: #{first_shift['shift_number']} by {first_shift['user_name']} ({first_shift['status_display']})")
assert 'shift_number' in first_shift
assert 'user_name' in first_shift
assert 'cash_drawer_code' in first_shift

# Test 2: Shift Activity Dossier (Latest Shift)
req2 = factory.get('/api/reports/data/?category=shift_audit&report_id=shift_dossier')
force_authenticate(req2, user=admin_user)
res2 = ReportDataView.as_view()(req2)
assert res2.status_code == 200, f"Expected 200, got {res2.status_code}"
data2 = res2.data
print(f"[PASS] Test 2: Shift Activity Dossier fetched: '{data2.get('title')}'")
assert len(data2.get('kpis', [])) == 4, f"Expected 4 KPIs, got {len(data2.get('kpis', []))}"
print(f"       KPIs: {[k['label'] + ': ' + str(k['value']) for k in data2['kpis']]}")
shift_info = data2.get('shift_info')
assert shift_info is not None, "shift_info missing in response"
print(f"       Shift Info: #{shift_info['shift_number']} | Cashier: {shift_info['cashier_name']} | Drawer: {shift_info['drawer_name']}")
print(f"       Activity breakdown: {len(shift_info.get('payments', []))} payments, {len(shift_info.get('checkins', []))} checkins, {len(shift_info.get('checkouts', []))} checkouts, {len(shift_info.get('expenses', []))} expenses, {len(shift_info.get('denominations', []))} denominations")

# Test 3: Shift Activity Dossier with specific shift_id
target_shift = Shift.objects.order_by('-opened_at').first()
req3 = factory.get(f'/api/reports/data/?category=shift_audit&report_id=shift_dossier&shift_id={target_shift.id}')
force_authenticate(req3, user=admin_user)
res3 = ReportDataView.as_view()(req3)
assert res3.status_code == 200
assert res3.data['shift_info']['id'] == target_shift.id
print(f"[PASS] Test 3: Specific shift_id={target_shift.id} successfully routed and verified")

# Test 4: Verify existing report categories still work 100% untouched
# 4a: Checkin report
req4a = factory.get('/api/reports/data/?category=stay_guest&report_id=checkin_report&period=all')
force_authenticate(req4a, user=admin_user)
res4a = ReportDataView.as_view()(req4a)
assert res4a.status_code == 200
print(f"[PASS] Test 4a: Stay & Operations ('checkin_report') verified, returned {len(res4a.data.get('rows', []))} rows")

# 4b: Daily Revenue report
req4b = factory.get('/api/reports/data/?category=revenue_payments&report_id=daily_revenue&period=this_month')
force_authenticate(req4b, user=admin_user)
res4b = ReportDataView.as_view()(req4b)
assert res4b.status_code == 200
print(f"[PASS] Test 4b: Revenue & Finance ('daily_revenue') verified, returned {len(res4b.data.get('rows', []))} rows")

# 4c: GST Summary report
req4c = factory.get('/api/reports/data/?category=gst_tax&report_id=gst_summary&period=all')
force_authenticate(req4c, user=admin_user)
res4c = ReportDataView.as_view()(req4c)
assert res4c.status_code == 200
print(f"[PASS] Test 4c: GST & Tax ('gst_summary') verified, returned {len(res4c.data.get('rows', []))} rows")

print("\n=== ALL REPORTS OVERHAUL & SHIFT DOSSIER TESTS PASSED SUCCESSFULLY! ===")
