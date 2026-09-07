from django.db import models, transaction, IntegrityError
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.http import HttpResponse
from .models import ChargeType, ExtraCharge, Payment, Invoice
from .serializers import ChargeTypeSerializer, ExtraChargeSerializer, PaymentSerializer, InvoiceSerializer
from apps.stays.models import Stay
from apps.billing.services import calculate_stay_bill, generate_unique_invoice_number, generate_unique_payment_number
from apps.settings_app.models import Settings
from apps.settings_app.tenant_views import TenantScopedViewSetMixin

from apps.authentication.permissions import user_has_perm, require_perm

def is_admin_user(user):
    return user and (user.is_superuser or getattr(user, 'role', None) in ['SUPER_ADMIN', 'HOTEL_OWNER', 'MANAGER'])

class ChargeTypeViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = ChargeType.objects.all().order_by('name')
    serializer_class = ChargeTypeSerializer
    permission_classes = [permissions.IsAuthenticated]

class ExtraChargeViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = ExtraCharge.objects.all().select_related('stay', 'charge_type', 'created_by').order_by('-created_at')
    serializer_class = ExtraChargeSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
        stay_id = self.request.query_params.get('stay')
        if stay_id:
            queryset = queryset.filter(stay_id=stay_id)
        return queryset

    def create(self, request, *args, **kwargs):
        stay_id = request.data.get('stay')
        if stay_id:
            stay = Stay.objects.filter(id=stay_id).first()
            if stay and stay.status in ['CHECKED_OUT', 'COMPLETED'] and not is_admin_user(request.user):
                return Response({'error': 'Receptionists cannot add extra charges to checked out stays. Admin rights required.'}, status=status.HTTP_403_FORBIDDEN)
        return super().create(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        require_perm(request.user, 'billing', 'can_void', "You do not have permission to void extra charges.")
        instance = self.get_object()
        if instance.stay and instance.stay.status in ['CHECKED_OUT', 'COMPLETED'] and not is_admin_user(request.user):
            return Response({'error': 'Receptionists cannot delete extra charges from checked out stays. Admin rights required.'}, status=status.HTTP_403_FORBIDDEN)
        return super().destroy(request, *args, **kwargs)

class PaymentViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Payment.objects.all().select_related(
        'stay', 'stay__room', 'stay__primary_customer', 'customer', 'received_by', 'created_by', 'shift'
    ).order_by('-payment_date')
    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
        stay_id = self.request.query_params.get('stay')
        if stay_id:
            queryset = queryset.filter(stay_id=stay_id)

        customer_id = self.request.query_params.get('customer')
        if customer_id:
            queryset = queryset.filter(models.Q(customer_id=customer_id) | models.Q(stay__primary_customer_id=customer_id))

        method = self.request.query_params.get('method')
        if method and method != 'ALL':
            queryset = queryset.filter(payment_method__iexact=method)

        start_date = self.request.query_params.get('start_date')
        if start_date:
            queryset = queryset.filter(payment_date__date__gte=start_date)

        end_date = self.request.query_params.get('end_date')
        if end_date:
            queryset = queryset.filter(payment_date__date__lte=end_date)

        return queryset

    def create(self, request, *args, **kwargs):
        require_perm(request.user, 'billing', 'can_collect_payment', "You do not have permission to collect payments.")
        try:
            amt = float(request.data.get('amount') or 0)
            if amt < 0:
                require_perm(request.user, 'billing', 'can_refund', "You do not have permission to process payment refunds.")
        except (ValueError, TypeError):
            pass

        stay_id = request.data.get('stay')
        use_wallet = request.data.get('use_wallet_credit') in [True, 'true', 'True'] or request.data.get('payment_method') == 'WALLET'
        if stay_id:
            stay = Stay.objects.filter(id=stay_id).first()
            if stay and stay.status in ['CHECKED_OUT', 'COMPLETED'] and not is_admin_user(request.user):
                return Response({'error': 'Receptionists cannot record payments for checked out stays. Admin rights required.'}, status=status.HTTP_403_FORBIDDEN)


            if use_wallet and stay and stay.primary_customer:
                customer = stay.primary_customer
                try:
                    amount_val = float(request.data.get('amount') or 0)
                except (ValueError, TypeError):
                    amount_val = 0.0

                from apps.billing.services import calculate_stay_bill
                stay_credits = 0.0
                overpaid_stays = []
                for s in Stay.objects.filter(primary_customer=customer):
                    bill = calculate_stay_bill(s)
                    bal = float(bill.get('balance', 0))
                    if bal < 0:
                        credit_amt = abs(bal)
                        overpaid_stays.append({'stay': s, 'credit': credit_amt})
                        stay_credits += credit_amt

                total_wallet_available = float(customer.advance_credit or 0) + stay_credits

                if total_wallet_available < amount_val or amount_val <= 0:
                    return Response({
                        'error': f'Insufficient wallet credit balance. Available guest credit is ₹{total_wallet_available:.2f}.'
                    }, status=status.HTTP_400_BAD_REQUEST)

                # Deduct used wallet amount
                from decimal import Decimal
                remaining_to_deduct = amount_val

                adv_credit_float = float(customer.advance_credit or 0)
                if adv_credit_float > 0:
                    deduct_adv = min(adv_credit_float, remaining_to_deduct)
                    customer.advance_credit -= Decimal(str(deduct_adv))
                    customer.save()
                    remaining_to_deduct -= deduct_adv

                if remaining_to_deduct > 0:
                    import datetime, uuid
                    from apps.billing.models import Payment
                    today_str = datetime.date.today().strftime('%Y%m%d')
                    pay_prefix = "PAY-"
                    for item in overpaid_stays:
                        if remaining_to_deduct <= 0:
                            break
                        st = item['stay']
                        st_credit = item['credit']
                        draw_amt = min(st_credit, remaining_to_deduct)

                        payment_number = None
                        for attempt in range(50):
                            pay_count = Payment.objects.filter(payment_number__startswith=f"{pay_prefix}{today_str}").count() + 1 + attempt
                            p_num = f"{pay_prefix}{today_str}-{pay_count:03d}"
                            if not Payment.objects.filter(payment_number=p_num).exists():
                                payment_number = p_num
                                break
                        if not payment_number:
                            payment_number = f"{pay_prefix}{today_str}-{uuid.uuid4().hex[:4].upper()}"

                        Payment.objects.create(
                            payment_number=payment_number,
                            stay=st,
                            amount=-Decimal(str(draw_amt)),
                            payment_method='OTHER',
                            transaction_reference='WALLET_TRANSFER_OUT',
                            received_by=request.user if request.user and request.user.is_authenticated else None,
                            notes=f'Wallet credit transfer of ₹{draw_amt:.2f} to settle stay #{stay.stay_number} dues'
                        )
                        remaining_to_deduct -= draw_amt

                # Create a mutable copy of request data and apply mutations
                mutable_data = request.data.copy()
                if mutable_data.get('payment_method') == 'WALLET':
                    mutable_data['payment_method'] = 'OTHER'
                if not mutable_data.get('transaction_reference'):
                    mutable_data['transaction_reference'] = 'CUSTOMER_WALLET_CREDIT'
                if not mutable_data.get('notes'):
                    mutable_data['notes'] = 'Paid using Guest Advance Credit Wallet'

                # Replace request data with the mutable copy
                request._full_data = mutable_data

        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        stay = serializer.validated_data.get('stay')
        customer = serializer.validated_data.get('customer')
        if not customer and stay and stay.primary_customer:
            customer = stay.primary_customer
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        
        from apps.shifts.services import get_active_shift_for_user, log_shift_action
        shift = get_active_shift_for_user(user) if user else None

        payment = serializer.save(
            customer=customer,
            received_by=user,
            created_by=user,
            updated_by=user,
            shift=shift
        )

        # Audit event if shift is active
        if shift:
            log_shift_action(
                shift,
                user,
                'PAYMENT_RECORDED',
                f'Payment #{payment.payment_number} of ₹{payment.amount:.2f} via {payment.get_payment_method_display()} recorded by {user.get_full_name() or user.username if user else "Staff"}',
                {'payment_id': payment.id, 'amount': float(payment.amount), 'method': payment.payment_method, 'user_id': user.id if user else None}
            )

    def perform_update(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        payment = serializer.save(updated_by=user)
        if payment.shift and user:
            from apps.shifts.services import log_shift_action
            log_shift_action(
                payment.shift,
                user,
                'PAYMENT_UPDATED',
                f'Payment #{payment.payment_number} updated by {user.get_full_name() or user.username} (Amount: ₹{payment.amount:.2f})',
                {'payment_id': payment.id, 'amount': float(payment.amount), 'method': payment.payment_method, 'updated_by_id': user.id}
            )

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.stay and instance.stay.status in ['CHECKED_OUT', 'COMPLETED'] and not is_admin_user(request.user):
            return Response({'error': 'Receptionists cannot modify payments of checked out stays. Admin rights required.'}, status=status.HTTP_403_FORBIDDEN)
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        require_perm(request.user, 'billing', 'can_refund', "You do not have permission to delete or refund recorded payments.")
        instance = self.get_object()
        if instance.stay and instance.stay.status in ['CHECKED_OUT', 'COMPLETED'] and not is_admin_user(request.user):
            return Response({'error': 'Receptionists cannot delete payments of checked out stays. Admin rights required.'}, status=status.HTTP_403_FORBIDDEN)
        return super().destroy(request, *args, **kwargs)


class InvoiceViewSet(TenantScopedViewSetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = Invoice.objects.all().select_related('stay', 'stay__room', 'stay__primary_customer').order_by('-generated_at')
    serializer_class = InvoiceSerializer
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=['get'], url_path=r'by-stay/(?P<stay_id>\d+)')
    def by_stay(self, request, stay_id=None):
        stay = get_object_or_404(Stay, pk=stay_id)
        prop = stay.property or self.get_property_for_request()
        settings_obj = Settings.get_settings(prop=prop)
        bill = calculate_stay_bill(stay)
        
        # Check or generate invoice record
        invoice = getattr(stay, 'invoice', None) or Invoice.objects.filter(stay=stay).first()
        if not invoice:
            if stay.status != Stay.Status.CHECKED_OUT and not stay.actual_checkout_date:
                return Response({
                    'detail': 'Invoice can only be generated after checkout is completed.'
                }, status=status.HTTP_400_BAD_REQUEST)

            inv_number = generate_unique_invoice_number(prop, settings_obj.invoice_prefix)
            for attempt in range(10):
                try:
                    with transaction.atomic():
                        invoice, _ = Invoice.objects.get_or_create(
                            stay=stay,
                            defaults={
                                'property': prop,
                                'invoice_number': inv_number,
                                'subtotal': bill.get('gross_subtotal', bill.get('subtotal', 0)),
                                'discount': bill.get('discount_amount', 0),
                                'tax': bill.get('gst_amount', bill.get('tax_amount', 0)),
                                'grand_total': bill.get('grand_total', 0),
                                'paid_amount': bill.get('total_paid', 0),
                                'balance': bill.get('balance', 0),
                            }
                        )
                    break
                except IntegrityError:
                    inv_number = generate_unique_invoice_number(prop, settings_obj.invoice_prefix)

        invoice_data = self.get_serializer(invoice).data
        return Response({
            'invoice': invoice_data,
            'bill': bill,
            'settings': {
                'lodge_name': settings_obj.lodge_name,
                'address': settings_obj.address,
                'phone': settings_obj.phone,
                'email': settings_obj.email,
                'website': settings_obj.website,
                'gst_number': settings_obj.gst_number,
                'currency': settings_obj.currency,
            },
            'stay_details': {
                'stay_number': stay.stay_number,
                'room_number': stay.room.room_number,
                'room_type': stay.room.room_type.name,
                'check_in_date': stay.check_in_date,
                'check_in_time': stay.check_in_time.strftime('%H:%M') if stay.check_in_time else '',
                'checkout_date': stay.actual_checkout_date or stay.expected_checkout_date,
                'checkout_time': stay.actual_checkout_time.strftime('%H:%M') if stay.actual_checkout_time else '',
                'customer_name': stay.primary_customer.full_name,
                'customer_mobile': stay.primary_customer.mobile,
                'customer_address': stay.primary_customer.address or '',
                'customer_id_type': stay.primary_customer.id_type,
                'customer_id_number': stay.primary_customer.id_number or '',
                'guests': [g.guest_name for g in stay.guests.all()],
                'extra_charges': [{'description': item.description, 'quantity': item.quantity, 'price': float(item.unit_price), 'amount': float(item.amount)} for item in stay.extra_charges.all()],
                'payments': [{'payment_number': p.payment_number, 'method': p.get_payment_method_display(), 'date': p.payment_date.strftime('%d/%m/%Y %I:%M %p') if p.payment_date else '', 'amount': float(p.amount)} for p in stay.payments.all()],
            }
        })
