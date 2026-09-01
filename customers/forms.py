from django import forms
from .models import Customer


class CustomerForm(forms.ModelForm):
    """
    Form for creating and updating customer information.
    """
    
    class Meta:
        model = Customer
        fields = ['full_name', 'company_name', 'email', 'phone', 'address', 'city', 'country']
        widgets = {
            'full_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Customer full name',
                'required': True
            }),
            'company_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Company name (optional)'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'customer@example.com',
                'required': True
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '+256 700 123456',
                'required': True
            }),
            'address': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Street address',
                'rows': 3
            }),
            'city': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'City'
            }),
            'country': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Country'
            }),
        }
    
    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email:
            email = email.lower()
            # Check for duplicate email only if creating new customer
            if not self.instance.pk:
                if Customer.objects.filter(email=email).exists():
                    raise forms.ValidationError(
                        "A customer with this email address already exists."
                    )
        return email
