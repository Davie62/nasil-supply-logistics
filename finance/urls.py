from decimal import Decimal
from django.urls import path
from django.db.models import F, Sum, Q, Value
from django.db.models.functions import Coalesce
from operations.module_ui import resource_urls, home_view, Action, ReasonForm, EmptyActionForm
from .models import Invoice, Payment, Reconciliation
from .forms import PaymentForm, match_form
from .services import save_payment, reverse_payment, match_payment, close_reconciliation
from .views import statement_import

app_name = "finance"
urlpatterns = [path("", home_view("Finance & reconciliation", [("Invoices", "finance:invoices_list", "finance.view_invoice"), ("Issue invoice", "staff_invoice_create", "payments.add_invoice"),
    ("Payments", "finance:payments_list", "finance.view_payment"), ("Bank reconciliation", "finance:reconciliations_list", "finance.view_reconciliation"),
    ("Import bank statement", "finance:statement_import", "finance.add_reconciliation")],
    lambda request: [("Issued invoices", Invoice.objects.filter(status="issued").count()), ("Posted payments", Payment.objects.filter(status="posted").count()), ("Open statements", Reconciliation.objects.filter(status="open").count())]), name="home"),
    path("import-statement/", statement_import, name="statement_import")]
urlpatterns += resource_urls(model=Invoice, slug="invoices", columns=["Invoice", "Quotation", "Currency", "Total", "Outstanding", "Status", "Due"], fields=["number", "quote", "currency", "amount", "outstanding", "get_status_display", "due_date"],
    search_fields=["number", "quote__customer__full_name"], select=["quote__customer"], entity="invoice",
    queryset=lambda: Invoice.objects.annotate(outstanding=F("amount")-Coalesce(Sum("finance_payments__amount", filter=Q(finance_payments__status="posted")), Value(Decimal("0.00")))),
    related=lambda obj: [{"title": "Invoice payments", "columns": ["Reference", "Amount", "Method", "Paid at", "Status"], "rows": obj.finance_payments.values_list("external_reference", "amount", "method", "paid_at", "status")[:100]}])
urlpatterns += resource_urls(model=Payment, slug="payments", form_class=PaymentForm, save=save_payment,
    columns=["Payment", "Invoice", "Purchase order", "Amount", "Currency", "Method", "External reference", "Status", "Paid at"], fields=["reference", "invoice", "purchase_order", "amount", "currency", "method", "external_reference", "get_status_display", "paid_at"],
    search_fields=["external_reference", "invoice__number", "purchase_order__number"], select=["invoice", "purchase_order"],
    actions={"reverse": Action("Reverse unreconciled payment", "finance.reverse_payment", lambda obj: ReasonForm, reverse_payment)})
urlpatterns += resource_urls(model=Reconciliation, slug="reconciliations", columns=["Statement", "Date", "Currency", "Opening", "Closing", "Status"], fields=["number", "statement_date", "currency", "opening_balance", "closing_balance", "get_status_display"], search_fields=["number"],
    actions={"match": Action("Match payment", "finance.change_reconciliation", match_form, match_payment), "close": Action("Close reconciliation", "finance.change_reconciliation", lambda obj: EmptyActionForm, close_reconciliation)},
    related=lambda obj: [{"title": "Statement reconciliation lines", "columns": ["Reference", "Amount", "Date", "Description", "Payment"], "rows": obj.lines.values_list("external_reference", "amount", "posted_date", "description", "payment__reference")[:100]}])
