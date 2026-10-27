from django import forms
from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_GET
from core.permissions import staff_permission_required
from customers.models import Customer
from operations.forms import StyledFormMixin
from operations.querysets import paginate, search
from operations.views import detail, action
from payments.models import Invoice
from payments.services import issue_invoice, void_invoice
from quotations.models import Quote
from .models import CustomerAccess, PortalInvitation
from .security import private_response
from .services import invite_customer, invitation_token, set_access
from .views import invoice_pdf_response


@staff_permission_required("customer_services.manage_access", "customers.view_customer")
@require_http_methods(["GET", "POST"])
def manage_access(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    if request.method == "POST":
        try:
            operation = request.POST.get("action")
            if operation == "invite":
                invite_customer(actor=request.user, customer_id=pk)
                if settings.NOTIFICATIONS_DELIVERY_ENABLED:
                    messages.success(request, "Invitation created and queued. You can also copy the activation link below.")
                else:
                    messages.success(request, "Invitation created. Email delivery is disabled locally; copy the activation link below and open it in a private/incognito window.")
            elif operation in {"enable", "disable"}:
                if not CustomerAccess.objects.filter(customer=customer).exists():
                    raise ValidationError("No portal account exists for this customer.")
                set_access(actor=request.user, customer_id=pk, enabled=operation == "enable")
            else:
                raise ValidationError("Choose a valid access action.")
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
        return redirect("customer_portal_access", pk=pk)
    access = CustomerAccess.objects.select_related("user").filter(customer=customer).first()
    invitation = PortalInvitation.objects.filter(customer=customer, email__iexact=customer.email, accepted_at__isnull=True, revoked_at__isnull=True, expires_at__gt=timezone.now()).order_by("-pk").first()
    activation_path = reverse("portal_activate", args=[invitation_token(invitation)]) if invitation else ""
    return private_response(render(request, "portal/staff_access.html", {"title": "Customer portal access", "customer": customer, "access": access, "activation_path": activation_path, "invitation": invitation}))


class InvoiceForm(StyledFormMixin, forms.Form):
    quote = forms.ModelChoiceField(queryset=Quote.objects.filter(status="approved", approved_at__isnull=False, approved_by__isnull=False, invoice__isnull=True).select_related("customer"))
    due_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    customer_note = forms.CharField(max_length=2000, required=False, widget=forms.Textarea(attrs={"rows": 3}))


@staff_permission_required("payments.view_invoice")
@require_GET
def invoice_list(request):
    queryset = search(Invoice.objects.select_related("quote__customer"), request.GET.get("q"), ("number", "quote__customer__full_name"))
    page, context = paginate(request, queryset)
    return render(request, "dashboard/workflow_list.html", {"title": "Invoices", "eyebrow": "CUSTOMER BILLING", "description": "Issued invoice snapshots. Online payment collection is not enabled.",
        "columns": ["Invoice", "Customer", "Currency", "Total", "Status", "Due"], "status_column": 4,
        "rows": [{"values": [invoice.number, invoice.quote.customer.full_name, invoice.currency, invoice.amount, invoice.get_status_display(), invoice.due_date], "url": reverse("staff_invoice_detail", args=[invoice.pk])} for invoice in page],
        "create_url": "staff_invoice_create" if request.user.has_perm("payments.add_invoice") else None, "create_label": "Issue invoice", **context})


@staff_permission_required("payments.view_invoice", "payments.add_invoice", "quotations.view_quote")
@require_http_methods(["GET", "POST"])
def invoice_create(request):
    form = InvoiceForm(request.POST if request.method == "POST" else None)
    if form.is_valid():
        try:
            invoice = issue_invoice(actor=request.user, quote_id=form.cleaned_data["quote"].pk, due_date=form.cleaned_data["due_date"], customer_note=form.cleaned_data["customer_note"])
        except ValidationError as error:
            form.add_error(None, error.messages)
        else:
            return redirect("staff_invoice_detail", pk=invoice.pk)
    return render(request, "dashboard/workflow_form.html", {"title": "Issue customer invoice", "eyebrow": "Approved quotation snapshot · No payment collection", "form": form, "back_url": "staff_invoice_list"})


class VoidForm(StyledFormMixin, forms.Form):
    reason = forms.CharField(max_length=255)


@staff_permission_required("payments.view_invoice")
@require_http_methods(["GET", "POST"])
def invoice_detail(request, pk):
    invoice = get_object_or_404(Invoice.objects.select_related("quote__customer"), pk=pk)
    from operations.models import OperationsEvent
    from django.core.exceptions import PermissionDenied
    if request.method == "POST":
        if not request.user.has_perm("payments.change_invoice"):
            raise PermissionDenied
        try:
            void_invoice(actor=request.user, invoice_id=pk, reason=request.POST.get("reason", ""))
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
        return redirect("staff_invoice_detail", pk=pk)
    return detail(request, title=invoice.number, back_url="staff_invoice_list", actions=[action("staff_invoice_pdf", "Download invoice PDF", pk)],
        fields=[("Customer", invoice.quote.customer.full_name), ("Quotation", invoice.quote.quote_number), ("Status", invoice.get_status_display()), ("Currency", invoice.currency),
                ("Amount", invoice.amount), ("Due date", invoice.due_date), ("Issued", invoice.issued_at), ("Invoice reference", invoice.reference), ("Customer note", invoice.customer_note), ("Void reason", invoice.void_reason)],
        audit=OperationsEvent.objects.filter(entity_type="invoice", entity_id=str(pk)), void_form=VoidForm() if invoice.status == "issued" and request.user.has_perm("payments.change_invoice") else None)


@staff_permission_required("payments.view_invoice")
@require_GET
def invoice_pdf(request, pk):
    return invoice_pdf_response(get_object_or_404(Invoice, pk=pk), request.user)
