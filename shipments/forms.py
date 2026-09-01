from django import forms
from .models import Shipment


class ShipmentForm(forms.ModelForm):
    """
    Form for creating and updating shipments.
    """
    
    class Meta:
        model = Shipment
        fields = ['quote', 'carrier', 'current_location', 'estimated_delivery', 'status']
        widgets = {
            'quote': forms.Select(attrs={
                'class': 'form-control',
                'required': True
            }),
            'carrier': forms.Select(attrs={
                'class': 'form-control'
            }),
            'current_location': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Current shipment location'
            }),
            'estimated_delivery': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'status': forms.Select(attrs={
                'class': 'form-control',
                'required': True
            }),
        }
    
    def clean_estimated_delivery(self):
        from datetime import date
        estimated_delivery = self.cleaned_data.get('estimated_delivery')
        if estimated_delivery and estimated_delivery < date.today():
            raise forms.ValidationError(
                "Estimated delivery date cannot be in the past."
            )
        return estimated_delivery
