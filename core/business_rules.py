"""Reusable, side-effect-free rules shared by quotation and shipment workflows."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone


QUOTE_TRANSITIONS = {
    "pending": {"reviewed", "rejected"},
    "reviewed": {"approved", "rejected", "pending"},
    "approved": {"reviewed"},  # Explicitly reopen before changing commercial terms.
    "rejected": {"pending"},
}
SHIPMENT_TRANSITIONS = {
    "pending": {"in_transit", "cancelled"},
    "in_transit": {"delivered", "cancelled"},
    "delivered": set(), "cancelled": set(),
}


def require_permission(actor, *permissions):
    if not actor or not actor.is_active or not actor.is_staff or not actor.has_perms(permissions):
        raise PermissionDenied("You do not have permission to perform this operation.")


def validate_transition(current, target, transitions):
    if current != target and target not in transitions.get(current, set()):
        raise ValidationError(f"Cannot change status from {current} to {target}.")


def validate_version(instance, expected_version):
    if expected_version is not None and instance.version != expected_version:
        raise ValidationError("This record changed since you opened it. Reload before saving.")


def decimal_value(value, label, minimum=Decimal("0")):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError(f"{label} must be a valid number.")
    if not number.is_finite() or number < minimum:
        raise ValidationError(f"{label} must be at least {minimum}.")
    return number


def calculate_price(*, weight, base_amount, rate_per_kg, surcharge, discount, tax_rate):
    weight = decimal_value(weight, "Weight", Decimal("0.01"))
    base = decimal_value(base_amount, "Base amount")
    rate = decimal_value(rate_per_kg, "Rate per kg")
    extra = decimal_value(surcharge, "Surcharge")
    reduction = decimal_value(discount, "Discount")
    tax = decimal_value(tax_rate, "Tax rate")
    if tax > 100:
        raise ValidationError("Tax rate cannot exceed 100 percent.")
    subtotal = (base + weight * rate + extra - reduction).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if subtotal < 0:
        raise ValidationError("Discount cannot exceed the charges.")
    tax_amount = (subtotal * tax / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    total = subtotal + tax_amount
    if total > Decimal("9999999999999.99"):
        raise ValidationError("Quotation total exceeds the supported amount.")
    return subtotal, tax_amount, total


def approval_limit(currency):
    from operations.policy import threshold_policy
    policy = threshold_policy()
    if not isinstance(policy, dict) or currency not in policy:
        raise ValidationError(f"Approval threshold is not configured for {currency}. Contact an administrator.")
    return decimal_value(policy[currency], "Approval threshold")


def validate_approval(quote, actor):
    require_permission(actor, "quotations.approve_quote")
    if actor.pk in {quote.created_by_id, quote.prepared_by_id}:
        raise ValidationError("The quotation preparer cannot approve their own quotation.")
    validate_commercial_terms(quote)
    if quote.total_amount > approval_limit(quote.currency):
        require_permission(actor, "quotations.approve_high_value_quote")
        if not actor.is_superuser and not actor.groups.filter(name="Administrator").exists():
            raise PermissionDenied("Only an Administrator may approve above-threshold quotations.")


def validate_commercial_terms(quote):
    if quote.total_amount <= 0:
        raise ValidationError("A positive quotation price is required.")
    if not quote.valid_until or quote.valid_until < timezone.localdate():
        raise ValidationError("Set a quotation validity date of today or later.")


def validate_convertible(quote):
    if quote.status != "approved" or not quote.approved_at or not quote.approved_by_id:
        raise ValidationError("Only a quotation approved through the approval workflow can become a shipment.")
    validate_commercial_terms(quote)
