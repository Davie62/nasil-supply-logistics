from django import forms
from .models import Company, Branch


class CompanyForm(forms.ModelForm):
    """
    Form for creating and updating company information.
    """
    
    class Meta:
        model = Company
        fields = [
            'name', 'registration_number', 'tin', 'email', 'phone',
            'website', 'address', 'logo'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Company legal name',
                'required': True
            }),
            'registration_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Business registration number',
                'required': True
            }),
            'tin': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Tax Identification Number',
                'required': True
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'company@example.com',
                'required': True
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '+256 700 123456',
                'required': True
            }),
            'website': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://example.com'
            }),
            'address': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Physical address',
                'rows': 3,
                'required': True
            }),
            'logo': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*'
            }),
        }


class BranchForm(forms.ModelForm):
    """
    Form for creating and updating branch information.
    """
    
    class Meta:
        model = Branch
        fields = ['company', 'name', 'code', 'city', 'country', 'address', 'phone', 'email', 'is_active']
        widgets = {
            'company': forms.Select(attrs={
                'class': 'form-control',
                'required': True
            }),
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Branch name',
                'required': True
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Branch code (e.g., KLA, MBR)',
                'required': True
            }),
            'city': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'City',
                'required': True
            }),
            'country': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Country',
                'required': True
            }),
            'address': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Branch address',
                'rows': 3,
                'required': True
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '+256 700 123456',
                'required': True
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'branch@example.com',
                'required': True
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }
