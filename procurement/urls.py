from django.urls import path
from operations.module_ui import resource_urls, home_view, Action
from orders.forms import LineForm
from .models import Supplier, ProcurementRequest, PurchaseOrder, SupplierAudit
from .forms import SupplierForm, RequestForm, PurchaseForm, AuditForm, RequestTransitionForm, PurchaseTransitionForm, receipt_form
from .services import save_supplier, audit_supplier, save_request, transition_request, save_purchase_order, add_purchase_line, transition_purchase, receive_goods

app_name = "procurement"
urlpatterns = [path("", home_view("Procurement", [("Suppliers", "procurement:suppliers_list", "procurement.view_supplier"),
    ("Procurement requests", "procurement:requests_list", "procurement.view_procurementrequest"), ("Purchase orders", "procurement:purchases_list", "procurement.view_purchaseorder")],
    lambda request: [("Active suppliers", Supplier.objects.filter(is_active=True).count()), ("Requests awaiting Admin", ProcurementRequest.objects.filter(status="submitted").count()),
        ("Purchases awaiting Admin", PurchaseOrder.objects.filter(status="submitted").count()), ("Awaiting goods", PurchaseOrder.objects.filter(status__in=["sent", "partially_received"]).count())]), name="home")]
urlpatterns += resource_urls(model=Supplier, slug="suppliers", form_class=SupplierForm, save=save_supplier,
    columns=["Supplier", "Registration", "Email", "Phone", "Active"], fields=["name", "registration_number", "email", "phone", "is_active"], search_fields=["name", "registration_number", "email"],
    actions={"audit": Action("Record supplier audit", "procurement.add_supplieraudit", lambda obj: AuditForm, audit_supplier)},
    related=lambda obj: [{"title": "Supplier audit history", "columns": ["Outcome", "Valid until", "Notes", "Auditor", "Timestamp"], "rows": obj.audits.values_list("outcome", "valid_until", "notes", "audited_by__username", "created_at")[:100]}])
urlpatterns += resource_urls(model=ProcurementRequest, slug="requests", form_class=RequestForm, save=save_request,
    columns=["Request", "Purpose", "Currency", "Budget", "Status", "Order", "Approver"], fields=["number", "purpose", "currency", "budget", "get_status_display", "order", "approved_by"],
    search_fields=["number", "purpose"], select=["order", "approved_by"], actions={"transition": Action("Change request status", "procurement.change_procurementrequest", lambda obj: RequestTransitionForm, transition_request)})
urlpatterns += resource_urls(model=PurchaseOrder, slug="purchases", form_class=PurchaseForm, save=save_purchase_order,
    columns=["Purchase order", "Supplier", "Request", "Currency", "Total", "Status", "Approver"], fields=["number", "supplier", "request", "currency", "total", "get_status_display", "approved_by"],
    search_fields=["number", "supplier__name", "request__number"], select=["supplier", "request", "approved_by"],
    actions={"line": Action("Add / replace purchase line", "procurement.change_purchaseorder", lambda obj: LineForm, add_purchase_line),
        "transition": Action("Change purchase status", "procurement.change_purchaseorder", lambda obj: PurchaseTransitionForm, transition_purchase),
        "receive": Action("Receive purchased goods", "procurement.receive_purchaseorder", receipt_form, receive_goods)},
    related=lambda obj: [{"title": "Purchase lines", "columns": ["ID", "Stock", "Ordered", "Received", "Unit price", "Total"], "rows": [(line.pk, line.stock, line.quantity, line.received_quantity, line.unit_price, line.line_total) for line in obj.lines.select_related("stock__product", "stock__item__warehouse")[:100]]},
        {"title": "Supplier payments", "columns": ["Reference", "Amount", "Currency", "Status"], "rows": obj.payments.values_list("external_reference", "amount", "currency", "status")[:100]}])
