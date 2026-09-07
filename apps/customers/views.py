from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import transaction, IntegrityError
from django.db.models import Q
from .models import Customer, CustomerDocument
from .serializers import CustomerSerializer, CustomerHistorySerializer, CustomerDocumentSerializer
from apps.settings_app.tenant_views import TenantScopedViewSetMixin
from apps.billing.services import generate_unique_payment_number

class CustomerViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Customer.objects.all().prefetch_related('documents').order_by('-created_at')
    serializer_class = CustomerSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
        query = self.request.query_params.get('search', None)
        if query:
            queryset = queryset.filter(
                Q(first_name__icontains=query) |
                Q(middle_name__icontains=query) |
                Q(last_name__icontains=query) |
                Q(mobile__icontains=query) |
                Q(id_number__icontains=query) |
                Q(email__icontains=query)
            )
        return queryset

    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        customer = self.get_object()
        serializer = CustomerHistorySerializer(customer, context={'request': request})
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def search(self, request):
        query = request.query_params.get('q', '').strip()
        if not query:
            return Response([])
        
        customers = self.get_queryset().filter(
            Q(first_name__icontains=query) |
            Q(middle_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(mobile__icontains=query) |
            Q(id_number__icontains=query) |
            Q(bookings__booking_number__icontains=query) |
            Q(stays__room__room_number__icontains=query)
        ).distinct()[:15]

        serializer = self.get_serializer(customers, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def wallets(self, request):
        """
        Returns all customer wallets having an available advance balance or pending dues.
        Strictly excludes zero-balance and negative-amount customers.
        Supports search and tab filtering ('all', 'credit_available', 'pending_dues').
        """
        from apps.billing.services import calculate_stay_bill
        from apps.stays.models import Stay

        queryset = self.get_queryset()
        search_query = request.query_params.get('search', '').strip()
        tab_filter = request.query_params.get('tab', 'all').strip().lower()

        if search_query:
            queryset = queryset.filter(
                Q(first_name__icontains=search_query) |
                Q(middle_name__icontains=search_query) |
                Q(last_name__icontains=search_query) |
                Q(mobile__icontains=search_query) |
                Q(id_number__icontains=search_query) |
                Q(email__icontains=search_query)
            ).distinct()

        customers = list(queryset.prefetch_related(
            'stays',
            'stays__room',
            'stays__extra_charges',
            'stays__payments',
            'payments'
        ))

        active_wallets = []
        total_credit_held = 0.0
        total_pending_dues = 0.0
        count_credit_customers = 0
        count_dues_customers = 0

        for cust in customers:
            adv_credit = float(cust.advance_credit or 0)
            stay_credits = 0.0
            pending_dues = 0.0
            active_stays_count = 0

            for stay in cust.stays.all():
                if stay.status == Stay.Status.CHECKED_IN:
                    active_stays_count += 1
                bill = calculate_stay_bill(stay)
                bal = float(bill.get('balance', 0))
                if bal < -0.01:
                    stay_credits += abs(bal)
                elif bal > 0.01:
                    pending_dues += bal

            total_available_credit = round(adv_credit + stay_credits, 2)
            pending_dues = round(pending_dues, 2)
            net_balance = round(total_available_credit - pending_dues, 2)

            # Strict Filtering: Exclude zero-balance and negative customers
            has_credit = total_available_credit > 0.01
            has_dues = pending_dues > 0.01

            if not has_credit and not has_dues:
                continue

            if has_credit:
                total_credit_held += total_available_credit
                count_credit_customers += 1
            if has_dues:
                total_pending_dues += pending_dues
                count_dues_customers += 1

            # Apply tab filter
            if tab_filter in ['credit_available', 'advance', 'credit'] and not has_credit:
                continue
            elif tab_filter in ['pending_dues', 'pending', 'dues'] and not has_dues:
                continue

            # Latest transaction summary
            last_pay = cust.payments.order_by('-payment_date', '-id').first()
            last_tx = None
            if last_pay:
                last_tx = {
                    'payment_number': last_pay.payment_number,
                    'amount': float(last_pay.amount),
                    'payment_method': last_pay.payment_method,
                    'payment_date': last_pay.payment_date,
                    'reference': last_pay.transaction_reference or '',
                    'notes': last_pay.notes or ''
                }

            full_name = f"{cust.first_name} {cust.middle_name or ''} {cust.last_name or ''}".replace('  ', ' ').strip() or cust.first_name or "Guest"

            active_wallets.append({
                'id': cust.id,
                'full_name': full_name,
                'first_name': cust.first_name,
                'last_name': cust.last_name,
                'mobile': cust.mobile,
                'email': cust.email or '',
                'id_type': cust.id_type or '',
                'id_number': cust.id_number or '',
                'city': cust.city or '',
                'state': cust.state or '',
                'advance_credit': adv_credit,
                'stay_credits': stay_credits,
                'total_available_credit': total_available_credit,
                'pending_dues': pending_dues,
                'net_balance': net_balance,
                'has_credit': has_credit,
                'has_dues': has_dues,
                'status': 'CREDIT_AVAILABLE' if has_credit and not has_dues else ('DUES_PENDING' if has_dues and not has_credit else 'PARTIALLY_SETTLED'),
                'total_stays_count': cust.stays.count(),
                'active_stays_count': active_stays_count,
                'last_transaction': last_tx,
            })

        # Sort active wallets: highest available credit first, then highest dues
        active_wallets.sort(key=lambda w: (w['total_available_credit'], w['pending_dues']), reverse=True)

        return Response({
            'success': True,
            'summary': {
                'total_active_wallets': len(active_wallets),
                'total_advance_credit_held': round(total_credit_held, 2),
                'total_customers_with_credit': count_credit_customers,
                'total_pending_dues': round(total_pending_dues, 2),
                'total_customers_with_dues': count_dues_customers,
                'net_position': round(total_credit_held - total_pending_dues, 2),
            },
            'results': active_wallets
        })

    @action(detail=True, methods=['post'])
    def upload_document(self, request, pk=None):
        customer = self.get_object()
        doc_file = request.FILES.get('document_file')
        title = request.data.get('title', 'Additional Document')
        if not doc_file:
            return Response({'error': 'document_file is required.'}, status=status.HTTP_400_BAD_REQUEST)

        doc = CustomerDocument.objects.create(
            customer=customer,
            title=title,
            document_file=doc_file
        )
        return Response(CustomerDocumentSerializer(doc).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['delete'])
    def remove_photo(self, request, pk=None):
        customer = self.get_object()
        if customer.photo:
            customer.photo.delete(save=False)
            customer.photo = None
            customer.save()
        return Response(CustomerSerializer(customer).data)

    @action(detail=True, methods=['delete'])
    def remove_id_front(self, request, pk=None):
        customer = self.get_object()
        if customer.id_document:
            customer.id_document.delete(save=False)
            customer.id_document = None
            customer.save()
        return Response(CustomerSerializer(customer).data)

    @action(detail=True, methods=['delete'])
    def remove_id_back(self, request, pk=None):
        customer = self.get_object()
        if customer.id_document_back:
            customer.id_document_back.delete(save=False)
            customer.id_document_back = None
            customer.save()
        return Response(CustomerSerializer(customer).data)

    @action(detail=True, methods=['post'])
    def record_payment(self, request, pk=None):
        """
        Record lump-sum payment for a customer and automatically allocate
        the payment across all their pending stays in FIFO order (oldest stay first).
        """
        from django.db import transaction
        from apps.stays.models import Stay
        from apps.billing.models import Payment
        from apps.billing.services import calculate_stay_bill
        import datetime, uuid

        customer = self.get_object()
        try:
            amount_to_pay = float(request.data.get('amount', 0))
        except (ValueError, TypeError):
            amount_to_pay = 0.0

        payment_method = request.data.get('payment_method', 'CASH')
        transaction_reference = request.data.get('transaction_reference', '')
        notes = request.data.get('notes', 'Customer Bulk Balance Settlement')

        if amount_to_pay <= 0:
            return Response({
                'success': False,
                'message': 'Payment amount must be greater than zero.',
                'errors': {'amount': ['Must be greater than 0']}
            }, status=status.HTTP_400_BAD_REQUEST)

        is_wallet_payment = (payment_method == 'WALLET') or (request.data.get('use_wallet_credit') in [True, 'true', 'True'])
        
        cust_prop = getattr(customer, 'property', None)
        stays = Stay.objects.filter(property=cust_prop, primary_customer=customer).order_by('check_in_date', 'id') if cust_prop else Stay.objects.filter(primary_customer=customer).order_by('check_in_date', 'id')
        stay_credits = 0.0
        overpaid_stays = []
        for s in stays:
            bill = calculate_stay_bill(s)
            bal = float(bill.get('balance', 0))
            if bal < 0:
                credit_amt = abs(bal)
                overpaid_stays.append({'stay': s, 'credit': credit_amt})
                stay_credits += credit_amt

        total_wallet_available = float(customer.advance_credit or 0) + stay_credits

        if is_wallet_payment:
            if total_wallet_available < amount_to_pay:
                return Response({
                    'success': False,
                    'message': f'Insufficient wallet balance. Guest has ₹{total_wallet_available:.2f} available in wallet credit.',
                    'errors': {'amount': ['Insufficient wallet balance']}
                }, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            if is_wallet_payment:
                from decimal import Decimal
                remaining_to_deduct = amount_to_pay

                # 1. Deduct from customer.advance_credit first if available
                adv_credit_float = float(customer.advance_credit or 0)
                if adv_credit_float > 0:
                    deduct_adv = min(adv_credit_float, remaining_to_deduct)
                    customer.advance_credit -= Decimal(str(deduct_adv))
                    customer.save()
                    remaining_to_deduct -= deduct_adv

                # 2. Deduct remaining from overpaid stays by creating negative adjustment payments
                if remaining_to_deduct > 0:
                    for item in overpaid_stays:
                        if remaining_to_deduct <= 0:
                            break
                        st = item['stay']
                        st_credit = item['credit']
                        draw_amt = min(st_credit, remaining_to_deduct)

                        for _ in range(10):
                            payment_number = generate_unique_payment_number("PAY-")
                            try:
                                with transaction.atomic():
                                    Payment.objects.create(
                                        property=cust_prop,
                                        payment_number=payment_number,
                                        stay=st,
                                        amount=-Decimal(str(draw_amt)),
                                        payment_method='OTHER',
                                        transaction_reference='WALLET_TRANSFER_OUT',
                                        received_by=request.user if request.user and request.user.is_authenticated else None,
                                        notes=f'Wallet credit transfer of ₹{draw_amt:.2f} to settle customer stay dues'
                                    )
                                break
                            except IntegrityError:
                                continue
                        remaining_to_deduct -= draw_amt

                payment_method = 'OTHER'
                transaction_reference = transaction_reference or 'Guest Wallet Credit Settlement'
            
            pending_stays = []
            total_customer_balance = 0.0

            is_direct_wallet_deposit = request.data.get('direct_wallet_deposit') in [True, 'true', 'True']

            if not is_direct_wallet_deposit:
                for stay in stays:
                    bill = calculate_stay_bill(stay)
                    bal = float(bill.get('balance', 0))
                    if bal > 0:
                        pending_stays.append({
                            'stay': stay,
                            'balance': bal
                        })
                        total_customer_balance += bal

            remaining_payment = amount_to_pay
            payments_created = []

            for item in pending_stays:
                if remaining_payment <= 0:
                    break
                stay = item['stay']
                stay_bal = item['balance']

                alloc_amount = min(remaining_payment, stay_bal)

                pay = None
                for _ in range(10):
                    payment_number = generate_unique_payment_number("PAY-")
                    try:
                        with transaction.atomic():
                            pay = Payment.objects.create(
                                property=cust_prop,
                                payment_number=payment_number,
                                stay=stay,
                                amount=alloc_amount,
                                payment_method=payment_method,
                                transaction_reference=transaction_reference or f'Customer Settlement — Stay #{stay.stay_number}',
                                received_by=request.user if request.user and request.user.is_authenticated else None,
                                notes=f"{notes} (Allocated {alloc_amount:.2f} to Stay #{stay.stay_number})"
                            )
                        break
                    except IntegrityError:
                        continue

                if pay:
                    payments_created.append({
                        'payment_number': pay.payment_number,
                        'stay_number': stay.stay_number,
                        'allocated_amount': alloc_amount
                    })

                remaining_payment -= alloc_amount

            # Save any unallocated excess amount directly into customer advance credit wallet and log transaction
            if remaining_payment > 0:
                from decimal import Decimal
                customer.advance_credit += Decimal(str(remaining_payment))
                customer.save()

                adv_pay = None
                for _ in range(10):
                    payment_number = generate_unique_payment_number("PAY-")
                    try:
                        with transaction.atomic():
                            adv_pay = Payment.objects.create(
                                property=cust_prop,
                                payment_number=payment_number,
                                customer=customer,
                                stay=None,
                                amount=remaining_payment,
                                payment_method=payment_method,
                                transaction_reference=transaction_reference or 'CUSTOMER_ADVANCE_DEPOSIT',
                                received_by=request.user if request.user and request.user.is_authenticated else None,
                                notes=f"{notes} (Advance Wallet Deposit)" if notes else "Direct Customer Advance Wallet Deposit"
                            )
                        break
                    except IntegrityError:
                        continue

                if adv_pay:
                    payments_created.append({
                        'payment_number': adv_pay.payment_number,
                        'stay_number': 'Wallet Deposit',
                        'allocated_amount': remaining_payment
                    })

        msg = f"Successfully recorded payment of ₹{amount_to_pay:.2f}."
        if payments_created:
            msg += f" Allocated across {len(payments_created)} stay(s)."
        if remaining_payment > 0:
            msg += f" ₹{remaining_payment:.2f} stored in guest Advance Credit Wallet."

        return Response({
            'success': True,
            'message': msg,
            'data': {
                'total_paid': amount_to_pay,
                'allocated_payments': payments_created,
                'advance_credit_stored': max(0, remaining_payment),
                'new_advance_credit_balance': float(customer.advance_credit)
            }
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def refund_credit(self, request, pk=None):
        from django.db import transaction
        from apps.stays.models import Stay
        from apps.billing.models import Payment
        from apps.billing.services import calculate_stay_bill
        from decimal import Decimal
        import datetime, uuid

        customer = self.get_object()
        try:
            refund_amount = float(request.data.get('amount', 0))
        except (ValueError, TypeError):
            refund_amount = 0.0

        payment_method = request.data.get('payment_method', 'CASH')
        transaction_reference = request.data.get('transaction_reference', '')
        notes = request.data.get('notes', 'Return / Refund of Guest Advance Credit Balance')

        if refund_amount <= 0:
            return Response({
                'success': False,
                'message': 'Refund amount must be greater than zero.',
                'errors': {'amount': ['Must be greater than 0']}
            }, status=status.HTTP_400_BAD_REQUEST)

        # Calculate total available wallet credit (advance credit + stay overpayments)
        stays = Stay.objects.filter(primary_customer=customer).order_by('check_in_date', 'id')
        stay_credits = 0.0
        overpaid_stays = []
        for s in stays:
            bill = calculate_stay_bill(s)
            bal = float(bill.get('balance', 0))
            if bal < 0:
                credit_amt = abs(bal)
                overpaid_stays.append({'stay': s, 'credit': credit_amt})
                stay_credits += credit_amt

        total_wallet_available = float(customer.advance_credit or 0) + stay_credits

        if refund_amount > total_wallet_available + 0.001:
            return Response({
                'success': False,
                'message': f'Cannot refund ₹{refund_amount:.2f}. Total available wallet credit is ₹{total_wallet_available:.2f}.',
                'errors': {'amount': [f'Amount exceeds available credit (₹{total_wallet_available:.2f})']}
            }, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            remaining_refund = refund_amount

            # 1. Deduct from customer.advance_credit first if available
            adv_credit_float = float(customer.advance_credit or 0)
            if adv_credit_float > 0:
                deduct_adv = min(adv_credit_float, remaining_refund)
                customer.advance_credit -= Decimal(str(deduct_adv))
                customer.save()
                
                # Log negative payment transaction for the refund
                for _ in range(10):
                    payment_number = generate_unique_payment_number("PAY-")
                    try:
                        with transaction.atomic():
                            Payment.objects.create(
                                payment_number=payment_number,
                                customer=customer,
                                stay=None,
                                amount=-Decimal(str(deduct_adv)),
                                payment_method=payment_method,
                                transaction_reference=transaction_reference or 'WALLET_CREDIT_REFUND',
                                received_by=request.user if request.user and request.user.is_authenticated else None,
                                notes=f"{notes} (Refunded ₹{deduct_adv:.2f} to guest via {payment_method})"
                            )
                        break
                    except IntegrityError:
                        continue
                remaining_refund -= deduct_adv

            # 2. If additional refund required, draw from overpaid stays
            if remaining_refund > 0:
                for item in overpaid_stays:
                    if remaining_refund <= 0:
                        break
                    st = item['stay']
                    st_credit = item['credit']
                    draw_amt = min(st_credit, remaining_refund)

                    for _ in range(10):
                        payment_number = generate_unique_payment_number("PAY-")
                        try:
                            with transaction.atomic():
                                Payment.objects.create(
                                    payment_number=payment_number,
                                    customer=customer,
                                    stay=st,
                                    amount=-Decimal(str(draw_amt)),
                                    payment_method=payment_method,
                                    transaction_reference=transaction_reference or 'STAY_OVERPAYMENT_REFUND',
                                    received_by=request.user if request.user and request.user.is_authenticated else None,
                                    notes=f"{notes} (Refunded ₹{draw_amt:.2f} stay overpayment to guest via {payment_method})"
                                )
                            break
                        except IntegrityError:
                            continue
                    remaining_refund -= draw_amt

        return Response({
            'success': True,
            'message': f'Successfully refunded ₹{refund_amount:.2f} to guest via {payment_method}.',
            'data': {
                'refunded_amount': refund_amount,
                'payment_method': payment_method,
                'remaining_wallet_credit': max(0.0, total_wallet_available - refund_amount)
            }
        }, status=status.HTTP_200_OK)

class CustomerDocumentViewSet(viewsets.ModelViewSet):
    queryset = CustomerDocument.objects.all().order_by('-created_at')
    serializer_class = CustomerDocumentSerializer
    permission_classes = [permissions.IsAuthenticated]
