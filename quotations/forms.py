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
            'special_instructions', 'trade_type', 'base_amount', 'rate_per_kg',
            'surcharge', 'discount', 'tax_rate', 'valid_until'
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ('base_amount', 'rate_per_kg', 'surcharge', 'discount', 'tax_rate'):
            if name in self.fields:
                self.fields[name].required = False
        if 'trade_type' in self.fields:
            self.fields['trade_type'].required = False
            from operations.policy import currency_for_scope
            self.fields['trade_type'].help_text = f"New local quotations use {currency_for_scope('local')}; international quotations use {currency_for_scope('international')}. Existing quotation currency is retained unless scope changes."
        if 'valid_until' in self.fields:
            self.fields['valid_until'].widget = forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
        if self.instance.pk:
            self.fields['record_version'] = forms.IntegerField(min_value=0, initial=self.instance.version, widget=forms.HiddenInput)

    def clean(self):
        data = super().clean()
        if 'trade_type' in self.fields:
            data['trade_type'] = data.get('trade_type') or 'local'
        for name in ('base_amount', 'rate_per_kg', 'surcharge', 'discount', 'tax_rate'):
            if name in self.fields and data.get(name) is None:
                data[name] = 0
        return data

    def clean_weight(self):
        weight = self.cleaned_data.get('weight')
        if weight is not None and weight <= 0:
            raise forms.ValidationError("Weight must be greater than 0.")
        return weight

    def clean_cargo_value(self):
        cargo_value = self.cleaned_data.get('cargo_value')
        if cargo_value and cargo_value < 0:
            raise forms.ValidationError("Cargo value cannot be negative.")
        return cargo_value



class PublicQuoteForm(QuoteForm):
    """Validate anonymous requests without exposing customer IDs or approval status."""
    full_name = forms.CharField(max_length=255, label="Full name")
    company_name = forms.CharField(max_length=255, required=False, label="Company name")
    email = forms.EmailField(max_length=254)
    phone = forms.CharField(max_length=20)

    class Meta(QuoteForm.Meta):
        fields = [
            "full_name", "company_name", "email", "phone",
            "pickup_location", "destination", "transport_mode", "trade_type",
            "cargo_description", "weight", "special_instructions",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"

    def clean_email(self):
        return self.cleaned_data["email"].lower()
