from django import forms
from .models import LandingInquiry

class LandingInquiryForm(forms.ModelForm):
    class Meta:
        model = LandingInquiry
        fields = [
            'full_name',
            'property_name',
            'room_count',
            'phone',
            'email',
            'city',
            'service_interest',
            'message'
        ]
        widgets = {
            'full_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. Rajesh Sharma',
                'required': 'required'
            }),
            'property_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. Royal Palace Heritage Lodge',
                'required': 'required'
            }),
            'room_count': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. 24',
                'min': '1',
                'max': '2000'
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. 9876543210',
                'required': 'required',
                'type': 'tel'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. owner@royalpalace.com',
                'required': 'required'
            }),
            'city': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. Jaipur, Rajasthan'
            }),
            'service_interest': forms.Select(attrs={
                'class': 'form-select'
            }),
            'message': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Tell us about your property, current pain points, or specific questions...'
            }),
        }
