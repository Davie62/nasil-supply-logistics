from django.conf import settings
from django.db import models
from operations.commercial import CommercialRecord


class Supplier(CommercialRecord):
    name = models.CharField(max_length=200)
    registration_number = models.CharField(max_length=80, unique=True)
    email = models.EmailField()
    phone = models.CharField(max_length=30)
    address = models.TextField(max_length=2000)
    is_active = models.BooleanField(default=True)


class SupplierAudit(CommercialRecord):
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="audits")
    outcome = models.CharField(max_length=10, choices=[("pass", "Pass"), ("fail", "Fail")])
    valid_until = models.DateField()
    notes = models.TextField(max_length=2000)
    audited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)


class ProcurementRequest(CommercialRecord):
    number = models.CharField(max_length=40, unique=True)
    purpose = models.CharField(max_length=255)
    currency = models.CharField(max_length=3, choices=[("UGX", "UGX"), ("USD", "USD")])
    budget = models.DecimalField(max_digits=15, decimal_places=2)
    order = models.ForeignKey("orders.Order", on_delete=models.PROTECT, null=True, blank=True)
    status = models.CharField(max_length=15, choices=[(code, code.title()) for code in ("draft", "submitted", "approved", "cancelled")], default="draft")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="procurement_requests")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="approved_requests")
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta(CommercialRecord.Meta):
        permissions = [("approve_procurementrequest", "Can approve procurement requests")]
        constraints = [models.CheckConstraint(condition=models.Q(budget__gt=0), name="procurement_positive_budget")]


class PurchaseOrder(CommercialRecord):
    number = models.CharField(max_length=40, unique=True)
    request = models.OneToOneField(ProcurementRequest, on_delete=models.PROTECT, related_name="purchase_order")
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="purchase_orders")
    currency = models.CharField(max_length=3)
    total = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=[(code, code.replace("_", " ").title()) for code in ("draft", "submitted", "approved", "sent", "partially_received", "received", "cancelled")], default="draft")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="prepared_purchase_orders")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="approved_purchase_orders")
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta(CommercialRecord.Meta):
        permissions = [("approve_purchaseorder", "Can approve purchase orders"), ("receive_purchaseorder", "Can receive purchased goods")]
        constraints = [models.CheckConstraint(condition=models.Q(total__gte=0), name="purchase_nonnegative_total")]


class PurchaseLine(CommercialRecord):
    def __str__(self):
        return f"Line {self.pk}: {self.stock.product.sku} ({self.received_quantity}/{self.quantity} received)"

    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.PROTECT, related_name="lines")
    stock = models.ForeignKey("inventory.StockLevel", on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=15, decimal_places=3)
    unit_price = models.DecimalField(max_digits=15, decimal_places=2)
    line_total = models.DecimalField(max_digits=15, decimal_places=2)
    received_quantity = models.DecimalField(max_digits=15, decimal_places=3, default=0)

    class Meta(CommercialRecord.Meta):
        constraints = [models.UniqueConstraint(fields=["purchase_order", "stock"], name="unique_purchase_stock"), models.CheckConstraint(condition=models.Q(quantity__gt=0, unit_price__gt=0, received_quantity__gte=0, received_quantity__lte=models.F("quantity")), name="purchase_valid_quantities")]


class GoodsReceipt(CommercialRecord):
    line = models.ForeignKey(PurchaseLine, on_delete=models.PROTECT, related_name="receipts")
    quantity = models.DecimalField(max_digits=15, decimal_places=3)
    movement = models.OneToOneField("operations.StockMovement", on_delete=models.PROTECT)
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    delivery_reference = models.CharField(max_length=150, unique=True)

    class Meta(CommercialRecord.Meta):
        constraints = [models.CheckConstraint(condition=models.Q(quantity__gt=0), name="receipt_positive_quantity")]
