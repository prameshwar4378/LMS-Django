from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q
from .models import Customer, CustomerDocument
from .serializers import CustomerSerializer, CustomerHistorySerializer, CustomerDocumentSerializer

class CustomerViewSet(viewsets.ModelViewSet):
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
        serializer = CustomerHistorySerializer(customer)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def search(self, request):
        query = request.query_params.get('q', '').strip()
        if not query:
            return Response([])
        
        customers = Customer.objects.filter(
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

class CustomerDocumentViewSet(viewsets.ModelViewSet):
    queryset = CustomerDocument.objects.all().order_by('-created_at')
    serializer_class = CustomerDocumentSerializer
    permission_classes = [permissions.IsAuthenticated]
