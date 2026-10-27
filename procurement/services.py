from decimal import Decimal, ROUND_HALF_UP
from django.core.exceptions import ValidationError
from django.db import transaction, models
from django.db.models import Sum
from django.utils import timezone
from core.business_rules import require_permission, validate_version, validate_transition
from operations.commercial import persist, number, money, quantity, approve, editable_data
from operations.services import move_stock
from operations.models import InventoryItem
from .models import Supplier, SupplierAudit, ProcurementRequest, PurchaseOrder, PurchaseLine, GoodsReceipt


def audited_supplier(supplier):
    audit = supplier.audits.order_by("-created_at", "-pk").first()
    if not supplier.is_active or not audit or audit.outcome != "pass" or audit.valid_until < timezone.localdate():
        raise ValidationError("An active supplier with a current passing audit is required.")


@transaction.atomic
def save_supplier(*, actor, data, record_id=None, expected_version=None):
    require_permission(actor, "procurement.change_supplier" if record_id else "procurement.add_supplier")
    editable_data(data, ("name", "registration_number", "email", "phone", "address", "is_active"))
    supplier = Supplier.objects.select_for_update().get(pk=record_id) if record_id else Supplier()
    validate_version(supplier, expected_version)
    for key, value in data.items():
        setattr(supplier, key, value)
    return persist(supplier, actor, "supplier_saved")


@transaction.atomic
def audit_supplier(*, actor, record_id, outcome, valid_until, notes, expected_version=None):
    require_permission(actor, "procurement.add_supplieraudit")
    supplier = Supplier.objects.select_for_update().get(pk=record_id)
    validate_version(supplier, expected_version)
    if valid_until < timezone.localdate() or not notes.strip():
        raise ValidationError("Audit notes and a current validity date are required.")
    persist(SupplierAudit(supplier=supplier, outcome=outcome, valid_until=valid_until, notes=notes, audited_by=actor), actor, "supplier_audited")
    return persist(supplier, actor, "supplier_audit_updated", outcome=outcome)


@transaction.atomic
def save_request(*, actor, data, record_id=None, expected_version=None):
    require_permission(actor, "procurement.change_procurementrequest" if record_id else "procurement.add_procurementrequest")
    editable_data(data, ("purpose", "currency", "budget", "order"))
    request = ProcurementRequest.objects.select_for_update().get(pk=record_id) if record_id else ProcurementRequest(number=number("PR"), created_by=actor)
    validate_version(request, expected_version)
    if request.status != "draft":
        raise ValidationError("Only draft procurement requests can be edited.")
    if data.get("order") and (data["order"].currency != data["currency"] or data["order"].status in {"closed", "cancelled"}):
        raise ValidationError("Choose an open order in the same currency.")
    for key, value in data.items():
        setattr(request, key, value)
    request.budget = money(request.budget)
    return persist(request, actor, "request_saved")


@transaction.atomic
def transition_request(*, actor, record_id, target, expected_version=None, reason=""):
    require_permission(actor, "procurement.change_procurementrequest")
    request = ProcurementRequest.objects.select_for_update().get(pk=record_id)
    validate_version(request, expected_version)
    if target == request.status:
        return request
    validate_transition(request.status, target, {"draft": {"submitted", "cancelled"}, "submitted": {"approved", "draft", "cancelled"}, "approved": {"cancelled"}, "cancelled": set()})
    if target == "approved":
        approve(actor, request, "procurement.approve_procurementrequest", request.budget, request.currency)
        request.approved_by, request.approved_at = actor, timezone.now()
    if target == "cancelled" and (not reason.strip() or PurchaseOrder.objects.filter(request=request).exclude(status="cancelled").exists()):
        raise ValidationError("Provide a reason and cancel any linked purchase order first.")
    request.status = target
    return persist(request, actor, "request_transition", target=target, reason=reason)


@transaction.atomic
def save_purchase_order(*, actor, data, record_id=None, expected_version=None):
    require_permission(actor, "procurement.change_purchaseorder" if record_id else "procurement.add_purchaseorder")
    editable_data(data, ("request", "supplier"))
    request = ProcurementRequest.objects.select_for_update().get(pk=data["request"].pk)
    if request.status != "approved" or not request.approved_at:
        raise ValidationError("Approve the procurement request first.")
    audited_supplier(data["supplier"])
    purchase = PurchaseOrder.objects.select_for_update().get(pk=record_id) if record_id else PurchaseOrder(number=number("PO"), request=request, currency=request.currency, created_by=actor)
    validate_version(purchase, expected_version)
    if purchase.status != "draft" or purchase.request_id != request.pk:
        raise ValidationError("Only draft supplier details can be changed; the request is fixed.")
    purchase.supplier = data["supplier"]
    return persist(purchase, actor, "purchase_order_saved")


