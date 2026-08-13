from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.http import HttpResponse
from .models import ChargeType, ExtraCharge, Payment, Invoice
from .serializers import ChargeTypeSerializer, ExtraChargeSerializer, PaymentSerializer, InvoiceSerializer
from apps.stays.models import Stay
from apps.billing.services import calculate_stay_bill
from apps.settings_app.models import Settings

def is_admin_user(user):
    return user and (user.is_superuser or getattr(user, 'role', None) in ['SUPER_ADMIN', 'MANAGER'])

class ChargeTypeViewSet(viewsets.ModelViewSet):
    queryset = ChargeType.objects.all().order_by('name')
    serializer_class = ChargeTypeSerializer
    permission_classes = [permissions.IsAuthenticated]

class ExtraChargeViewSet(viewsets.ModelViewSet):
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
        instance = self.get_object()
        if instance.stay and instance.stay.status in ['CHECKED_OUT', 'COMPLETED'] and not is_admin_user(request.user):
            return Response({'error': 'Receptionists cannot delete extra charges from checked out stays. Admin rights required.'}, status=status.HTTP_403_FORBIDDEN)
        return super().destroy(request, *args, **kwargs)

class PaymentViewSet(viewsets.ModelViewSet):
    queryset = Payment.objects.all().select_related('stay', 'stay__room', 'stay__primary_customer', 'received_by').order_by('-payment_date')
    serializer_class = PaymentSerializer
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
                return Response({'error': 'Receptionists cannot record payments for checked out stays. Admin rights required.'}, status=status.HTTP_403_FORBIDDEN)
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.stay and instance.stay.status in ['CHECKED_OUT', 'COMPLETED'] and not is_admin_user(request.user):
            return Response({'error': 'Receptionists cannot modify payments of checked out stays. Admin rights required.'}, status=status.HTTP_403_FORBIDDEN)
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.stay and instance.stay.status in ['CHECKED_OUT', 'COMPLETED'] and not is_admin_user(request.user):
            return Response({'error': 'Receptionists cannot delete payments of checked out stays. Admin rights required.'}, status=status.HTTP_403_FORBIDDEN)
        return super().destroy(request, *args, **kwargs)

class InvoiceViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Invoice.objects.all().select_related('stay', 'stay__room', 'stay__primary_customer').order_by('-generated_at')
    serializer_class = InvoiceSerializer
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=['get'], url_path=r'by-stay/(?P<stay_id>\d+)')
    def by_stay(self, request, stay_id=None):
        stay = get_object_or_404(Stay, pk=stay_id)
        bill = calculate_stay_bill(stay)
        settings_obj = Settings.get_settings()
        
        # Check or generate invoice record
        invoice = getattr(stay, 'invoice', None)
        if not invoice:
            inv_number = f"{settings_obj.invoice_prefix or 'INV-'}{stay.stay_number.replace('STAY-', '')}"
            invoice, _ = Invoice.objects.get_or_create(
                stay=stay,
                defaults={
                    'invoice_number': inv_number,
                    'subtotal': bill['subtotal'],
                    'discount': bill['discount_amount'],
                    'tax': bill['tax_amount'],
                    'grand_total': bill['grand_total'],
                    'paid_amount': bill['total_paid'],
                    'balance': bill['balance'],
                }
            )

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
