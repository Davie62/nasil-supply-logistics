from django import forms
from .models import Quote


class QuoteForm(forms.ModelForm):
    """
    Form for creating and updating quotations.
    """
    
    class Meta:
        model = Quote
        fields = [
            'customer', 'service', 'pickup_location', 'destination',
            'transport_mode', 'cargo_description', 'weight', 'cargo_value',
            'special_instructions'
        ]
        widgets = {
            'customer': forms.Select(attrs={
                'class': 'form-control',
                'required': True
            }),
            'service': forms.Select(attrs={
                'class': 'form-control'
            }),
            'pickup_location': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Pickup location',
                'required': True
            }),
            'destination': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Destination',
                'required': True
            }),
            'transport_mode': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Road, Air, Sea, Rail'
            }),
            'cargo_description': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Describe the cargo/goods',
                'rows': 4,
                'required': True
            }),
            'weight': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Weight in kg',
                'min': 0.01,
                'step': 0.01,
                'required': True
            }),
            'cargo_value': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Value in USD (optional)',
                'min': 0,
                'step': 0.01
            }),
            'special_instructions': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Any special handling instructions',
                'rows': 3
            }),
        }
    
    def clean_weight(self):
        weight = self.cleaned_data.get('weight')
        if weight and weight <= 0:
            raise forms.ValidationError("Weight must be greater than 0.")
        return weight
    
    def clean_cargo_value(self):
        cargo_value = self.cleaned_data.get('cargo_value')
        if cargo_value and cargo_value < 0:
            raise forms.ValidationError("Cargo value cannot be negative.")
        return cargo_value
