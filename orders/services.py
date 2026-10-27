from decimal import Decimal, ROUND_HALF_UP
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from core.business_rules import require_permission, validate_transition, validate_version, validate_convertible
from operations.commercial import persist, number, approve, money, quantity, editable_data
from quotations.models import Quote
from shipments.models import Shipment
from .models import Order, OrderLine

TRANSITIONS = {"draft": {"submitted", "cancelled"}, "submitted": {"approved", "draft", "cancelled"}, "approved": {"fulfilled", "cancelled"}, "fulfilled": {"shipped"}, "shipped": {"closed"}, "closed": set(), "cancelled": set()}


@transaction.atomic
def save_order(*, actor, data, record_id=None, expected_version=None):
    require_permission(actor, "orders.change_order" if record_id else "orders.add_order", "quotations.view_quote")
    editable_data(data, ("quote", "notes"))
    quote = Quote.objects.select_for_update().get(pk=data["quote"].pk)
    validate_convertible(quote)
    order = Order.objects.select_for_update().get(pk=record_id) if record_id else Order(number=number("ORD"), created_by=actor, quote=quote, currency=quote.currency)
    validate_version(order, expected_version)
    if order.status != "draft" or order.quote_id != quote.pk:
        raise ValidationError("Only draft order notes can be edited; the quotation is fixed.")
    if Shipment.objects.filter(quote=quote).exclude(status="pending").exists():
        raise ValidationError("This quotation already has a dispatched or completed shipment.")
    order.notes = data.get("notes", "")
    return persist(order, actor, "order_saved")


@transaction.atomic
def add_line(*, actor, record_id, stock, quantity_value, unit_price, expected_version=None):
    require_permission(actor, "orders.change_order", "inventory.view_stocklevel")
    quote_id = Order.objects.values_list("quote_id", flat=True).get(pk=record_id)
    Quote.objects.select_for_update().get(pk=quote_id)
    order = Order.objects.select_for_update().get(pk=record_id)
    validate_version(order, expected_version)
    if order.status != "draft":
        raise ValidationError("Lines can only be changed on draft orders.")
    from inventory.services import validate_stock
    validate_stock(stock)
    qty, price = quantity(quantity_value), money(unit_price)
    line = OrderLine.objects.filter(order=order, stock=stock).first() or OrderLine(order=order, stock=stock)
    line.quantity, line.unit_price = qty, price
    line.line_total = (qty * price).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
    persist(line, actor, "order_line_saved")
    order.total = order.lines.aggregate(value=Sum("line_total"))["value"] or 0
    return persist(order, actor, "order_lines_updated")


@transaction.atomic
def transition_order(*, actor, record_id, target, expected_version=None, reason=""):
    require_permission(actor, "orders.change_order")
    quote_id = Order.objects.values_list("quote_id", flat=True).get(pk=record_id)
    quote = Quote.objects.select_for_update().get(pk=quote_id)
    order = Order.objects.select_for_update().get(pk=record_id)
    validate_version(order, expected_version)
    if target == order.status:
        return order
    validate_transition(order.status, target, TRANSITIONS)
    if target in {"submitted", "approved", "fulfilled"}:
        validate_convertible(quote)
        if not order.lines.exists() or order.total != quote.total_amount or order.currency != quote.currency:
            raise ValidationError("Order line totals and currency must match the approved quotation before submission or fulfillment.")
    from inventory.services import reserve_order, release_order
    if target == "approved":
        approve(actor, order, "orders.approve_order", order.total, order.currency)
        reserve_order(order, actor)
        order.approved_by, order.approved_at = actor, timezone.now()
    elif target == "fulfilled":
        require_permission(actor, "orders.fulfill_order", "operations.adjust_inventory")
        from inventory.models import Reservation
        if Reservation.objects.filter(order_line__order=order, status="reserved").count() != order.lines.count():
            raise ValidationError("Every order line must have a reservation before fulfillment.")
        release_order(order, actor, consume=True)
        from shipments.workflows import convert_quote_to_shipment
        order.shipment = convert_quote_to_shipment(quote_id=quote.pk, actor=actor)
    elif target == "shipped":
        from shipments.workflows import transition_shipment
        transition_shipment(shipment_id=order.shipment_id, actor=actor, target="in_transit")
        order.refresh_from_db()  # Shipment signal synchronizes the linked order.
    elif target == "closed":
        if not order.shipment_id or order.shipment.status != "delivered":
            raise ValidationError("Delivery must be confirmed before closing an order.")
    elif target == "cancelled":
        if not reason.strip():
            raise ValidationError("A cancellation reason is required.")
        release_order(order, actor)
    order.status = target
    persist(order, actor, "order_transition", target=target, reason=reason)
    if target == "cancelled":
        booking = Shipment.objects.filter(quote=quote, status="pending").first()
        if booking:
            from shipments.workflows import transition_shipment
            transition_shipment(shipment_id=booking.pk, actor=actor, target="cancelled", reason=reason)
    return order


def validate_linked_shipment(shipment, target):
    order = Order.objects.filter(quote_id=shipment.quote_id).first()
    if not order:
        return
    if target == "in_transit" and (order.status != "fulfilled" or order.shipment_id != shipment.pk):
        raise ValidationError("Fulfill the linked order and reserve/issue its stock before dispatch.")
    if target == "cancelled" and order.status not in {"cancelled", "draft", "submitted"}:
        raise ValidationError("Cancel the order before cancelling its booking. Issued stock requires a controlled return.")
