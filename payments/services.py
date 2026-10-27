import uuid
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from core.business_rules import require_permission, validate_convertible
from operations.services import managed_save, event
from quotations.models import Quote
from .models import Invoice


@transaction.atomic
def issue_invoice(*, actor, quote_id, due_date, customer_note=""):
    require_permission(actor, "payments.add_invoice", "quotations.view_quote")
    quote = Quote.objects.select_for_update().get(pk=quote_id)
    if hasattr(quote, "shipment"):
        if quote.status != "approved" or not quote.approved_at or not quote.approved_by_id or quote.total_amount <= 0:
            raise ValidationError("The booked quotation must have verified approval and pricing.")
    else:
        validate_convertible(quote)
    if due_date < timezone.localdate() or Invoice.objects.filter(quote=quote).exists():
        raise ValidationError("Choose a current due date and a quotation without an existing invoice.")
    invoice = Invoice(number="INV-" + uuid.uuid4().hex[:16].upper(), quote=quote, currency=quote.currency, amount=quote.total_amount,
                      due_date=due_date, customer_note=customer_note, issued_by=actor,
                      pricing={"customer_name": quote.customer.full_name, "company_name": quote.customer.company_name or "", "billing_email": quote.customer.email,
                               **{field: str(getattr(quote, field)) for field in ("base_amount", "weight", "rate_per_kg", "surcharge", "discount", "subtotal", "tax_rate", "tax_amount", "total_amount")}})
    invoice.full_clean()
    managed_save(invoice)
    event(actor, "invoice", invoice.pk, "invoice_issued", reference=str(invoice.reference), quote=quote.quote_number, amount=str(invoice.amount), currency=invoice.currency)
    return invoice


@transaction.atomic
def void_invoice(*, actor, invoice_id, reason):
    require_permission(actor, "payments.change_invoice")
    invoice = Invoice.objects.select_for_update().get(pk=invoice_id)
    if invoice.gateway_intents.filter(status__in=["created", "pending", "review"]).exists():
        raise ValidationError("Resolve pending gateway payments before voiding this invoice.")
    if invoice.finance_payments.filter(status="posted").exists():
        raise ValidationError("Reverse unreconciled payments before voiding an invoice; paid documents cannot be voided.")
    if invoice.status != "issued" or not reason.strip():
        raise ValidationError("Only an issued invoice can be voided, with a reason.")
    invoice.status, invoice.void_reason, invoice.voided_at = "void", reason.strip(), timezone.now()
    invoice.full_clean()
    managed_save(invoice)
    event(actor, "invoice", invoice.pk, "invoice_voided", reason=reason)
    return invoice
