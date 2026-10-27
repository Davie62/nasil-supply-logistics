"""Only staff workflow entry points may prepare or approve quotations."""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from core.business_rules import QUOTE_TRANSITIONS, require_permission, validate_approval, validate_transition, validate_version
from core.workflow_models import workflow_save
from .models import Quote


EDITABLE_FIELDS = {
    "customer", "service", "pickup_location", "destination", "transport_mode",
    "cargo_description", "weight", "cargo_value", "special_instructions",
    "trade_type", "base_amount", "rate_per_kg", "surcharge", "discount", "tax_rate", "valid_until",
}


def apply_details(quote, data):
    if set(data) - EDITABLE_FIELDS:
        raise ValidationError("Unsupported quotation fields. Use the status workflow for approval.")
    for field, value in data.items():
        setattr(quote, field, value)


@transaction.atomic
def create_quote(*, actor, data):
    require_permission(actor, "quotations.add_quote")
    quote = Quote(created_by=actor, prepared_by=actor)
    apply_details(quote, data)
    workflow_save(quote, actor, "created")
    return quote


@transaction.atomic
def update_quote(*, quote_id, actor, data, expected_version=None):
    require_permission(actor, "quotations.change_quote")
    quote = Quote.objects.select_for_update().get(pk=quote_id)
    validate_version(quote, expected_version)
    if quote.status == "approved" or hasattr(quote, "shipment") or hasattr(quote, "invoice") or hasattr(quote, "sales_order"):
        raise ValidationError("Reopen the quotation before editing. Converted quotations are locked.")
    apply_details(quote, data)
    quote.prepared_by = actor
    workflow_save(quote, actor, "updated")
    return quote


@transaction.atomic
def transition_quote(*, quote_id, actor, target, reason="", expected_version=None):
    require_permission(actor, "quotations.approve_quote" if target == "approved" else "quotations.change_quote")
    quote = Quote.objects.select_for_update().get(pk=quote_id)
    validate_version(quote, expected_version)
    validate_transition(quote.status, target, QUOTE_TRANSITIONS)
    if quote.status == target:
        return quote
    if hasattr(quote, "shipment") or hasattr(quote, "invoice") or hasattr(quote, "sales_order"):
        raise ValidationError("A converted quotation cannot change status.")
    reason = reason.strip()
    if (target == "rejected" or quote.status == "approved") and not reason:
        raise ValidationError("A reason is required to reject or reopen a quotation.")
    if target == "approved":
        quote.clean()
        validate_approval(quote, actor)
        quote.approved_by, quote.approved_at = actor, timezone.now()
    else:
        quote.approved_by, quote.approved_at = None, None
    quote.status = target
    workflow_save(quote, actor, "status_changed", reason)
    return quote
