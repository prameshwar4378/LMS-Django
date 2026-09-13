from django import forms
from .models import LandingInquiry
from .security import verify_captcha

class LandingInquiryForm(forms.ModelForm):
    # Honeypot trap: invisible to humans, auto-filled by automated bot scrapers
    website_hp = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'style': 'position: absolute; left: -9999px; width: 1px; height: 1px; opacity: 0; pointer-events: none;',
            'tabindex': '-1',
            'autocomplete': 'off'
        })
    )

    # Cryptographically signed challenge token (tamper-proof)
    captcha_token = forms.CharField(
        required=True,
        widget=forms.HiddenInput(attrs={'id': 'id_captcha_token'})
    )

    # User's solution to the arithmetic challenge
    captcha_answer = forms.CharField(
        label="Security Verification",
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control font-monospace',
            'placeholder': 'Enter result',
            'autocomplete': 'off',
            'required': 'required'
        })
    )

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

    def clean(self):
        cleaned_data = super().clean()
        
        # 1. Honeypot check: If filled, reject automated bot
        if cleaned_data.get('website_hp'):
            self.add_error(None, "Automated spam submission detected.")
            self.add_error('captcha_answer', "Automated spam submission detected.")

        # 2. Cryptographic CAPTCHA verification
        captcha_answer = cleaned_data.get('captcha_answer')
        captcha_token = cleaned_data.get('captcha_token')

        if captcha_answer is not None and captcha_token:
            try:
                verify_captcha(captcha_answer, captcha_token)
            except forms.ValidationError as e:
                self.add_error('captcha_answer', e)

        return cleaned_data
