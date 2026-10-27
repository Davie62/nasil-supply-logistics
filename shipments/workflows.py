from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from core.business_rules import SHIPMENT_TRANSITIONS, require_permission, validate_convertible, validate_transition, validate_version
from core.workflow_models import workflow_save
from quotations.models import Quote
from .models import Shipment


def validate_delivery_date(value, previous=None):
    if value and value != previous and value < timezone.localdate():
        raise ValidationError("A new estimated delivery date cannot be in the past.")


@transaction.atomic
def convert_quote_to_shipment(*, quote_id, actor, carrier=None, current_location="", estimated_delivery=None):
    require_permission(actor, "shipments.add_shipment", "quotations.view_quote")
    quote = Quote.objects.select_for_update().get(pk=quote_id)
    # A retry returns the existing booking without creating a second event.
    existing = Shipment.objects.filter(quote=quote).first()
    if existing:
        return existing
    validate_convertible(quote)
    validate_delivery_date(estimated_delivery)
    shipment = Shipment(quote=quote, carrier=carrier, current_location=current_location or quote.pickup_location,
                        estimated_delivery=estimated_delivery, created_by=actor)
    workflow_save(shipment, actor, "converted_from_quote")
    return shipment


@transaction.atomic
def update_shipment(*, shipment_id, actor, target=None, reason="", expected_version=None, **details):
    require_permission(actor, "shipments.change_shipment")
    # Same lock order as conversion/reopening: quotation, then shipment.
    quote_id = Shipment.objects.values_list("quote_id", flat=True).get(pk=shipment_id)
    Quote.objects.select_for_update().get(pk=quote_id)
    shipment = Shipment.objects.select_for_update().get(pk=shipment_id)
    validate_version(shipment, expected_version)
    if set(details) - {"carrier", "current_location", "estimated_delivery"}:
        raise ValidationError("Unsupported shipment fields; the source quotation cannot be changed.")
    target = target or shipment.status
    validate_transition(shipment.status, target, SHIPMENT_TRANSITIONS)
    if shipment.status in {"delivered", "cancelled"}:
        raise ValidationError("Completed or cancelled shipments are locked.")
    reason = reason.strip()
    if target == "cancelled" and not reason:
        raise ValidationError("A reason is required to cancel a shipment.")
    validate_delivery_date(details.get("estimated_delivery"), shipment.estimated_delivery)
    previous_status = shipment.status
    if target != previous_status:
        from orders.services import validate_linked_shipment
        validate_linked_shipment(shipment, target)
        if target == "in_transit":
            from fleet.services import validate_dispatch
            validate_dispatch(shipment)
    for field, value in details.items():
        setattr(shipment, field, value)
    if previous_status != target:
        timestamp_field = {"in_transit": "dispatched_at", "delivered": "delivered_at", "cancelled": "cancelled_at"}[target]
        setattr(shipment, timestamp_field, timezone.now())
    shipment.status = target
    workflow_save(shipment, actor, "status_changed" if previous_status != target else "updated", reason)
    if target in {"delivered", "cancelled"}:
        from fleet.services import release_completed
        release_completed(shipment, actor)
    return shipment


def transition_shipment(*, shipment_id, actor, target, reason="", expected_version=None):
    return update_shipment(shipment_id=shipment_id, actor=actor, target=target, reason=reason, expected_version=expected_version)
