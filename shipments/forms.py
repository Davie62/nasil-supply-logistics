from django import forms
from django.utils import timezone
from core.business_rules import SHIPMENT_TRANSITIONS
from quotations.models import Quote
from .models import Shipment


class ShipmentForm(forms.ModelForm):
    reason = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}), help_text="Required when cancelling a shipment.")

    class Meta:
        model = Shipment
        fields = ['quote', 'carrier', 'current_location', 'estimated_delivery', 'status']
        widgets = {'estimated_delivery': forms.DateInput(attrs={'type': 'date'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields['quote'].disabled = True
            self.fields['quote'].queryset = Quote.objects.filter(pk=self.instance.quote_id)
            allowed = SHIPMENT_TRANSITIONS.get(self.instance.status, set()) | {self.instance.status}
            self.fields['status'].choices = [(key, label) for key, label in Shipment.STATUS_CHOICES if key in allowed]
            self.fields['record_version'] = forms.IntegerField(min_value=0, initial=self.instance.version, widget=forms.HiddenInput)
        else:
            self.fields['quote'].queryset = Quote.objects.filter(status='approved', approved_at__isnull=False, approved_by__isnull=False, shipment__isnull=True, valid_until__gte=timezone.localdate())
            self.fields['status'].choices = [('pending', 'Pending')]
            self.fields['quote'].help_text = 'Only approved, unexpired quotations without a shipment can be converted.'
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'

    def clean_estimated_delivery(self):
        from .workflows import validate_delivery_date
        value = self.cleaned_data.get('estimated_delivery')
        validate_delivery_date(value, self.instance.estimated_delivery if self.instance.pk else None)
        return value
