from django.urls import path
from django.db.models import F
from operations.module_ui import resource_urls, home_view, Action
from .models import Product, StockLevel, Warehouse
from .forms import ProductForm, StockForm, WarehouseForm, AdjustmentForm
from .services import save_product, save_stock, save_warehouse, adjust_stock, reserved_for_item

app_name = "inventory"
urlpatterns = [path("", home_view("Inventory", [
    ("Products", "inventory:products_list", "inventory.view_product"), ("Stock levels", "inventory:stock_list", "inventory.view_stocklevel"),
    ("Warehouses", "inventory:warehouses_list", "inventory.view_warehouse")],
    lambda request: [("Products", Product.objects.count()), ("Active stock levels", StockLevel.objects.filter(item__is_active=True).count()),
        ("Low-stock alerts", StockLevel.objects.filter(item__is_active=True, item__quantity__lte=F("item__reorder_level")).count())]), name="home")]
urlpatterns += resource_urls(model=Product, slug="products", form_class=ProductForm, save=save_product,
    columns=["SKU", "Product", "Unit", "Active"], fields=["sku", "name", "unit", "is_active"], search_fields=["sku", "name"])
urlpatterns += resource_urls(model=StockLevel, slug="stock", form_class=StockForm, save=save_stock,
    columns=["Stock", "On hand", "Updated"], fields=["__str__", "quantity", "updated_at"], search_fields=["product__sku", "product__name", "item__warehouse__name"], select=["product", "item__warehouse"],
    actions={"adjust": Action("Receive / issue stock", "operations.adjust_inventory", lambda obj: AdjustmentForm,
        adjust_stock)},
    related=lambda obj: [{"title": "Availability", "columns": ["On hand", "Reserved", "Available", "Reorder level", "Low-stock alert"],
        "rows": [(obj.quantity, reserved_for_item(obj.item_id), obj.quantity-reserved_for_item(obj.item_id), obj.item.reorder_level, "Low stock" if obj.quantity <= obj.item.reorder_level else "Within target")]},
        {"title": "Stock movements", "columns": ["Quantity", "Balance", "Reason", "Timestamp"], "rows": obj.item.movements.values_list("quantity_change", "balance_after", "reason", "created_at")[:100]}])
urlpatterns += resource_urls(model=Warehouse, slug="warehouses", form_class=WarehouseForm, save=save_warehouse,
    columns=["Code", "Warehouse", "Location", "Active"], fields=["code", "name", "location", "is_active"], search_fields=["code", "name", "location"], entity="warehouse", queryset=lambda: Warehouse.all_objects.filter(is_deleted=False).order_by("name"))
