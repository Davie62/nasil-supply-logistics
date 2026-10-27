import uuid
from django import forms
from operations.module_ui import ResourceForm, ActionForm
from operations.forms import StyledFormMixin
from .models import Payment, StatementLine

class PaymentForm(ResourceForm):
    idempotency_key = forms.CharField(max_length=150, widget=forms.HiddenInput)
    class Meta:
        model = Payment
        fields = ["invoice", "purchase_order", "amount", "currency", "method", "external_reference", "paid_at", "idempotency_key"]
        widgets = {"paid_at": forms.DateTimeInput(attrs={"type": "datetime-local"})}
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["method"].choices = [("bank", "Bank"), ("cash", "Cash")]
        if not self.is_bound:
            self.initial["idempotency_key"] = str(uuid.uuid4())

class ImportStatementForm(StyledFormMixin, forms.Form):
    number = forms.CharField(max_length=60, label="Bank statement reference")
    currency = forms.ChoiceField(choices=[("UGX", "UGX"), ("USD", "USD")])
    statement_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    opening_balance = forms.DecimalField(max_digits=15, decimal_places=2)
    closing_balance = forms.DecimalField(max_digits=15, decimal_places=2)
    csv_file = forms.FileField(help_text="UTF-8 CSV header: external_reference,amount,posted_date,description. Positive receipts; negative supplier payments. Max 2 MB / 1,000 lines.")

def match_form(reconciliation):
    class MatchForm(ActionForm):
        line = forms.ModelChoiceField(queryset=StatementLine.objects.filter(reconciliation=reconciliation, payment__isnull=True))
        payment = forms.ModelChoiceField(queryset=Payment.objects.filter(status="posted", statement_line__isnull=True, currency=reconciliation.currency))
    return MatchForm
