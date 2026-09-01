from django import forms
from .models import Service, Carrier


class ServiceForm(forms.ModelForm):
    """
    Form for creating and updating services.
    """
    
    class Meta:
        model = Service
        fields = ['name', 'description', 'icon', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Service name',
                'required': True
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Service description',
                'rows': 4,
                'required': True
            }),
            'icon': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'CSS icon class (e.g., bi bi-truck)'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }


class CarrierForm(forms.ModelForm):
    """
    Form for creating and updating carriers/logistics partners.
    """
    
    class Meta:
        model = Carrier
        fields = ['name', 'contact_person', 'phone', 'email', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Carrier/Company name',
                'required': True
            }),
            'contact_person': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Contact person name'
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '+256 700 123456',
                'required': True
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'contact@carrier.com',
                'required': True
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }
    
    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email:
            email = email.lower()
        return email
