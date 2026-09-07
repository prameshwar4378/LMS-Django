from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db import transaction, IntegrityError
from django.db.models import Q, Sum
from django.utils import timezone
from decimal import Decimal
import datetime
import uuid

from .models import Shift, ShiftDenomination, ShiftExpense, ShiftCashAdjustment, ShiftHandover, ShiftAuditLog, CashDrawer
from .serializers import (
    ShiftSerializer, ShiftDetailSerializer, ShiftExpenseSerializer,
    ShiftCashAdjustmentSerializer, ShiftHandoverSerializer, ShiftDenominationSerializer,
    CashDrawerSerializer
)
from .services import (
    get_active_shift_for_user, get_suggested_opening_balance,
    calculate_shift_financials, log_shift_action
)
from .notifications import trigger_shift_closing_notifications
from apps.settings_app.models import Settings
from apps.billing.models import Payment
from apps.billing.services import generate_unique_shift_number

def ensure_default_drawers(prop=None):
    if prop:
        if CashDrawer.objects.filter(property=prop).count() == 0:
            CashDrawer.objects.create(property=prop, name="Main Front Desk", code="POS-MAIN-01", location="Lobby Front Desk", default_float=Decimal('1000.00'))
            CashDrawer.objects.create(property=prop, name="Night Desk Counter", code="POS-NIGHT-01", location="Front Counter", default_float=Decimal('1000.00'))
            CashDrawer.objects.create(property=prop, name="Restaurant / Café POS", code="POS-CAFE-01", location="Ground Floor Restaurant", default_float=Decimal('500.00'))
            CashDrawer.objects.create(property=prop, name="Room Service Station", code="POS-RS-01", location="Kitchen Service Counter", default_float=Decimal('500.00'))
    else:
        if CashDrawer.objects.count() == 0:
            CashDrawer.objects.create(name="Main Front Desk", code="POS-MAIN-01", location="Lobby Front Desk", default_float=Decimal('1000.00'))
            CashDrawer.objects.create(name="Night Desk Counter", code="POS-NIGHT-01", location="Front Counter", default_float=Decimal('1000.00'))
            CashDrawer.objects.create(name="Restaurant / Café POS", code="POS-CAFE-01", location="Ground Floor Restaurant", default_float=Decimal('500.00'))
            CashDrawer.objects.create(name="Room Service Station", code="POS-RS-01", location="Kitchen Service Counter", default_float=Decimal('500.00'))

from apps.settings_app.tenant_views import TenantScopedViewSetMixin
from apps.authentication.permissions import user_has_perm, require_perm, get_perm_limit

def is_manager_or_admin(user):
    return user and (user.is_superuser or getattr(user, 'role', None) in ['SUPERUSER', 'HOTEL_OWNER', 'SUPER_ADMIN', 'MANAGER'])


class ShiftViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Shift.objects.all().select_related('user', 'closed_by', 'manager_approved_by', 'reopened_by', 'cash_drawer').order_by('-opened_at')
    serializer_class = ShiftSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.action in ['retrieve', 'close', 'current']:
            return ShiftDetailSerializer
        return ShiftSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        
        # Non-managers can see all shifts or filter their own, but default to list
        user_param = self.request.query_params.get('user')
        status_param = self.request.query_params.get('status')
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        discrepancy_only = self.request.query_params.get('discrepancy_only') in ['true', '1', True]
        search = self.request.query_params.get('search')

        if not is_manager_or_admin(user) and self.request.query_params.get('my_only') in ['true', '1', True]:
            queryset = queryset.filter(user=user)

        if user_param:
            queryset = queryset.filter(user_id=user_param)

        if status_param:
            queryset = queryset.filter(status=status_param)

        if start_date:
            queryset = queryset.filter(opened_at__date__gte=start_date)

        if end_date:
            queryset = queryset.filter(opened_at__date__lte=end_date)

        if discrepancy_only:
            queryset = queryset.filter(~Q(cash_difference=Decimal('0.00')), actual_cash__isnull=False)

        if search:
            queryset = queryset.filter(
                Q(shift_number__icontains=search) |
                Q(user__first_name__icontains=search) |
                Q(user__last_name__icontains=search) |
                Q(user__username__icontains=search)
            )

        return queryset

    @action(detail=False, methods=['get'])
    def current(self, request):
        """
        Returns active shift for current logged in user with live financial breakdown.
        If no active shift, returns suggested opening balance from last closed shift.
        """
        user = request.user
        prop = getattr(user, 'property', None)
        sett = Settings.get_settings(prop=prop)
        is_shift_wise = getattr(prop, 'is_shift_wise', True) if prop else (getattr(sett, 'shift_operation_mode', None) != 'SINGLE_OPERATOR')
        active_shift = get_active_shift_for_user(user)
        # Pending incoming handovers for this user
        pending_handovers = ShiftHandover.objects.filter(to_user=user, status=ShiftHandover.Status.PENDING)
        handovers_data = ShiftHandoverSerializer(pending_handovers, many=True).data

        if active_shift:
            serializer = ShiftDetailSerializer(active_shift)
            return Response({
                'has_active_shift': True,
                'is_shift_wise': is_shift_wise,
                'shifts_enabled': is_shift_wise,
                'shift': serializer.data,
                'financials': calculate_shift_financials(active_shift),
                'operation_mode': getattr(prop, 'operation_mode', 'SHIFT_WISE') if prop else sett.shift_operation_mode,
                'pending_handovers': handovers_data
            })
        else:
            suggested_balance = get_suggested_opening_balance()
            last_closed = Shift.objects.filter(status=Shift.Status.CLOSED).order_by('-closed_at', '-id').first()

            return Response({
                'has_active_shift': False,
                'is_shift_wise': is_shift_wise,
                'shifts_enabled': is_shift_wise,
                'operation_mode': getattr(prop, 'operation_mode', 'SHIFT_WISE') if prop else sett.shift_operation_mode,
                'suggested_opening_balance': suggested_balance,
                'last_closed_shift': {
                    'shift_number': last_closed.shift_number if last_closed else None,
                    'closed_at': last_closed.closed_at.strftime('%Y-%m-%d %H:%M') if last_closed and last_closed.closed_at else None,
                    'closing_cash': float(last_closed.actual_cash if last_closed and last_closed.actual_cash is not None else (last_closed.expected_cash if last_closed else 0.00))
                } if last_closed else None,
                'pending_handovers': handovers_data
            })

    @action(detail=False, methods=['post'])
    @transaction.atomic
    def open(self, request):
        """
        Opens a new shift for the authenticated receptionist / cashier.
        """
        user = request.user
        user_prop = getattr(user, 'property', None) if user and not user.is_superuser else None
        if user_prop and hasattr(user_prop, 'is_single_owner') and user_prop.is_single_owner:
            return Response({
                'success': False,
                'message': 'Shift operations are disabled for this property because it is configured in Single Owner Mode by the platform administrator.',
                'errors': {'shift': ['Shifts disabled in Single Owner Mode.']}
            }, status=status.HTTP_400_BAD_REQUEST)

        # 1. Check for existing active shift
        existing_shift = get_active_shift_for_user(user)
        if existing_shift:
            return Response({
                'success': False,
                'message': f'You already have an active shift (#{existing_shift.shift_number}). Please close it before opening a new one.',
                'errors': {'shift': ['User already has an active shift.']}
            }, status=status.HTTP_400_BAD_REQUEST)

        # 2. Parse Opening Balance
        try:
            opening_balance = Decimal(str(request.data.get('opening_balance', 0) or 0))
            if opening_balance < 0:
                raise ValueError("Opening balance cannot be negative.")
        except Exception as e:
            return Response({
                'success': False,
                'message': 'Invalid opening balance amount.',
                'errors': {'opening_balance': [str(e)]}
            }, status=status.HTTP_400_BAD_REQUEST)

        # 3. Check Cash Drawer / Register Assignment
        user_prop = getattr(user, 'property', None) if user and not user.is_superuser else None
        drawer_id = request.data.get('cash_drawer') or request.data.get('cash_drawer_id')
        drawer = None
        if drawer_id:
            drawer_filter = {'id': drawer_id, 'is_active': True}
            if user_prop:
                drawer_filter['property'] = user_prop
            drawer = CashDrawer.objects.filter(**drawer_filter).first()
            if drawer and not drawer.allow_shared_users:
                occupied = Shift.objects.filter(
                    cash_drawer=drawer,
                    status__in=[Shift.Status.OPEN, Shift.Status.CLOSING]
                ).exclude(user=user).first()
                if occupied:
                    occupied_by = occupied.user.get_full_name() or occupied.user.username
                    return Response({
                        'success': False,
                        'message': f"Register '{drawer.name}' ({drawer.code}) is currently in use by {occupied_by} (Shift #{occupied.shift_number}). Please select an available drawer.",
                        'errors': {'cash_drawer': ['Register is currently in use by another cashier.']}
                    }, status=status.HTTP_400_BAD_REQUEST)

        # 4. Generate Unique Shift Number (SHIFT-YYYYMMDD-XXX)
        prefix = "SHIFT-"
        opening_notes = request.data.get('opening_notes', '')

        # 5. Create Shift record
        shift = None
        for _ in range(10):
            shift_number = generate_unique_shift_number(user_prop, prefix)
            try:
                with transaction.atomic():
                    shift = Shift.objects.create(
                        property=user_prop,
                        shift_number=shift_number,
                        cash_drawer=drawer,
                        user=user,
                        opened_at=timezone.now(),
                        opening_balance=opening_balance,
                        expected_cash=opening_balance,
                        status=Shift.Status.OPEN,
                        opening_notes=opening_notes
                    )
                break
            except IntegrityError:
                continue

        # 5. Link any accepted Handover if provided
        handover_id = request.data.get('handover_id')
        if handover_id:
            handover = ShiftHandover.objects.filter(id=handover_id, to_user=user, status=ShiftHandover.Status.PENDING).first()
            if handover:
                handover.to_shift = shift
                handover.status = ShiftHandover.Status.ACCEPTED
                handover.received_at = timezone.now()
                handover.save()
                log_shift_action(shift, user, 'HANDOVER_ACCEPTED', f'Accepted cash handover of ₹{handover.amount:.2f} from {handover.from_user.username}', {'handover_id': handover.id, 'amount': float(handover.amount)})

        # 6. Audit Log
        log_shift_action(
            shift,
            user,
            'SHIFT_OPENED',
            f'Shift opened by {user.get_full_name() or user.username} with opening balance ₹{opening_balance:.2f}',
            {'opening_balance': float(opening_balance), 'notes': opening_notes}
        )

        return Response({
            'success': True,
            'message': f'Shift #{shift.shift_number} opened successfully.',
            'data': ShiftDetailSerializer(shift).data
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def close(self, request, pk=None):
        """
        Close Shift workflow with physical denomination counting and discrepancy detection.
        """
        require_perm(request.user, 'counter_till', 'can_close_till', "You do not have permission to submit end-of-day till closing.")
        shift = self.get_object()
        user = request.user

        # Permission check
        if shift.user != user and not is_manager_or_admin(user):
            return Response({
                'success': False,
                'message': 'You are not authorized to close another user\'s shift.',
                'errors': {'permission': ['Unauthorized.']}
            }, status=status.HTTP_403_FORBIDDEN)


        if shift.status == Shift.Status.CLOSED:
            return Response({
                'success': False,
                'message': 'This shift is already closed.',
                'errors': {'status': ['Shift is already closed.']}
            }, status=status.HTTP_400_BAD_REQUEST)

        # 1. Process Denominations
        denominations_data = request.data.get('denominations', [])
        import json
        if isinstance(denominations_data, str):
            try:
                denominations_data = json.loads(denominations_data)
            except Exception:
                denominations_data = []
        elif not isinstance(denominations_data, list):
            denominations_data = []

        total_counted = Decimal('0.00')

        # Clean old denominations if re-submitting
        shift.denominations.all().delete()

        valid_units = {
            '500': Decimal('500.00'),
            '200': Decimal('200.00'),
            '100': Decimal('100.00'),
            '50': Decimal('50.00'),
            '20': Decimal('20.00'),
            '10': Decimal('10.00'),
            '5': Decimal('5.00'),
            'COINS': Decimal('1.00'),
            '1': Decimal('1.00')
        }

        for item in denominations_data:
            if not isinstance(item, dict):
                continue
            denom_key = str(item.get('denomination', '')).strip().upper()
            qty = int(item.get('quantity', 0) or 0)
            if qty > 0 and denom_key:
                unit_val = valid_units.get(denom_key, Decimal(str(item.get('unit_value', 1.0))))
                line_total = Decimal(str(qty)) * unit_val
                total_counted += line_total
                ShiftDenomination.objects.create(
                    shift=shift,
                    denomination=denom_key,
                    unit_value=unit_val,
                    quantity=qty,
                    total=line_total
                )

        # Allow direct actual_cash override if provided and no denomination list
        if not denominations_data and 'actual_cash' in request.data:
            try:
                total_counted = Decimal(str(request.data.get('actual_cash', 0) or 0))
            except Exception:
                total_counted = Decimal('0.00')

        # 2. Compute Backend Expected Cash
        fin = calculate_shift_financials(shift)
        expected_cash_dec = Decimal(str(fin['expected_cash']))
        difference = total_counted - expected_cash_dec

        closing_notes = request.data.get('closing_notes', '') or ''
        difference_reason = request.data.get('difference_reason', '') or ''

        # 3. Update Shift attributes
        shift.actual_cash = total_counted
        shift.expected_cash = expected_cash_dec
        shift.cash_difference = difference
        shift.closing_notes = closing_notes
        shift.closed_by = user
        shift.updated_by = user

        # 4. State Transition
        sett_mode = Settings.get_settings().shift_operation_mode
        is_admin_closing = is_manager_or_admin(user) or (sett_mode == 'SINGLE_OPERATOR')

        if difference == Decimal('0.00'):
            shift.status = Shift.Status.CLOSED
            shift.closed_at = timezone.now()
            message = f'Shift #{shift.shift_number} reconciled and closed successfully with zero difference.'
            action_name = 'SHIFT_CLOSED_RECONCILED'
        elif is_admin_closing:
            # Manager/Owner closing with difference is self-approved and closed directly
            shift.status = Shift.Status.CLOSED
            shift.closed_at = timezone.now()
            shift.manager_approved_by = user
            shift.manager_approved_at = timezone.now()
            shift.difference_reason = difference_reason or "Variance approved during shift closing by Owner/Manager."
            shift.manager_approval_notes = f"Self-approved by {user.get_full_name() or user.username} upon shift closing."
            discrepancy_str = f"Shortage of ₹{abs(difference):.2f}" if difference < 0 else f"Excess of ₹{difference:.2f}"
            message = f'Shift #{shift.shift_number} closed and reconciled with {discrepancy_str} by Owner/Manager.'
            action_name = 'SHIFT_CLOSED_BY_ADMIN'
        else:
            # Receptionist closing with shortage or excess requires managerial approval
            shift.status = Shift.Status.PENDING_APPROVAL
            blind_enabled = Settings.get_settings().enable_blind_till_closing
            shift.difference_reason = difference_reason or ("Blind Count Discrepancy - Routed for Manager Approval" if blind_enabled else "")
            discrepancy_str = f"Shortage of ₹{abs(difference):.2f}" if difference < 0 else f"Excess of ₹{difference:.2f}"
            message = f'Shift #{shift.shift_number} submitted with {discrepancy_str}. Routed to manager for approval.'
            action_name = 'SHIFT_CLOSING_PENDING_APPROVAL'

        shift.save()

        # 5. Audit Log
        log_shift_action(
            shift,
            user,
            action_name,
            f"Closing submitted: Expected ₹{expected_cash_dec:.2f}, Counted ₹{total_counted:.2f}, Difference: ₹{difference:.2f}",
            {
                'expected_cash': float(expected_cash_dec),
                'actual_cash': float(total_counted),
                'difference': float(difference),
                'reason': difference_reason,
                'closing_notes': closing_notes
            }
        )

        # 6. Trigger Instant Notifications (WhatsApp & Email to Owner/Managers)
        trigger_shift_closing_notifications(shift)

        return Response({
            'success': True,
            'message': message,
            'data': ShiftDetailSerializer(shift).data,
            'is_reconciled': difference == Decimal('0.00'),
            'difference': float(difference)
        })

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def expenses(self, request, pk=None):
        """
        Record a cash expense from the till during the active shift.
        """
        require_perm(request.user, 'counter_till', 'can_record_expense', "You do not have permission to disburse counter petty cash.")
        shift = self.get_object()
        user = request.user

        if shift.status != Shift.Status.OPEN and not is_manager_or_admin(user):
            return Response({'success': False, 'message': 'Expenses can only be added to an OPEN shift.', 'errors': {'status': ['Shift is not open.']}}, status=status.HTTP_400_BAD_REQUEST)

        amount = request.data.get('amount')
        description = request.data.get('description')
        category = request.data.get('category', ShiftExpense.Category.OTHER)
        manager_pin = str(request.data.get('manager_pin', '')).strip()

        if not amount or float(amount) <= 0:
            return Response({'success': False, 'message': 'A valid positive expense amount is required.', 'errors': {'amount': ['Must be positive.']}}, status=status.HTTP_400_BAD_REQUEST)

        if not description:
            return Response({'success': False, 'message': 'Expense description is required.', 'errors': {'description': ['Required.']}}, status=status.HTTP_400_BAD_REQUEST)

        expense_amount = Decimal(str(amount))

        # Check Threshold Limits & Manager Governance
        settings_obj = Settings.get_settings()
        default_max_exp = Decimal(str(getattr(settings_obj, 'max_cash_expense_without_approval', 1000.00) or 1000.00))
        role_limit = Decimal(str(get_perm_limit(user, 'counter_till', 'max_expense_limit', fallback=float(default_max_exp))))
        max_limit = role_limit if role_limit < Decimal('1000000') else default_max_exp
        daily_cap = Decimal(str(getattr(settings_obj, 'daily_petty_cash_cap', 5000.00) or 5000.00))
        
        current_shift_expenses = ShiftExpense.objects.filter(shift=shift).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
        new_total_expenses = current_shift_expenses + expense_amount

        is_manager = is_manager_or_admin(user) or (settings_obj.shift_operation_mode == 'SINGLE_OPERATOR')
        requires_approval = ((expense_amount > max_limit) or (new_total_expenses > daily_cap)) and (settings_obj.shift_operation_mode != 'SINGLE_OPERATOR')

        approved_by = None
        if is_manager:
            approved_by = user
        elif requires_approval:
            valid_pin = settings_obj.manager_override_pin or "1234"
            if not manager_pin or manager_pin != valid_pin:
                limit_msg = f"Single expense of ₹{expense_amount:.2f} exceeds your role limit of ₹{max_limit:.2f}." if expense_amount > max_limit else f"Total expenses of ₹{new_total_expenses:.2f} exceed daily cap of ₹{daily_cap:.2f}."
                return Response({
                    'success': False,
                    'message': f"{limit_msg} Valid Manager Override PIN is required.",
                    'requires_manager_pin': True,
                    'errors': {'manager_pin': ['Invalid or missing Manager Override PIN.']}
                }, status=status.HTTP_400_BAD_REQUEST)
            
            from django.contrib.auth import get_user_model
            User = get_user_model()
            approved_by = User.objects.filter(role__in=['SUPER_ADMIN', 'MANAGER']).first() or user

        expense = ShiftExpense.objects.create(
            shift=shift,
            category=category,
            amount=expense_amount,
            description=description,
            receipt=request.FILES.get('receipt'),
            created_by=user,
            is_manager_approved=bool(approved_by or not requires_approval),
            approved_by=approved_by
        )

        # Update expected cash on shift
        fin = calculate_shift_financials(shift)
        shift.expected_cash = Decimal(str(fin['expected_cash']))
        shift.save()

        approval_str = f" [Approved by Manager {approved_by.username}]" if approved_by else ""
        log_shift_action(
            shift,
            user,
            'EXPENSE_ADDED',
            f'Cash expense of ₹{expense.amount:.2f} for {expense.description} recorded by {user.username}{approval_str}',
            {
                'expense_id': expense.id,
                'category': expense.category,
                'amount': float(expense.amount),
                'requires_approval': requires_approval
            }
        )

        return Response({
            'success': True,
            'message': f'Expense of ₹{expense.amount:.2f} recorded successfully.{approval_str}',
            'data': ShiftExpenseSerializer(expense).data,
            'financials': fin
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def adjustments(self, request, pk=None):
        """
        Record cash added (float in) or cash removed (bank drop / manager float out).
        """
        require_perm(request.user, 'counter_till', 'can_adjust_float', "You do not have permission to perform float adjustments or safe drops.")
        shift = self.get_object()
        user = request.user


        if shift.status != Shift.Status.OPEN and not is_manager_or_admin(user):
            return Response({'success': False, 'message': 'Adjustments can only be added to an OPEN shift.', 'errors': {'status': ['Shift is not open.']}}, status=status.HTTP_400_BAD_REQUEST)

        adj_type = request.data.get('adjustment_type')
        amount = request.data.get('amount')
        reason = request.data.get('reason')

        if adj_type not in [ShiftCashAdjustment.AdjustmentType.ADD_CASH, ShiftCashAdjustment.AdjustmentType.REMOVE_CASH]:
            return Response({'success': False, 'message': 'Invalid adjustment type. Must be ADD_CASH or REMOVE_CASH.', 'errors': {'adjustment_type': ['Invalid.']}}, status=status.HTTP_400_BAD_REQUEST)

        if not amount or float(amount) <= 0:
            return Response({'success': False, 'message': 'A valid positive adjustment amount is required.', 'errors': {'amount': ['Must be positive.']}}, status=status.HTTP_400_BAD_REQUEST)

        if not reason:
            return Response({'success': False, 'message': 'Reason for cash adjustment is mandatory.', 'errors': {'reason': ['Required.']}}, status=status.HTTP_400_BAD_REQUEST)

        adjustment = ShiftCashAdjustment.objects.create(
            shift=shift,
            adjustment_type=adj_type,
            amount=Decimal(str(amount)),
            reason=reason,
            notes=request.data.get('notes', ''),
            created_by=user,
            approved_by=user if is_manager_or_admin(user) else None
        )

        # Update expected cash on shift
        fin = calculate_shift_financials(shift)
        shift.expected_cash = Decimal(str(fin['expected_cash']))
        shift.save()

        log_shift_action(
            shift,
            user,
            'CASH_ADJUSTED',
            f'{adjustment.get_adjustment_type_display()} of ₹{adjustment.amount:.2f} ({adjustment.reason})',
            {'adjustment_id': adjustment.id, 'type': adjustment.adjustment_type, 'amount': float(adjustment.amount)}
        )

        return Response({
            'success': True,
            'message': f'{adjustment.get_adjustment_type_display()} of ₹{adjustment.amount:.2f} recorded.',
            'data': ShiftCashAdjustmentSerializer(adjustment).data,
            'financials': fin
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def approve(self, request, pk=None):
        """
        Manager approval for discrepancy / pending reconciliation.
        """
        shift = self.get_object()
        user = request.user

        if not is_manager_or_admin(user):
            return Response({'success': False, 'message': 'Only Managers and Super Admins can approve shift discrepancies.', 'errors': {'permission': ['Unauthorized.']}}, status=status.HTTP_403_FORBIDDEN)

        notes = request.data.get('approval_notes', '')

        shift.status = Shift.Status.CLOSED
        shift.closed_at = shift.closed_at or timezone.now()
        shift.manager_approved_by = user
        shift.manager_approval_notes = notes
        shift.manager_approved_at = timezone.now()
        shift.updated_by = user
        shift.save()

        log_shift_action(
            shift,
            user,
            'DISCREPANCY_APPROVED',
            f'Shift discrepancy of ₹{shift.cash_difference:.2f} approved by Manager {user.username}. Shift is now CLOSED.',
            {'approved_by': user.username, 'difference': float(shift.cash_difference), 'notes': notes}
        )

        # Trigger Instant Notifications upon manager approval
        trigger_shift_closing_notifications(shift)

        return Response({
            'success': True,
            'message': f'Shift #{shift.shift_number} discrepancy approved and shift is marked CLOSED.',
            'data': ShiftDetailSerializer(shift).data
        })

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def force_close(self, request, pk=None):
        """
        Manager / Super Admin forcibly closes an abandoned or overdue shift.
        """
        shift = self.get_object()
        user = request.user

        if not is_manager_or_admin(user):
            return Response({
                'success': False,
                'message': 'Only Managers and Super Admins can force close a shift.',
                'errors': {'permission': ['Unauthorized.']}
            }, status=status.HTTP_403_FORBIDDEN)

        if shift.status in [Shift.Status.CLOSED, Shift.Status.FORCED_CLOSED]:
            return Response({
                'success': False,
                'message': 'Shift is already closed.',
                'errors': {'status': ['Already closed.']}
            }, status=status.HTTP_400_BAD_REQUEST)

        reason = request.data.get('reason', '').strip()
        if not reason:
            return Response({
                'success': False,
                'message': 'An administrative reason is required to force close this shift.',
                'errors': {'reason': ['Required.']}
            }, status=status.HTTP_400_BAD_REQUEST)

        actual_cash = request.data.get('actual_cash')
        fin = calculate_shift_financials(shift)
        expected_cash_dec = Decimal(str(fin['expected_cash']))

        if actual_cash is not None and str(actual_cash).strip() != '':
            try:
                counted_dec = Decimal(str(actual_cash))
            except Exception:
                counted_dec = expected_cash_dec
        else:
            counted_dec = expected_cash_dec

        diff = counted_dec - expected_cash_dec

        shift.status = Shift.Status.FORCED_CLOSED
        shift.closed_at = timezone.now()
        shift.closed_by = user
        shift.manager_approved_by = user
        shift.manager_approved_at = timezone.now()
        shift.actual_cash = counted_dec
        shift.expected_cash = expected_cash_dec
        shift.cash_difference = diff
        shift.closing_notes = f"[ADMIN FORCED CLOSE] {reason}"
        shift.manager_approval_notes = f"Forced closed by {user.username}: {reason}"
        shift.updated_by = user
        shift.save()

        log_shift_action(
            shift,
            user,
            'ADMIN_FORCED_CLOSE',
            f'Shift #{shift.shift_number} was forcibly closed by Manager {user.username}. Reason: {reason}',
            {
                'forced_by': user.username,
                'reason': reason,
                'expected_cash': float(expected_cash_dec),
                'actual_cash': float(counted_dec),
                'difference': float(diff)
            }
        )

        trigger_shift_closing_notifications(shift)

        return Response({
            'success': True,
            'message': f'Shift #{shift.shift_number} has been forcibly closed by Administrator.',
            'data': ShiftDetailSerializer(shift).data
        })

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def reject(self, request, pk=None):
        """
        Manager rejects closing discrepancy and returns shift to CLOSING for recount.
        """
        shift = self.get_object()
        user = request.user

        if not is_manager_or_admin(user):
            return Response({'success': False, 'message': 'Only Managers and Super Admins can reject shift reconciliation.', 'errors': {'permission': ['Unauthorized.']}}, status=status.HTTP_403_FORBIDDEN)

        rejection_notes = request.data.get('rejection_notes', '')
        if not rejection_notes:
            return Response({'success': False, 'message': 'Rejection reason is required.', 'errors': {'rejection_notes': ['Required.']}}, status=status.HTTP_400_BAD_REQUEST)

        shift.status = Shift.Status.CLOSING
        shift.manager_approval_notes = f"Rejected: {rejection_notes}"
        shift.updated_by = user
        shift.save()

        log_shift_action(
            shift,
            user,
            'DISCREPANCY_REJECTED',
            f'Reconciliation rejected by Manager {user.username}: {rejection_notes}',
            {'rejected_by': user.username, 'notes': rejection_notes}
        )

        return Response({
            'success': True,
            'message': f'Shift #{shift.shift_number} closing rejected and returned for recount/explanation.',
            'data': ShiftDetailSerializer(shift).data
        })

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def reopen(self, request, pk=None):
        """
        Manager / Super Admin reopens a CLOSED shift with audit explanation.
        """
        shift = self.get_object()
        user = request.user

        if not is_manager_or_admin(user):
            return Response({'success': False, 'message': 'Only Managers and Super Admins can reopen shifts.', 'errors': {'permission': ['Unauthorized.']}}, status=status.HTTP_403_FORBIDDEN)

        reopen_reason = request.data.get('reopen_reason', '')
        if not reopen_reason:
            return Response({'success': False, 'message': 'Reopening justification reason is required.', 'errors': {'reopen_reason': ['Required.']}}, status=status.HTTP_400_BAD_REQUEST)

        shift.status = Shift.Status.OPEN
        shift.reopened_by = user
        shift.reopened_at = timezone.now()
        shift.reopen_reason = reopen_reason
        shift.updated_by = user
        shift.save()

        log_shift_action(
            shift,
            user,
            'SHIFT_REOPENED',
            f'Shift reopened by Manager {user.username}. Reason: {reopen_reason}',
            {'reopened_by': user.username, 'reason': reopen_reason}
        )

        return Response({
            'success': True,
            'message': f'Shift #{shift.shift_number} reopened successfully.',
            'data': ShiftDetailSerializer(shift).data
        })

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def handover(self, request, pk=None):
        """
        Initiate cash handover to another receptionist, with optional shift closing.
        """
        shift = self.get_object()
        from_user = request.user
        to_user_id = request.data.get('to_user')
        amount = request.data.get('amount')
        close_from_shift = request.data.get('close_from_shift') in [True, 'true', 'True', 1, '1']

        if not to_user_id:
            return Response({'success': False, 'message': 'Recipient receptionist (to_user) is required.', 'errors': {'to_user': ['Required.']}}, status=status.HTTP_400_BAD_REQUEST)

        if str(to_user_id) == str(from_user.id):
            return Response({
                'success': False,
                'message': 'You cannot hand over a shift to yourself.',
                'errors': {'to_user': ['Recipient receptionist cannot be yourself.']}
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            handover_amount_dec = Decimal(str(amount))
            if handover_amount_dec < Decimal('0.00'):
                raise ValueError()
        except Exception:
            return Response({'success': False, 'message': 'Valid non-negative handover amount is required.', 'errors': {'amount': ['Invalid amount.']}}, status=status.HTTP_400_BAD_REQUEST)

        from django.contrib.auth import get_user_model
        from apps.settings_app.models import Property
        User = get_user_model()

        # Resolve recipient user within property hierarchy, active tenant staff, or authorized users
        to_user = None
        if shift.property:
            root_prop = shift.property.parent_property or shift.property
            prop_ids = list(Property.objects.filter(
                Q(id=root_prop.id) | Q(parent_property=root_prop)
            ).values_list('id', flat=True))
            user_qs = User.objects.filter(is_active=True).filter(
                Q(property_id__in=prop_ids) |
                Q(is_superuser=True) |
                Q(role__in=['SUPER_ADMIN', 'SUPERUSER', 'HOTEL_OWNER', 'OWNER'])
            )
            to_user = user_qs.filter(pk=to_user_id).first()
            if not to_user and is_manager_or_admin(from_user):
                to_user = User.objects.filter(pk=to_user_id, is_active=True).first()
        else:
            to_user = User.objects.filter(pk=to_user_id, is_active=True).first()

        if not to_user:
            return Response({
                'success': False,
                'message': 'Selected recipient receptionist was not found or is inactive.',
                'errors': {'to_user': ['Recipient user not found.']}
            }, status=status.HTTP_400_BAD_REQUEST)

        handover = ShiftHandover.objects.create(
            from_shift=shift,
            from_user=from_user,
            to_user=to_user,
            amount=handover_amount_dec,
            status=ShiftHandover.Status.PENDING,
            notes=request.data.get('notes', ''),
            updated_by=from_user
        )

        # If outgoing employee chooses to finalize/close their shift during handover
        if close_from_shift and shift.status in [Shift.Status.OPEN, Shift.Status.CLOSING]:
            fin = calculate_shift_financials(shift)
            expected_drawer_cash = Decimal(str(fin['expected_cash'])) + handover_amount_dec
            diff = handover_amount_dec - expected_drawer_cash

            shift.actual_cash = handover_amount_dec
            shift.expected_cash = expected_drawer_cash
            shift.cash_difference = diff
            shift.closed_at = timezone.now()
            shift.closed_by = from_user
            shift.updated_by = from_user
            shift.closing_notes = f"Handover to {to_user.get_full_name() or to_user.username}: {request.data.get('notes', '')}".strip()

            if diff == Decimal('0.00') or is_manager_or_admin(from_user):
                shift.status = Shift.Status.CLOSED
                if diff != Decimal('0.00'):
                    shift.manager_approved_by = from_user
                    shift.manager_approved_at = timezone.now()
            else:
                shift.status = Shift.Status.PENDING_APPROVAL
                shift.difference_reason = f"Handover discrepancy: ₹{diff:.2f}"

            shift.save()
            trigger_shift_closing_notifications(shift)

        log_shift_action(
            shift,
            from_user,
            'HANDOVER_INITIATED',
            f'Handover of ₹{handover.amount:.2f} initiated to {to_user.get_full_name() or to_user.username}{" with shift finalized" if close_from_shift else ""}',
            {'handover_id': handover.id, 'to_user': to_user.username, 'amount': float(handover.amount), 'closed_shift': close_from_shift}
        )

        return Response({
            'success': True,
            'message': f'Handover of ₹{handover.amount:.2f} to {to_user.get_full_name() or to_user.username} initiated.',
            'data': ShiftHandoverSerializer(handover).data,
            'shift_closed': close_from_shift
        }, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'])
    def handover_recipients(self, request):
        """
        Returns active staff members eligible to receive a shift handover.
        Strictly scoped to the same hotel property and its branches.
        """
        user = request.user
        user_prop = self.get_property_for_request() or getattr(user, 'property', None)

        if not user_prop and not user.is_superuser:
            return Response({'success': True, 'results': []})

        from django.contrib.auth import get_user_model
        from apps.settings_app.models import Property
        User = get_user_model()

        if user.is_superuser and not user_prop:
            recipients_qs = User.objects.filter(is_active=True).exclude(id=user.id)
        else:
            root_prop = user_prop.parent_property or user_prop
            prop_ids = list(Property.objects.filter(
                Q(id=root_prop.id) | Q(parent_property=root_prop)
            ).values_list('id', flat=True))

            recipients_qs = User.objects.filter(
                is_active=True,
                property_id__in=prop_ids
            ).exclude(id=user.id).select_related('property').order_by('first_name', 'username')

        results = []
        for u in recipients_qs:
            is_same_branch = (u.property_id == user_prop.id) if user_prop else True
            branch_label = u.property.name if u.property else 'Main Hotel'
            full_name = u.get_full_name() or u.username
            results.append({
                'id': u.id,
                'username': u.username,
                'first_name': u.first_name,
                'last_name': u.last_name,
                'full_name': full_name,
                'role': u.role,
                'role_display': u.get_role_display() if hasattr(u, 'get_role_display') else u.role,
                'property_id': u.property_id,
                'property_name': branch_label,
                'is_same_branch': is_same_branch,
            })

        # Sort: same branch employees first, then by name
        results.sort(key=lambda x: (not x['is_same_branch'], x['full_name'].lower()))

        return Response({
            'success': True,
            'results': results
        })

    @action(detail=False, methods=['post'], url_path=r'handovers/(?P<handover_id>[^/.]+)/accept')
    @transaction.atomic
    def accept_handover(self, request, handover_id=None):
        """
        Incoming receptionist accepts a pending handover.
        If the user does not have an active shift, a new shift is automatically opened
        with the handover cash set as opening balance.
        """
        user = request.user
        handover = ShiftHandover.objects.filter(id=handover_id, to_user=user, status=ShiftHandover.Status.PENDING).first()
        if not handover:
            return Response({
                'success': False,
                'message': 'No pending handover found matching this ID for your user account.'
            }, status=status.HTTP_404_NOT_FOUND)

        active_shift = get_active_shift_for_user(user)

        if active_shift:
            # User already has an active shift: attach handover to current active shift
            handover.to_shift = active_shift
            handover.is_opening_handover = False
            handover.status = ShiftHandover.Status.ACCEPTED
            handover.received_at = timezone.now()
            handover.updated_by = user
            handover.save()

            log_shift_action(
                active_shift,
                user,
                'HANDOVER_ACCEPTED',
                f'Accepted cash handover of ₹{handover.amount:.2f} from {handover.from_user.get_full_name() or handover.from_user.username}',
                {'handover_id': handover.id, 'amount': float(handover.amount)}
            )

            # Update expected cash on current shift
            fin = calculate_shift_financials(active_shift)
            active_shift.expected_cash = Decimal(str(fin['expected_cash']))
            active_shift.updated_by = user
            active_shift.save()

            return Response({
                'success': True,
                'message': f'Handover of ₹{handover.amount:.2f} accepted into your active shift #{active_shift.shift_number}.',
                'shift': ShiftDetailSerializer(active_shift).data,
                'handover': ShiftHandoverSerializer(handover).data
            })
        else:
            # Open new shift for incoming user with handed-over cash
            user_prop = getattr(user, 'property', None) if user and not user.is_superuser else None
            drawer_id = request.data.get('cash_drawer') or (handover.from_shift.cash_drawer_id if handover.from_shift else None)
            drawer = None
            if drawer_id:
                drawer = CashDrawer.objects.filter(id=drawer_id).first()

            # Generate Unique Shift Number
            prefix = "SHIFT-"
            opening_notes = request.data.get('opening_notes') or f"Opened via accepted handover from {handover.from_user.get_full_name() or handover.from_user.username} (Shift #{handover.from_shift.shift_number if handover.from_shift else 'N/A'})"

            now = timezone.now()
            target_property = (handover.from_shift.property if handover.from_shift else None) or user_prop
            new_shift = None
            for _ in range(10):
                shift_number = generate_unique_shift_number(target_property, prefix)
                try:
                    with transaction.atomic():
                        new_shift = Shift.objects.create(
                            property=target_property,
                            shift_number=shift_number,
                            cash_drawer=drawer,
                            user=user,
                            opened_at=now,
                            opening_balance=handover.amount,
                            expected_cash=handover.amount,
                            status=Shift.Status.OPEN,
                            opening_notes=opening_notes,
                            updated_by=user
                        )
                    break
                except IntegrityError:
                    continue

            handover.to_shift = new_shift
            handover.is_opening_handover = True
            handover.status = ShiftHandover.Status.ACCEPTED
            handover.received_at = now
            handover.updated_by = user
            handover.save()

            log_shift_action(
                new_shift,
                user,
                'HANDOVER_ACCEPTED_AND_SHIFT_OPENED',
                f'Shift #{new_shift.shift_number} opened with accepted handover of ₹{handover.amount:.2f} from {handover.from_user.get_full_name() or handover.from_user.username}',
                {'handover_id': handover.id, 'amount': float(handover.amount), 'from_shift': handover.from_shift.shift_number if handover.from_shift else 'N/A'}
            )

            return Response({
                'success': True,
                'message': f'Handover of ₹{handover.amount:.2f} accepted. Shift #{new_shift.shift_number} opened successfully.',
                'shift': ShiftDetailSerializer(new_shift).data,
                'handover': ShiftHandoverSerializer(handover).data
            }, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], url_path=r'handovers/(?P<handover_id>[^/.]+)/reject')
    @transaction.atomic
    def reject_handover(self, request, handover_id=None):
        """
        Incoming receptionist rejects a pending handover due to cash variance or mistake.
        """
        user = request.user
        handover = ShiftHandover.objects.filter(id=handover_id, to_user=user, status=ShiftHandover.Status.PENDING).first()
        if not handover:
            return Response({
                'success': False,
                'message': 'No pending handover found matching this ID for your user account.'
            }, status=status.HTTP_404_NOT_FOUND)

        reason = request.data.get('reason', '').strip()
        if not reason:
            return Response({
                'success': False,
                'message': 'A rejection reason (e.g. cash discrepancy explanation) is mandatory.'
            }, status=status.HTTP_400_BAD_REQUEST)

        handover.status = ShiftHandover.Status.REJECTED
        handover.rejection_reason = reason
        handover.updated_by = user
        handover.save()

        if handover.from_shift:
            log_shift_action(
                handover.from_shift,
                user,
                'HANDOVER_REJECTED',
                f'Handover of ₹{handover.amount:.2f} was REJECTED by {user.get_full_name() or user.username}. Reason: {reason}',
                {'handover_id': handover.id, 'rejected_by': user.username, 'reason': reason}
            )

        return Response({
            'success': True,
            'message': 'Handover has been rejected.',
            'handover': ShiftHandoverSerializer(handover).data
        })

    @action(detail=True, methods=['put', 'patch'], url_path=r'expenses/(?P<expense_id>\d+)')
    @transaction.atomic
    def update_expense(self, request, pk=None, expense_id=None):
        shift = self.get_object()
        user = request.user
        expense = get_object_or_404(ShiftExpense, id=expense_id, shift=shift)

        amount = request.data.get('amount')
        description = request.data.get('description')
        category = request.data.get('category')

        if amount is not None:
            expense.amount = Decimal(str(amount))
        if description is not None:
            expense.description = description
        if category is not None:
            expense.category = category
        if request.FILES.get('receipt'):
            expense.receipt = request.FILES.get('receipt')

        expense.updated_by = user
        expense.save()

        fin = calculate_shift_financials(shift)
        shift.expected_cash = Decimal(str(fin['expected_cash']))
        shift.updated_by = user
        shift.save()

        log_shift_action(
            shift,
            user,
            'EXPENSE_UPDATED',
            f'Expense #{expense.id} updated by {user.get_full_name() or user.username}: ₹{expense.amount:.2f} ({expense.description})',
            {'expense_id': expense.id, 'amount': float(expense.amount)}
        )

        return Response({
            'success': True,
            'message': 'Expense updated successfully.',
            'data': ShiftExpenseSerializer(expense).data,
            'financials': fin
        })

    @action(detail=True, methods=['put', 'patch'], url_path=r'adjustments/(?P<adjustment_id>\d+)')
    @transaction.atomic
    def update_adjustment(self, request, pk=None, adjustment_id=None):
        shift = self.get_object()
        user = request.user
        adjustment = get_object_or_404(ShiftCashAdjustment, id=adjustment_id, shift=shift)

        amount = request.data.get('amount')
        reason = request.data.get('reason')
        notes = request.data.get('notes')
        adj_type = request.data.get('adjustment_type')

        if amount is not None:
            adjustment.amount = Decimal(str(amount))
        if reason is not None:
            adjustment.reason = reason
        if notes is not None:
            adjustment.notes = notes
        if adj_type is not None:
            adjustment.adjustment_type = adj_type

        adjustment.updated_by = user
        adjustment.save()

        fin = calculate_shift_financials(shift)
        shift.expected_cash = Decimal(str(fin['expected_cash']))
        shift.updated_by = user
        shift.save()

        log_shift_action(
            shift,
            user,
            'CASH_ADJUSTMENT_UPDATED',
            f'Cash adjustment #{adjustment.id} updated by {user.get_full_name() or user.username}: ₹{adjustment.amount:.2f} ({adjustment.reason})',
            {'adjustment_id': adjustment.id, 'amount': float(adjustment.amount)}
        )

        return Response({
            'success': True,
            'message': 'Adjustment updated successfully.',
            'data': ShiftCashAdjustmentSerializer(adjustment).data,
            'financials': fin
        })

    @action(detail=False, methods=['get'])
    def cash_drawers(self, request):
        """
        Returns all active physical cash drawers with live occupancy and default floats.
        """
        user_prop = self.get_property_for_request()
        ensure_default_drawers(prop=user_prop)
        drawers = CashDrawer.objects.filter(property=user_prop, is_active=True) if user_prop else CashDrawer.objects.filter(is_active=True)
        return Response({
            'success': True,
            'data': CashDrawerSerializer(drawers, many=True).data
        })

    @action(detail=False, methods=['get'])
    def summary_stats(self, request):
        """
        Executive live summary stats for dashboard and managers.
        """
        today = datetime.date.today()
        base_qs = self.get_queryset()
        active_shifts = base_qs.filter(status__in=[Shift.Status.OPEN, Shift.Status.CLOSING]).select_related('user', 'cash_drawer')
        pending_approvals = base_qs.filter(status=Shift.Status.PENDING_APPROVAL)
        
        today_shifts = base_qs.filter(opened_at__date=today)
        user_prop = self.get_property_for_request()
        pay_qs = Payment.objects.filter(property=user_prop) if user_prop else Payment.objects.all()
        today_cash_in = pay_qs.filter(payment_date__date=today, payment_method='CASH').aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        # Compute Station / Cash Drawer live balances
        drawers = CashDrawer.objects.filter(property=user_prop, is_active=True) if user_prop else CashDrawer.objects.filter(is_active=True)
        station_balances = []
        for d in drawers:
            active_shift = active_shifts.filter(cash_drawer=d).first()
            fin = calculate_shift_financials(active_shift) if active_shift else None
            station_balances.append({
                'id': d.id,
                'name': d.name,
                'code': d.code,
                'location': d.location,
                'is_in_use': bool(active_shift),
                'current_cashier': active_shift.user.get_full_name() or active_shift.user.username if active_shift and active_shift.user else None,
                'shift_number': active_shift.shift_number if active_shift else None,
                'shift_id': active_shift.id if active_shift else None,
                'expected_cash': fin['expected_cash'] if fin else float(d.default_float),
                'default_float': float(d.default_float)
            })

        return Response({
            'active_shifts_count': active_shifts.count(),
            'pending_approvals_count': pending_approvals.count(),
            'today_shifts_count': today_shifts.count(),
            'today_cash_collected': float(today_cash_in),
            'active_shifts': ShiftSerializer(active_shifts, many=True).data,
            'station_balances': station_balances
        })