@transaction.atomic
def add_purchase_line(*, actor, record_id, stock, quantity_value, unit_price, expected_version=None):
    require_permission(actor, "procurement.change_purchaseorder", "inventory.view_stocklevel")
    purchase = PurchaseOrder.objects.select_for_update().get(pk=record_id)
    validate_version(purchase, expected_version)
    if purchase.status != "draft":
        raise ValidationError("Purchase lines can only be changed while draft.")
    from inventory.services import validate_stock
    validate_stock(stock)
    qty, price = quantity(quantity_value), money(unit_price)
    line = PurchaseLine.objects.filter(purchase_order=purchase, stock=stock).first() or PurchaseLine(purchase_order=purchase, stock=stock)
    line.quantity, line.unit_price = qty, price
    line.line_total = (qty * price).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
    persist(line, actor, "purchase_line_saved")
    purchase.total = purchase.lines.aggregate(value=Sum("line_total"))["value"] or 0
    return persist(purchase, actor, "purchase_lines_updated")


@transaction.atomic
def transition_purchase(*, actor, record_id, target, expected_version=None, reason=""):
    require_permission(actor, "procurement.change_purchaseorder")
    request_id = PurchaseOrder.objects.values_list("request_id", flat=True).get(pk=record_id)
    request = ProcurementRequest.objects.select_for_update().get(pk=request_id)
    purchase = PurchaseOrder.objects.select_for_update().get(pk=record_id)
    validate_version(purchase, expected_version)
    if target == purchase.status:
        return purchase
    validate_transition(purchase.status, target, {"draft": {"submitted", "cancelled"}, "submitted": {"approved", "draft", "cancelled"}, "approved": {"sent", "cancelled"}, "sent": {"cancelled"}, "partially_received": set(), "received": set(), "cancelled": set()})
    if target in {"submitted", "approved", "sent"}:
        audited_supplier(purchase.supplier)
        if request.status != "approved" or purchase.total <= 0 or purchase.total > request.budget or not purchase.lines.exists():
            raise ValidationError("An approved request and positive purchase lines within its budget are required.")
    if target == "approved":
        approve(actor, purchase, "procurement.approve_purchaseorder", purchase.total, purchase.currency)
        purchase.approved_by, purchase.approved_at = actor, timezone.now()
    if target == "cancelled" and (not reason.strip() or purchase.payments.filter(status="posted").exists() or purchase.lines.filter(received_quantity__gt=0).exists()):
        raise ValidationError("Provide a reason; received or paid purchases cannot be cancelled.")
    purchase.status = target
    return persist(purchase, actor, "purchase_transition", target=target, reason=reason)


@transaction.atomic
def receive_goods(*, actor, record_id, line, quantity_value, delivery_reference, expected_version=None):
    require_permission(actor, "procurement.receive_purchaseorder", "operations.adjust_inventory")
    purchase = PurchaseOrder.objects.select_for_update().get(pk=record_id)
    qty = quantity(quantity_value)
    existing = GoodsReceipt.objects.filter(delivery_reference=delivery_reference).first()
    if existing:
        if existing.line_id != line.pk or existing.quantity != qty:
            raise ValidationError("Receipt reference was already used for different goods.")
        return purchase
    validate_version(purchase, expected_version)
    if purchase.status not in {"sent", "partially_received"}:
        raise ValidationError("Only sent purchase orders can receive goods.")
    audited_supplier(purchase.supplier)
    line = PurchaseLine.objects.select_for_update().get(pk=line.pk, purchase_order=purchase)
    from inventory.services import validate_stock
    validate_stock(line.stock)
    if line.received_quantity + qty > line.quantity:
        raise ValidationError("Receipt quantity exceeds the outstanding purchased quantity.")
    item = InventoryItem.objects.select_for_update().get(pk=line.stock.item_id)
    movement = move_stock(actor=actor, item_id=item.pk, quantity_change=qty, reason=f"Receipt {purchase.number}: {delivery_reference}", expected_version=item.version)
    line.received_quantity += qty
    persist(line, actor, "purchase_line_received", quantity=str(qty))
    persist(GoodsReceipt(line=line, quantity=qty, movement=movement, received_by=actor, delivery_reference=delivery_reference), actor, "goods_received")
    purchase.status = "received" if not purchase.lines.exclude(received_quantity=models.F("quantity")).exists() else "partially_received"
    return persist(purchase, actor, "purchase_receipt_updated")
