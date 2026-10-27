from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from core.business_rules import require_permission, validate_version
from operations.commercial import persist, editable_data, quantity
from operations.models import InventoryItem
from operations.services import save_inventory, move_stock, event
from .models import Product, StockLevel, Reservation, Warehouse


def reserved_for_item(item_id):
    return Reservation.objects.filter(stock__item_id=item_id, status="reserved").aggregate(value=Sum("quantity"))["value"] or Decimal("0")


def validate_stock(stock):
    if not stock.product.is_active or not stock.item.is_active or not stock.item.warehouse.is_active or stock.item.warehouse.is_deleted:
        raise ValidationError("Choose an active product, stock level and warehouse.")


@transaction.atomic
def save_product(*, actor, data, record_id=None, expected_version=None):
    require_permission(actor, "inventory.change_product" if record_id else "inventory.add_product")
    editable_data(data, ("sku", "name", "unit", "description", "is_active"))
    product = Product.objects.select_for_update().get(pk=record_id) if record_id else Product()
    validate_version(product, expected_version)
    data = dict(data)
    data["sku"] = data.get("sku", product.sku).strip().upper()
    if record_id and product.stock_levels.exists() and any(data.get(key, getattr(product, key)) != getattr(product, key) for key in ("sku", "unit")):
        raise ValidationError("SKU and unit are locked once stock records exist.")
    if not data.get("is_active", product.is_active) and Reservation.objects.filter(stock__product=product, status="reserved").exists():
        raise ValidationError("Fulfill or release open reservations before archiving this product.")
    for key, value in data.items():
        setattr(product, key, value)
    return persist(product, actor, "product_saved")


@transaction.atomic
def save_stock(*, actor, data, record_id=None, expected_version=None):
    require_permission(actor, "inventory.change_stocklevel" if record_id else "inventory.add_stocklevel")
    editable_data(data, ("product", "warehouse", "reorder_level", "is_active"))
    level = StockLevel.objects.select_for_update().select_related("item").get(pk=record_id) if record_id else StockLevel()
    validate_version(level, expected_version)
    product, warehouse = data["product"], data["warehouse"]
    if not product.is_active:
        raise ValidationError("Choose an active product.")
    if record_id and (level.product_id != product.pk or level.item.warehouse_id != warehouse.pk):
        raise ValidationError("Product and warehouse are locked after stock creation.")
    item = level.item if record_id else InventoryItem.objects.select_for_update().filter(sku=product.sku, warehouse=warehouse).first()
    if item and item.unit != product.unit:
        raise ValidationError("Legacy stock has a different unit; reconcile it before linking.")
    item = save_inventory(actor=actor, item_id=item.pk if item else None, expected_version=item.version if item else None,
        data={"sku": product.sku, "name": product.name, "unit": product.unit, "warehouse": warehouse,
              "reorder_level": data["reorder_level"], "is_active": data["is_active"]})
    level.product, level.item = product, item
    return persist(level, actor, "stock_linked")


@transaction.atomic
def save_warehouse(*, actor, data, record_id=None, expected_version=None):
    require_permission(actor, "inventory.change_warehouse" if record_id else "inventory.add_warehouse")
    editable_data(data, ("branch", "name", "code", "location", "capacity", "manager", "is_active"))
    warehouse = Warehouse.all_objects.select_for_update().get(pk=record_id) if record_id else Warehouse(created_by=actor)
    if record_id and expected_version is not None and str(warehouse.updated_at) != str(expected_version):
        raise ValidationError("Warehouse changed. Reload before saving.")
    if not data["is_active"] and Reservation.objects.filter(stock__item__warehouse=warehouse, status="reserved").exists():
        raise ValidationError("Release reservations before archiving the warehouse.")
    if not data["branch"].is_active:
        raise ValidationError("Choose an active branch.")
    for key, value in data.items():
        setattr(warehouse, key, value)
    warehouse.updated_by = actor
    warehouse.full_clean()
    warehouse.save()
    event(actor, "warehouse", warehouse.pk, "warehouse_saved", code=warehouse.code, active=warehouse.is_active)
    return warehouse


@transaction.atomic
def adjust_stock(*, actor, record_id, quantity_change, reason, expected_version=None):
    require_permission(actor, "inventory.change_stocklevel", "operations.adjust_inventory")
    level = StockLevel.objects.select_related("product", "item__warehouse").get(pk=record_id)
    validate_version(level, expected_version)
    validate_stock(level)
    item = InventoryItem.objects.select_for_update().get(pk=level.item_id)
    return move_stock(actor=actor, item_id=item.pk, quantity_change=quantity_change, reason=reason, expected_version=item.version)


def reserve_order(order, actor):
    lines = list(order.lines.select_related("stock__product", "stock__item__warehouse").order_by("stock__item_id"))
    for line in lines:
        validate_stock(line.stock)
        item = InventoryItem.objects.select_for_update().get(pk=line.stock.item_id)
        if item.quantity - reserved_for_item(item.pk) < line.quantity:
            raise ValidationError(f"Insufficient available stock for {line.stock.product.sku}.")
        persist(Reservation(stock=line.stock, order_line=line, quantity=line.quantity), actor, "stock_reserved", order=order.number)


def release_order(order, actor, consume=False):
    for reservation in Reservation.objects.filter(order_line__order=order, status="reserved").select_related("stock__item").order_by("stock__item_id"):
        item = InventoryItem.objects.select_for_update().get(pk=reservation.stock.item_id)
        reservation.status = "consumed" if consume else "released"
        persist(reservation, actor, "stock_consumed" if consume else "reservation_released", order=order.number)
        if consume:
            move_stock(actor=actor, item_id=item.pk, quantity_change=-reservation.quantity, reason=f"Fulfillment {order.number}", expected_version=item.version)
