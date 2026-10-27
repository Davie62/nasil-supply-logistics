from django import forms
from operations.module_ui import ResourceForm, ActionForm
from orders.forms import LineForm
from .models import Supplier, ProcurementRequest, PurchaseOrder, PurchaseLine

class SupplierForm(ResourceForm):
    class Meta:
        model = Supplier
        fields = ["name", "registration_number", "email", "phone", "address", "is_active"]

class RequestForm(ResourceForm):
    class Meta:
        model = ProcurementRequest
        fields = ["purpose", "currency", "budget", "order"]

class PurchaseForm(ResourceForm):
    class Meta:
        model = PurchaseOrder
        fields = ["request", "supplier"]

class AuditForm(ActionForm):
    outcome = forms.ChoiceField(choices=[("pass", "Pass"), ("fail", "Fail")])
    valid_until = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    notes = forms.CharField(widget=forms.Textarea, max_length=2000)

class RequestTransitionForm(ActionForm):
    target = forms.ChoiceField(choices=ProcurementRequest._meta.get_field("status").choices)
    reason = forms.CharField(max_length=255, required=False)

class PurchaseTransitionForm(ActionForm):
    target = forms.ChoiceField(choices=[(code, label) for code, label in PurchaseOrder._meta.get_field("status").choices if code not in {"received", "partially_received"}])
    reason = forms.CharField(max_length=255, required=False)

def receipt_form(purchase):
    class ReceiptForm(ActionForm):
        line = forms.ModelChoiceField(queryset=PurchaseLine.objects.filter(purchase_order=purchase).select_related("stock__product"))
        quantity_value = forms.DecimalField(label="Received quantity", max_digits=15, decimal_places=3, min_value=.001)
        delivery_reference = forms.CharField(max_length=150, help_text="Unique receipt/delivery-note reference; retrying the same reference does not receive twice.")
    return ReceiptForm
