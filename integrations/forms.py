from django import forms
from operations.module_ui import ResourceForm, ActionForm
from .models import Connection

class ConnectionForm(ResourceForm):
    class Meta:
        model = Connection
        fields = ["name", "code", "kind", "base_url", "credential_env", "webhook_secret_env", "is_active"]

class DocumentForm(ActionForm):
    document_type = forms.ChoiceField(choices=[("invoice", "Invoice"), ("purchase_order", "Purchase order")])
    document_id = forms.IntegerField(min_value=1)

class IntentForm(forms.Form):
    invoice_id = forms.IntegerField(min_value=1)
    provider = forms.ChoiceField(choices=[("flutterwave", "Flutterwave"), ("pawapay", "pawaPay mobile money")])
    phone = forms.CharField(required=False, max_length=16)
    mobile_provider = forms.CharField(required=False, max_length=50)
