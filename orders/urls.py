from django.urls import path
from operations.module_ui import resource_urls, home_view, Action
from .models import Order
from .forms import OrderForm, LineForm, TransitionForm
from .services import save_order, add_line, transition_order

app_name = "orders"
urlpatterns = [path("", home_view("Orders", [("Customer orders", "orders:orders_list", "orders.view_order")],
    lambda request: [("Awaiting approval", Order.objects.filter(status="submitted").count()), ("Ready to fulfill", Order.objects.filter(status="approved").count()),
        ("In transit", Order.objects.filter(status="shipped").count())]), name="home")]
urlpatterns += resource_urls(model=Order, slug="orders", form_class=OrderForm, save=save_order,
    columns=["Order", "Quotation", "Status", "Currency", "Total", "Shipment", "Approved by", "Updated"],
    fields=["number", "quote", "get_status_display", "currency", "total", "shipment", "approved_by", "updated_at"],
    search_fields=["number", "quote__customer__full_name"], select=["quote__customer", "shipment", "approved_by"],
    actions={"line": Action("Add / replace line", "orders.change_order", lambda obj: LineForm, add_line),
             "transition": Action("Change order status", "orders.change_order", lambda obj: TransitionForm, transition_order)},
    related=lambda obj: [{"title": "Order lines (totals must match quotation)", "columns": ["Stock", "Quantity", "Unit price", "Total"],
        "rows": [(line.stock, line.quantity, line.unit_price, line.line_total) for line in obj.lines.select_related("stock__product", "stock__item__warehouse")[:100]]}])
